//! Seal closed private target engines and carry their actual ownership through
//! accepted publication. This is a filesystem primitive, not READY verification
//! or an application deployment journal.
use super::{err, checkpoint, directory::{Directory, OfflineScope, Root, identity, name, pinned}};
use rustler::{Atom, Encoder, LocalPid, NifResult, OwnedEnv, Resource, ResourceArc, Term};
use std::fs::{self, File, Metadata};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};

mod atoms { rustler::atoms! { accepted, released, error } }
pub(crate) struct Custody(pub(crate) Arc<Root>);
impl Drop for Custody {
    fn drop(&mut self) { self.0.pins.fetch_sub(1, Ordering::AcqRel); }
}
struct Destination { path: PathBuf, parent: File, parent_metadata: Metadata, name: String }
impl Destination {
    fn check(&self) -> std::io::Result<()> {
        let parent = self.path.parent().ok_or_else(|| std::io::Error::other("destination parent missing"))?;
        if !identity(&self.parent_metadata, &self.parent.metadata()?)
            || !identity(&self.parent_metadata, &fs::symlink_metadata(parent)?) {
            return Err(std::io::Error::other("publication parent changed"));
        }
        Ok(())
    }
}
struct Publication { destination: Option<Destination>, moved: bool, stable: bool }
struct Sealed {
    scope: ResourceArc<OfflineScope>, target: Arc<Directory>,
    publication: Mutex<Publication>,
    // Drop closed-store locks before releasing the job's explicit custody pin.
    _stores: Vec<Arc<Directory>>, _original: Option<Arc<super::source::Original>>, _custody: Custody,
}
struct SealHandle { value: Mutex<Option<Arc<Sealed>>>, busy: AtomicBool }
#[rustler::resource_impl]
impl Resource for SealHandle {}

pub(crate) fn relative(parts: &str) -> std::io::Result<Vec<&str>> {
    let values: Vec<_> = parts.split('/').collect();
    if values.is_empty() || values.len() > 128 || parts.len() > 4096 {
        return Err(std::io::Error::other("invalid sealed store path"));
    }
    for value in &values { name(value)?; }
    Ok(values)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_seal(scope: ResourceArc<OfflineScope>, paths: Vec<String>)
 -> NifResult<ResourceArc<SealHandle>> {
    let _guard = scope.directory.root.write.lock().map_err(err)?;
    scope.directory.writable().map_err(err)?; scope.marker.check().map_err(err)?;
    if paths.is_empty() || paths.len() > 256 { return Err(err("invalid sealed store inventory")); }
    let target = scope.directory.child("target", false, true).map_err(err)?;
    target.writable().map_err(err)?;
    let mut stores = Vec::new(); let mut canonical = Vec::new();
    for path in paths {
        let mut current = target.clone(); let parts = relative(&path).map_err(err)?;
        for (index, part) in parts.iter().enumerate() {
            current = current.child(part, false, index + 1 == parts.len()).map_err(err)?;
        }
        if canonical.iter().any(|old: &PathBuf| old.starts_with(&current.path) || current.path.starts_with(old)) {
            return Err(err("overlapping sealed stores"));
        }
        super::require_existing_engine(&current.path).map_err(err)?;
        canonical.push(current.path.clone()); stores.push(current);
    }
    // Native handles opened through another copy of the same Scope cannot be
    // omitted from the declaration. Directory roots share this inventory.
    let opened = scope.directory.root.engines.lock().map_err(err)?;
    if opened.iter().any(|path| path.starts_with(&target.path) && !canonical.contains(path)) {
        return Err(err("sealed store inventory omitted a native opening"));
    }
    drop(opened);
    let original = scope.source.lock().map_err(err)?.clone();
    let mut seal = scope.directory.root.sealed.lock().map_err(err)?;
    if seal.is_some() { return Err(err("job target already sealed")); }
    *seal = Some(target.path.clone());
    scope.directory.root.pins.fetch_add(1, Ordering::AcqRel);
    let custody = Custody(scope.directory.root.clone());
    Ok(ResourceArc::new(SealHandle {
        value: Mutex::new(Some(Arc::new(Sealed { scope: scope.clone(), target,
            publication: Mutex::new(Publication { destination: None, moved: false, stable: false }),
            _stores: stores, _original: original, _custody: custody }))), busy: AtomicBool::new(false),
    }))
}

fn destination(scope: &OfflineScope, path: &Path) -> std::io::Result<Destination> {
    let parent_path = scope.directory.path.parent().ok_or_else(|| std::io::Error::other("job parent missing"))?;
    let leaf = path.file_name().and_then(|v| v.to_str()).ok_or_else(|| std::io::Error::other("invalid publication name"))?;
    name(leaf)?;
    if !path.is_absolute() || path.parent() != Some(parent_path) || path == scope.directory.path {
        return Err(std::io::Error::other("publication must be a distinct canonical sibling of the job"));
    }
    if fs::canonicalize(parent_path)? != parent_path {
        return Err(std::io::Error::other("publication parent is not canonical"));
    }
    // Pin the canonical parent through both directory fsyncs.
    use std::os::unix::fs::OpenOptionsExt;
    let parent = fs::OpenOptions::new().read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC).open(parent_path)?;
    let parent_metadata = parent.metadata()?;
    let result = Destination { path: path.into(), parent, parent_metadata, name: leaf.into() };
    result.check()?; Ok(result)
}

