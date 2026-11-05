//! Process custody for a prepared application generation. Claims are actual
//! app/root/store directory flocks, retained by every opened native handle.
//! This first boundary grants read-only access only. Foundry admission is a
//! separate durable decision; possessing a path or receipt never grants writes.
use super::{directory::{Directory, DirectoryHandle, Reader}, err, sealing::{Custody, relative}};
use rustler::{Binary, NifResult, Resource, ResourceArc};
use std::collections::HashMap;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock, Weak, atomic::{AtomicBool, Ordering}};

const MARKER: &str = ".bl-generation";
const LIMIT: usize = 1048576;
fn failure(message: &'static str) -> std::io::Error { std::io::Error::other(message) }
fn registry() -> &'static Mutex<HashMap<PathBuf, Weak<Owner>>> {
    static OWNERS: OnceLock<Mutex<HashMap<PathBuf, Weak<Owner>>>> = OnceLock::new();
    OWNERS.get_or_init(|| Mutex::new(HashMap::new()))
}
pub(crate) struct Owner {
    root: Arc<Directory>, app: Arc<Directory>, marker: Reader,
    stores: HashMap<PathBuf, Arc<Directory>>, closed: AtomicBool,
    // Store locks drop before either root's explicit custody pin.
    _root_custody: Custody, _app_custody: Custody,
}
impl Owner {
    pub(crate) fn check(&self) -> std::io::Result<()> {
        if self.closed.load(Ordering::Acquire) { return Err(failure("generation owner closed")); }
        self.root.check()?; self.app.check()?; self.marker.check()
    }
    pub(crate) fn store_lock(&self, path: &Path) -> std::io::Result<File> {
        self.check()?;
        self.stores.get(path).ok_or_else(|| failure("store outside generation inventory"))?.file.try_clone()
    }
    pub(crate) fn write_guard(&self) -> std::io::Result<std::sync::MutexGuard<'_, ()>> {
        self.check()?;
        Err(failure("generation has no durable write admission"))
    }
}
struct OwnerHandle(Mutex<Option<Arc<Owner>>>);
#[rustler::resource_impl]
impl Resource for OwnerHandle {}

/// Find protection through the nearest existing canonical ancestor, BEFORE
/// creation. A symlink or a nonexistent descendant cannot escape enrollment.
fn enrolled(path: &Path) -> std::io::Result<Option<PathBuf>> {
    let absolute = if path.is_absolute() { path.to_path_buf() } else { std::env::current_dir()?.join(path) };
    let mut existing = absolute;
    loop {
        match fs::symlink_metadata(&existing) {
            Ok(_) => break,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                if !existing.pop() { return Err(failure("generation path has no existing ancestor")); }
            }
            Err(e) => return Err(e),
        }
    }
    let canonical = fs::canonicalize(existing)?;
    // Metadata writes pass an existing FILE, not just store directories. A
    // protection marker belongs to its parent; probing file/.bl-generation
    // would return ENOTDIR and incorrectly refuse every journal replacement.
    let canonical = if fs::symlink_metadata(&canonical)?.is_dir() { canonical }
        else { canonical.parent().ok_or_else(|| failure("generation file has no parent"))?.to_path_buf() };
    for ancestor in canonical.ancestors() {
        match fs::symlink_metadata(ancestor.join(MARKER)) {
            Ok(_) => return Ok(Some(ancestor.into())),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e),
        }
    }
    Ok(None)
}

