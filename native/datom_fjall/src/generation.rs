//! Process custody for a prepared application generation. Claims are actual
//! app/root/store directory flocks, retained by every opened native handle.
//! Foundry's actual root-owned journal grants writes after candidate readiness.
//! A copied receipt or caller flag never supplies that decision.
use super::{directory::{Directory, DirectoryHandle, Reader}, err, sealing::{Custody, relative}};
use rustler::{Binary, NifResult, Resource, ResourceArc};
use std::collections::HashMap;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::os::unix::fs::MetadataExt;
use std::sync::{Arc, Mutex, OnceLock, RwLock, RwLockReadGuard, Weak, atomic::{AtomicBool, Ordering}};
use serde::Deserialize;

const MARKER: &str = ".bl-generation";
const LIMIT: usize = 1048576;
fn failure(message: &'static str) -> std::io::Error { std::io::Error::other(message) }
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Marker { version: u8, protocol: String, generation: String, ready: String, key_format: u8, data_version: u16 }
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Ready { version: u8, protocol: String, application: String, generation: String, code: String,
               tool: String, destination: String, key_format: u8, data_version: u16 }
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Selection { version: u8, application: String, writer_root: String, root: String, generation: String,
                   ready: String, key_format: u8, data_version: u16, code: String, runtime: String }
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Activation { version: u8, phase: String, journal_revision: u64, writes_admitted: bool,
                    candidate_release_id: String, data_version: u16, data_generation: Selection }
struct Binding { marker: Marker, ready: Ready }
struct Admission { journal: PathBuf, runtime: String, code: String }
pub(crate) struct BlobTier {
    pub(crate) path: PathBuf, pub(crate) parts: Vec<String>,
    pub(crate) directory: Mutex<Option<Arc<Directory>>>,
}
pub(crate) struct WriteGuard<'a> { owner: &'a Owner, _admission: RwLockReadGuard<'a, Option<Admission>> }
impl WriteGuard<'_> {
    pub(crate) fn directory(&self, directory: &Directory) -> std::io::Result<()> {
        self.owner.check()?; directory.check()?;
        if !Arc::ptr_eq(&directory.root, &self.owner.root.root) || directory.readonly()
            || directory.root.sealed.lock().map_err(|_| failure("generation seal poisoned"))?.is_some() {
            return Err(failure("directory outside admitted generation"));
        }
        Ok(())
    }
}
fn bounded_json<T: serde::de::DeserializeOwned>(reader: &mut Reader, limit: usize) -> std::io::Result<T> {
    if reader.len() == 0 || reader.len() > limit as u64 { return Err(failure("generation metadata byte bound")); }
    let mut raw = Vec::with_capacity(reader.len() as usize);
    loop { let part = reader.read(65536)?; if part.is_empty() { break; } raw.extend_from_slice(&part); }
    serde_json::from_slice(&raw).map_err(|_| failure("invalid generation metadata"))
}
fn digest(value: &str) -> bool { value.len() == 64 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)) }
fn trusted_file(reader: &Reader) -> std::io::Result<()> {
    let metadata = reader.metadata();
    if metadata.uid() != 0 || metadata.mode() & 0o022 != 0 { return Err(failure("journal and protocol files must be root-owned and protected")); }
    reader.check()
}
fn trusted_directory(path: &Path, leaf_writable: bool) -> std::io::Result<()> {
    for (index, ancestor) in path.ancestors().enumerate() {
        let metadata = fs::symlink_metadata(ancestor)?;
        let writable = metadata.mode() & 0o022 != 0;
        if !metadata.is_dir() || metadata.uid() != 0 || (writable && metadata.mode() & 0o1000 == 0)
            || (index == 0 && writable && (!leaf_writable || metadata.mode() & 0o002 != 0)) {
            return Err(failure("generation authority needs protected root-owned ancestry"));
        }
    }
    Ok(())
}
fn registry() -> &'static Mutex<HashMap<PathBuf, Weak<Owner>>> {
    static OWNERS: OnceLock<Mutex<HashMap<PathBuf, Weak<Owner>>>> = OnceLock::new();
    OWNERS.get_or_init(|| Mutex::new(HashMap::new()))
}
pub(crate) struct Owner {
    pub(crate) root: Arc<Directory>, app: Arc<Directory>, marker: Reader, ready: Reader,
    stores: HashMap<PathBuf, Arc<Directory>>, closed: AtomicBool,
    pub(crate) blobs: HashMap<PathBuf, Arc<BlobTier>>,
    binding: Binding, admission: RwLock<Option<Admission>>,
    // Store locks drop before either root's explicit custody pin.
    _root_custody: Custody, _app_custody: Custody,
}
impl Owner {
    pub(crate) fn check(&self) -> std::io::Result<()> {
        if self.closed.load(Ordering::Acquire) { return Err(failure("generation owner closed")); }
        self.root.check()?; self.app.check()?; self.marker.check()?; self.ready.check()
    }
    pub(crate) fn store_lock(&self, path: &Path) -> std::io::Result<File> {
        self.check()?;
        let directory = self.stores.get(path).ok_or_else(|| failure("store outside generation inventory"))?;
        directory.check()?; directory.file.try_clone()
    }
    pub(crate) fn write_guard(&self) -> std::io::Result<WriteGuard<'_>> {
        let admission = self.admission.read().map_err(|_| failure("generation admission poisoned"))?;
        self.check()?;
        if admission.is_none() { return Err(failure("generation has no durable write admission")); }
        Ok(WriteGuard { owner: self, _admission: admission })
    }
    pub(crate) fn writable(&self) -> std::io::Result<bool> {
        self.check()?;
        Ok(self.admission.read().map_err(|_| failure("generation admission poisoned"))?.is_some())
    }
}
struct OwnerHandle(Mutex<Option<Arc<Owner>>>);
#[rustler::resource_impl]
impl Resource for OwnerHandle {}