fn publish(sealed: &Sealed, wanted: &Path) -> Result<String, String> {
    let _guard = sealed.scope.directory.root.write.lock().map_err(|_| "job writer lock poisoned")?;
    sealed.scope.directory.check().map_err(|e| e.to_string())?;
    sealed.scope.marker.check().map_err(|e| e.to_string())?;
    let mut state = sealed.publication.lock().map_err(|_| "publication state poisoned")?;
    if let Some(old) = &state.destination {
        if old.path != wanted { return Err("sealed target destination changed".into()); }
    } else { state.destination = Some(destination(&sealed.scope, wanted).map_err(|e| e.to_string())?); }
    let dest = state.destination.as_ref().ok_or("publication destination missing")?;
    dest.check().map_err(|e| e.to_string())?;
    if !state.moved {
        sealed.target.check().map_err(|e| e.to_string())?;
        checkpoint::sync_tree_handle(&pinned(&sealed.scope.directory.file, "target"), &sealed.target.file)
            .map_err(|e| e.to_string())?;
        checkpoint::publish_no_clobber_at(&sealed.scope.directory.file, "target", &dest.parent, &dest.name)
            .map_err(|e| e.to_string())?;
        // Persist the visible outcome in native custody BEFORE any fallible
        // sync. A repeated call reconciles this same inode without overwriting.
        state.moved = true;
    }
    let dest = state.destination.as_ref().ok_or("publication destination missing")?;
    if !identity(&sealed.target.metadata, &fs::symlink_metadata(pinned(&dest.parent, &dest.name)).map_err(|e| e.to_string())?) {
        return Err("published target identity changed".into());
    }
    checkpoint::sync_tree_handle(&pinned(&dest.parent, &dest.name), &sealed.target.file).map_err(|e| e.to_string())?;
    sealed.scope.directory.file.sync_all().map_err(|e| e.to_string())?;
    dest.parent.sync_all().map_err(|e| e.to_string())?;
    dest.check().map_err(|e| e.to_string())?;
    state.stable = true;
    Ok(wanted.to_string_lossy().into_owned())
}

#[rustler::nif]
fn fjall_offline_publish(handle: ResourceArc<SealHandle>, path: String, recipient: LocalPid, tag: Term) -> NifResult<Atom> {
    handle.busy.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .map_err(|_| err("sealed publication in progress"))?;
    let sealed = match handle.value.lock() {
        Ok(value) => value.clone(),
        Err(_) => { handle.busy.store(false, Ordering::Release); return Err(err("sealed custody poisoned")); }
    };
    let Some(sealed) = sealed else {
        handle.busy.store(false, Ordering::Release); return Err(err("sealed custody released"));
    };
    let mut messages = OwnedEnv::new(); let saved_tag = messages.save(tag); let worker = handle.clone();
    let spawned = std::thread::Builder::new().name("datom-sealed-publish".into()).spawn(move || {
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| publish(&sealed, Path::new(&path))))
            .unwrap_or_else(|_| Err("sealed publication panicked; reconcile before retry".into()));
        drop(sealed);
        worker.busy.store(false, Ordering::Release);
        let _ = messages.send_and_clear(&recipient, |env| {
            let reply = match result { Ok(path) => path.encode(env), Err(reason) => (atoms::error(), reason).encode(env) };
            (saved_tag.load(env), reply).encode(env)
        });
    });
    if let Err(reason) = spawned { handle.busy.store(false, Ordering::Release); return Err(err(reason)); }
    Ok(atoms::accepted())
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_release(handle: ResourceArc<SealHandle>) -> NifResult<Atom> {
    // Serialize against acceptance with the same atomic flag, not a racy
    // check followed by removal of the resource the worker is about to clone.
    handle.busy.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .map_err(|_| err("sealed publication in progress"))?;
    let result = handle.value.lock().map(|mut value| { value.take(); atoms::released() });
    handle.busy.store(false, Ordering::Release);
    result.map_err(err)
}