pub(crate) fn access(path: &Path) -> std::io::Result<Option<Arc<Owner>>> {
    let Some(root) = enrolled(path)? else { return Ok(None); };
    let owner = registry().lock().map_err(|_| failure("generation registry poisoned"))?
        .get(&root).and_then(Weak::upgrade).ok_or_else(|| failure("generation requires its application owner"))?;
    owner.check()?;
    Ok(Some(owner))
}
pub(crate) fn check_write(path: &Path) -> std::io::Result<()> {
    if let Some(owner) = access(path)? { drop(owner.write_guard()?); }
    Ok(())
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_claim(app: ResourceArc<DirectoryHandle>, root: ResourceArc<DirectoryHandle>,
                          expected: Binary, paths: Vec<String>) -> NifResult<ResourceArc<OwnerHandle>> {
    // Reject overlapping capabilities before taking two mutexes (same-root
    // derived handles must not deadlock or stand in for independent custody).
    if app.0.path.starts_with(&root.0.path) || root.0.path.starts_with(&app.0.path)
        || Arc::ptr_eq(&app.0.root, &root.0.root)
        || app.0.path != app.0.root.path || root.0.path != root.0.root.path
        || app.0.readonly() || root.0.readonly() {
        return Err(err("generation needs distinct writable app and data claims"));
    }
    let _app = app.0.root.write.lock().map_err(err)?;
    let _root = root.0.root.write.lock().map_err(err)?;
    app.0.check().map_err(err)?; root.0.check().map_err(err)?;
    if app.0.root.pins.load(Ordering::Acquire) != 0 || root.0.root.pins.load(Ordering::Acquire) != 0 {
        return Err(err("application or generation already retained"));
    }
    if expected.is_empty() || expected.len() > LIMIT || paths.is_empty() || paths.len() > 256 {
        return Err(err("invalid generation binding or inventory bound"));
    }
    super::refuse_offline_path(&root.0.path).map_err(err)?;
    super::refuse_offline_path(&app.0.path).map_err(err)?;
    if enrolled(&app.0.path).map_err(err)?.is_some() || enrolled(&root.0.path).map_err(err)?.as_ref() != Some(&root.0.path) {
        return Err(err("generation owner roots are not independent"));
    }
    let mut marker = root.0.open_file(MARKER).map_err(err)?;
    if marker.len() != expected.len() as u64 || marker.read(LIMIT).map_err(err)? != expected.as_slice() {
        return Err(err("generation marker does not match"));
    }
    let mut stores: HashMap<PathBuf, Arc<Directory>> = HashMap::new();
    for path in paths {
        let parts = relative(&path).map_err(err)?; let mut directory = root.0.clone();
        for (index, part) in parts.iter().enumerate() {
            directory = directory.child(part, false, index + 1 == parts.len()).map_err(err)?;
        }
        if stores.keys().any(|p| p.starts_with(&directory.path) || directory.path.starts_with(p)) {
            return Err(err("overlapping generation stores"));
        }
        super::require_existing_engine(&directory.path).map_err(err)?;
        stores.insert(directory.path.clone(), directory);
    }
    marker.check().map_err(err)?;
    let mut owners = registry().lock().map_err(err)?;
    owners.retain(|_, owner| owner.strong_count() != 0);
    if owners.get(&root.0.path).and_then(Weak::upgrade).is_some() {
        return Err(err("generation already has an owner"));
    }
    app.0.root.pins.fetch_add(1, Ordering::AcqRel);
    root.0.root.pins.fetch_add(1, Ordering::AcqRel);
    let owner = Arc::new(Owner { root: root.0.clone(), app: app.0.clone(), marker, stores,
        closed: AtomicBool::new(false), _root_custody: Custody(root.0.root.clone()),
        _app_custody: Custody(app.0.root.clone()) });
    owners.insert(root.0.path.clone(), Arc::downgrade(&owner));
    Ok(ResourceArc::new(OwnerHandle(Mutex::new(Some(owner)))))
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_release(handle: ResourceArc<OwnerHandle>) -> NifResult<bool> {
    let mut value = handle.0.lock().map_err(err)?;
    let owner = value.as_ref().ok_or_else(|| err("generation owner already released"))?;
    let _root = owner.root.root.write.lock().map_err(err)?;
    if Arc::strong_count(owner) != 1 { return Err(err("generation still has live native handles")); }
    owner.closed.store(true, Ordering::Release);
    drop(_root);
    value.take();
    Ok(true)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_guard(path: String) -> NifResult<bool> {
    super::refuse_offline_path(Path::new(&path)).map_err(err)?;
    if enrolled(Path::new(&path)).map_err(err)?.is_some() {
        return Err(err("generation blobs require an owned blob capability"));
    }
    Ok(true)
}