/// Find protection through the nearest existing canonical ancestor, BEFORE
/// creation. A symlink or a nonexistent descendant cannot escape enrollment.
fn enrolled(path: &Path) -> std::io::Result<Option<PathBuf>> {
    let absolute = if path.is_absolute() { path.to_path_buf() } else { std::env::current_dir()?.join(path) };
    let owners = registry().lock().map_err(|_| failure("generation registry poisoned"))?;
    // Known owners also protect missing markers and paths redirected OUT of
    // the generation. This common path needs no ancestor metadata probes.
    for ancestor in absolute.ancestors() {
        if owners.get(ancestor).is_some_and(|owner| owner.strong_count() != 0) {
            return Ok(Some(ancestor.into()));
        }
    }
    let mut existing = absolute.clone();
    loop {
        match fs::symlink_metadata(&existing) {
            Ok(_) => break,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                if !existing.pop() { return Err(failure("generation path has no existing ancestor")); }
            }
            Err(e) => return Err(e),
        }
    }
    let canonical = fs::canonicalize(&existing)?;
    let alias = canonical != existing;
    // Metadata writes pass an existing FILE, not just store directories. A
    // protection marker belongs to its parent; probing file/.bl-generation
    // would return ENOTDIR and incorrectly refuse every journal replacement.
    let canonical = if fs::symlink_metadata(&canonical)?.is_dir() { canonical }
        else { canonical.parent().ok_or_else(|| failure("generation file has no parent"))?.to_path_buf() };
    for ancestor in canonical.ancestors() {
        if owners.get(ancestor).is_some_and(|owner| owner.strong_count() != 0) {
            return Ok(Some(ancestor.into()));
        }
        match fs::symlink_metadata(ancestor.join(MARKER)) {
            Ok(_) => return Ok(Some(ancestor.into())),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e),
        }
    }
    // An unowned marked root still protects its lexical descendants when a
    // link points outside. Ordinary canonical paths pay no second walk.
    if alias {
        for ancestor in absolute.ancestors() {
            match fs::symlink_metadata(ancestor.join(MARKER)) {
                Ok(_) => return Ok(Some(fs::canonicalize(ancestor)?)),
                Err(e) if matches!(e.kind(), std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory) => (),
                Err(e) => return Err(e),
            }
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
    // Generic filesystem calls do not borrow an owned store/blob writer. Even
    // after admission they must not edit protocol files or evade inventory.
    if access(path)?.is_some() { return Err(failure("generation requires an owned writer capability")); }
    Ok(())
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_claim(app: ResourceArc<DirectoryHandle>, root: ResourceArc<DirectoryHandle>,
                          expected: Binary, expected_ready: Binary, paths: Vec<String>, blob_paths: Vec<String>) -> NifResult<ResourceArc<OwnerHandle>> {
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
    if expected.is_empty() || expected.len() > LIMIT || expected_ready.is_empty() || expected_ready.len() > 16 * LIMIT
        || paths.is_empty() || paths.len() > 256
        || blob_paths.len() != paths.len() {
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
    let descriptor: Marker = serde_json::from_slice(expected.as_slice()).map_err(err)?;
    let mut ready_reader = root.0.open_file("READY.json").map_err(err)?;
    if ready_reader.len() != expected_ready.len() as u64 { return Err(err("generation READY length differs")); }
    let mut offset = 0;
    loop {
        let part = ready_reader.read(65536).map_err(err)?;
        if part != expected_ready.as_slice()[offset..offset + part.len()] { return Err(err("generation READY changed")); }
        offset += part.len(); if part.is_empty() { break; }
    }
    let ready: Ready = serde_json::from_slice(expected_ready.as_slice()).map_err(err)?;
    if descriptor.version != 1 || descriptor.protocol != "datom-generation-v1" || descriptor.key_format != 2
        || descriptor.data_version == 0 || !digest(&descriptor.generation) || !digest(&descriptor.ready)
        || ready.version != 1 || ready.protocol != "datom-offline-root-v1" || ready.key_format != 2
        || ready.data_version != descriptor.data_version || ready.generation != descriptor.generation
        || ready.destination != root.0.path.to_string_lossy() || !digest(&ready.code) || !digest(&ready.tool) {
        return Err(err("invalid prepared generation binding"));
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
    let mut blobs: HashMap<PathBuf, Arc<BlobTier>> = HashMap::new();
    for path in blob_paths {
        let parts: Vec<String> = relative(&path).map_err(err)?.into_iter().map(str::to_owned).collect();
        let full = root.0.path.join(path);
        if stores.keys().chain(blobs.keys()).any(|old| full.starts_with(old) || old.starts_with(&full)) {
            return Err(err("generation blob inventory overlaps"));
        }
        let mut current = Some(root.0.clone());
        for part in &parts {
            current = match current.unwrap().child(part, false, false) {
                Ok(value) => Some(value),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
                Err(e) => return Err(err(e)),
            };
            if current.is_none() { break; }
        }
        blobs.insert(full.clone(), Arc::new(BlobTier { path: full, parts, directory: Mutex::new(current) }));
    }
    marker.check().map_err(err)?;
    let mut owners = registry().lock().map_err(err)?;
    owners.retain(|_, owner| owner.strong_count() != 0);
    if owners.get(&root.0.path).and_then(Weak::upgrade).is_some() {
        return Err(err("generation already has an owner"));
    }
    app.0.root.pins.fetch_add(1, Ordering::AcqRel);
    root.0.root.pins.fetch_add(1, Ordering::AcqRel);
    let owner = Arc::new(Owner { root: root.0.clone(), app: app.0.clone(), marker, ready: ready_reader, stores, blobs,
        binding: Binding { marker: descriptor, ready }, admission: RwLock::new(None),
        closed: AtomicBool::new(false), _root_custody: Custody(root.0.root.clone()),
        _app_custody: Custody(app.0.root.clone()) });
    owners.insert(root.0.path.clone(), Arc::downgrade(&owner));
    Ok(ResourceArc::new(OwnerHandle(Mutex::new(Some(owner)))))
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_admit(handle: ResourceArc<OwnerHandle>, journal: ResourceArc<DirectoryHandle>, runtime: String) -> NifResult<bool> {
    let owner = handle.0.lock().map_err(err)?.clone().ok_or_else(|| err("generation owner closed"))?;
    owner.check().map_err(err)?; journal.0.check().map_err(err)?;
    // The fixed writer directory determines the ONE journal authority. A
    // stale root-owned journal copied elsewhere is never interchangeable.
    if owner.app.path.file_name().and_then(|p| p.to_str()) != Some("writer")
        || owner.app.path.parent() != Some(journal.0.path.as_path())
        || journal.0.path != journal.0.root.path || !digest(&runtime) {
        return Err(err("generation journal authority mismatch"));
    }
    trusted_directory(&journal.0.path, false).map_err(err)?;
    trusted_directory(&owner.app.path, false).map_err(err)?;
    trusted_directory(&owner.root.path, true).map_err(err)?;
    trusted_file(&owner.marker).map_err(err)?;
    let mut ready = owner.root.open_file("READY.json").map_err(err)?;
    trusted_file(&ready).map_err(err)?;
    let current: Ready = bounded_json(&mut ready, 16 * LIMIT).map_err(err)?;
    let mut reader = journal.0.open_file("activation.json").map_err(err)?;
    trusted_file(&reader).map_err(err)?;
    let record: Activation = bounded_json(&mut reader, LIMIT).map_err(err)?;
    let selected = &record.data_generation;
    let bound = &owner.binding;
    if record.version != 1 || record.journal_revision == 0 || record.journal_revision > i64::MAX as u64
        || !matches!(record.phase.as_str(), "write-admitted" | "verified") || !record.writes_admitted
        || selected.version != 1 || selected.application != bound.ready.application
        || selected.writer_root != owner.app.path.to_string_lossy() || selected.root != owner.root.path.to_string_lossy()
        || selected.generation != bound.marker.generation || selected.ready != bound.marker.ready
        || selected.key_format != bound.marker.key_format || selected.data_version != bound.marker.data_version
        || record.data_version != selected.data_version || selected.code != bound.ready.code
        || record.candidate_release_id != selected.code || selected.runtime != runtime || runtime != bound.ready.tool
        || current.code != bound.ready.code || current.tool != bound.ready.tool
        || current.generation != bound.marker.generation || current.application != bound.ready.application {
        return Err(err("journal does not durably admit this generation/code/runtime"));
    }
    // Repeat the actual file+directory flush before publishing the in-memory
    // grant, including reconciliation of a lost host reply. No flag can skip it.
    reader.sync().map_err(err)?; journal.0.file.sync_all().map_err(err)?;
    ready.check().map_err(err)?; owner.check().map_err(err)?; journal.0.check().map_err(err)?;
    let mut admission = owner.admission.write().map_err(err)?;
    if let Some(previous) = &*admission {
        if previous.journal != journal.0.path || previous.runtime != runtime || previous.code != selected.code {
            return Err(err("generation admission already bound elsewhere"));
        }
    } else { *admission = Some(Admission { journal: journal.0.path.clone(), runtime, code: selected.code.clone() }); }
    Ok(true)
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
