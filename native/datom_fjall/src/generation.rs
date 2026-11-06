//! Process custody for a prepared application generation. Claims are actual
//! app/root/store directory flocks, retained by every opened native handle.
//! Foundry's actual root-owned journal grants writes after candidate readiness.
//! A copied receipt or caller flag never supplies that decision.
use super::{directory::{Directory, DirectoryHandle, Reader}, err, sealing::{Custody, relative}};
use rustler::{Binary, NifResult, Resource, ResourceArc};
use std::collections::HashMap;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::os::unix::fs::MetadataExt;
use std::sync::{Arc, Mutex, OnceLock, RwLock, RwLockReadGuard, Weak, atomic::{AtomicBool, Ordering}};
use serde::{Deserialize, Serialize};

const MARKER: &str = ".bl-generation";
const LIMIT: usize = 1048576;
pub(crate) const CREATE_MARKER: &str = ".bl-datom-create";
const CREATE_PENDING: &str = ".bl-datom-create.pending";
const CREATE_BYTES: &[u8] = b"datom-generation-new-store-v1\n";
fn failure(message: &'static str) -> std::io::Error { std::io::Error::other(message) }
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Marker { version: u8, protocol: String, generation: String, ready: String, key_format: u8, data_version: u16 }
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Ready { version: u8, protocol: String, application: String, generation: String, code: String,
               tool: String, destination: String, key_format: u8, data_version: u16, storage: Storage }
#[derive(Deserialize)]
struct Storage { files: Vec<String>, directories: Vec<String> }
#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Selection { version: u8, application: String, writer_root: String, root: String, generation: String,
                   ready: String, key_format: u8, data_version: u16, code: String, runtime: String,
                   #[serde(default, deserialize_with = "capability", skip_serializing_if = "Option::is_none")] dynamic_stores: Option<u8> }
// Absence is the legacy closed inventory; explicit null is not a capability.
fn capability<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<Option<u8>, D::Error> {
    u8::deserialize(deserializer).map(Some)
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Activation { version: u8, phase: String, journal_revision: u64, writes_admitted: bool,
                    candidate_release_id: String, data_version: u16, data_generation: Selection }
struct Binding { marker: Marker, ready: Ready }
struct Admission { journal: PathBuf, runtime: String, code: String }
#[derive(Clone, PartialEq)]
struct Cohort { code: String, runtime: String, dynamic_stores: Option<u8> }
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
    reserved: Vec<PathBuf>, binding: Binding, cohort: RwLock<Option<Cohort>>, admission: RwLock<Option<Admission>>,
    // Store locks drop before either root's explicit custody pin.
    _root_custody: Custody, _app_custody: Custody,
}
impl Owner {
    pub(crate) fn check(&self) -> std::io::Result<()> {
        if self.closed.load(Ordering::Acquire) { return Err(failure("generation owner closed")); }
        self.root.check()?; self.app.check()?; self.marker.check()?; self.ready.check()
    }
    fn dynamic_enabled(&self) -> std::io::Result<bool> {
        self.check()?;
        Ok(self.cohort.read().map_err(|_| failure("generation cohort poisoned"))?
            .as_ref().is_some_and(|cohort| cohort.dynamic_stores == Some(1)))
    }
    fn dynamic_parts<'a>(&self, path: &'a Path) -> std::io::Result<Vec<&'a str>> {
        if !self.dynamic_enabled()? { return Err(failure("store outside generation inventory")); }
        let relative_path = path.strip_prefix(&self.root.path).map_err(|_| failure("dynamic store outside generation"))?;
        let parts = relative(relative_path.to_str().ok_or_else(|| failure("invalid dynamic store name"))?)?;
        if parts.len() > 16 || parts.iter().any(|part| part.starts_with('.'))
            || parts[..parts.len() - 1].iter().any(|part| part.ends_with(".fjall") || part.ends_with(".blobs"))
            || !parts.last().is_some_and(|name| name.len() > 6 && name.ends_with(".fjall")) {
            return Err(failure("unsupported dynamic store namespace"));
        }
        let blob = PathBuf::from(format!("{}.blobs", path.to_string_lossy()));
        for existing in self.stores.keys().chain(self.blobs.keys()).chain(self.reserved.iter()) {
            if [path, blob.as_path()].iter().any(|new| new.starts_with(existing) || existing.starts_with(new)) {
                return Err(failure("dynamic store overlaps declared inventory"));
            }
        }
        Ok(parts)
    }
    pub(crate) fn canonical_store(&self, path: &Path) -> std::io::Result<PathBuf> {
        self.check()?;
        if let Ok(canonical) = fs::canonicalize(path) {
            if let Some(directory) = self.stores.get(&canonical) {
                directory.check()?; return Ok(canonical);
            }
        }
        let absolute = if path.is_absolute() { path.to_path_buf() } else { std::env::current_dir()?.join(path) };
        let parts = self.dynamic_parts(&absolute)?;
        let mut directory = self.root.clone();
        for part in parts {
            directory = match directory.child(part, false, false) {
                Ok(value) => value,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    let permit = self.write_guard()?;
                    directory.owned_child(part, &permit)?
                }
                Err(error) => return Err(error),
            };
        }
        Ok(directory.path.clone())
    }
    pub(crate) fn store_directory(&self, path: &Path) -> std::io::Result<(Arc<Directory>, bool, bool)> {
        self.check()?;
        if let Some(directory) = self.stores.get(path) {
            directory.check()?; return Ok((directory.clone(), false, false));
        }
        let parts = self.dynamic_parts(path)?;
        let mut directory = self.root.clone();
        for (index, part) in parts.iter().enumerate() {
            directory = directory.child(part, false, index + 1 == parts.len())?;
        }
        let mut entries = fs::read_dir(super::directory::pinned(&directory.file, "."))?;
        let first = entries.next().transpose()?;
        let empty = first.is_none();
        let only_pending = first.as_ref().is_some_and(|entry| entry.file_name() == CREATE_PENDING)
            && entries.next().transpose()?.is_none();
        let creating = if empty || only_pending {
            let permit = self.write_guard()?;
            permit.directory(&directory)?;
            if only_pending {
                // This exact name is reserved for UNPUBLISHED creation, and
                // there is no engine or other entry to relabel/delete. A
                // crashed writer may leave zero or partial staging bytes.
                let pending = directory.open_file(CREATE_PENDING)?;
                if pending.metadata().uid() != unsafe { libc::geteuid() }
                    || pending.metadata().mode() & 0o077 != 0 {
                    return Err(failure("untrusted pending store creation"));
                }
                pending.check()?;
                fs::remove_file(super::directory::pinned(&directory.file, CREATE_PENDING))?;
                directory.file.sync_all()?;
            }
            let mut marker = OpenOptions::new().write(true).create_new(true).mode(0o600)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(super::directory::pinned(&directory.file, CREATE_PENDING))?;
            marker.write_all(CREATE_BYTES)?; marker.sync_all()?;
            super::directory::rename_anchored(&directory, CREATE_PENDING, CREATE_MARKER, true)?;
            true
        } else {
            match directory.open_file(CREATE_MARKER) {
                Ok(mut marker) => {
                    self.write_guard()?;
                    if marker.len() != CREATE_BYTES.len() as u64 || marker.read(CREATE_BYTES.len())? != CREATE_BYTES {
                        return Err(failure("unsupported pending store creation"));
                    }
                    match directory.open_file("version") {
                        Ok(mut version) => {
                            if version.len() != 4 || version.read(4)? != b"FJL\x02" {
                                return Err(failure("unsupported pending physical engine version"));
                            }
                        }
                        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                        Err(error) => return Err(error),
                    }
                    true
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    super::require_existing_engine(path)?; false
                }
                Err(error) => return Err(error),
            }
        };
        Ok((directory, true, creating))
    }
    pub(crate) fn blob_tier(&self, path: &Path) -> std::io::Result<Arc<BlobTier>> {
        self.check()?;
        if let Some(tier) = self.blobs.get(path) { return Ok(tier.clone()); }
        let text = path.to_str().ok_or_else(|| failure("invalid dynamic blob path"))?;
        let store = Path::new(text.strip_suffix(".blobs").ok_or_else(|| failure("unsupported dynamic blob sibling"))?);
        self.dynamic_parts(store)?;
        // No registry file and no startup traversal: only the requested engine
        // is checked. The whole-app owner excludes other generation writers.
        super::require_existing_engine(store)?;
        let parts = relative(path.strip_prefix(&self.root.path).map_err(|_| failure("blob outside generation"))?
            .to_str().ok_or_else(|| failure("invalid dynamic blob path"))?)?.into_iter().map(str::to_owned).collect();
        Ok(Arc::new(BlobTier { path: path.into(), parts, directory: Mutex::new(None) }))
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
    let reserved = ready.storage.files.iter().chain(ready.storage.directories.iter()).map(|path| {
        relative(path).map(|_| root.0.path.join(path))
    }).collect::<std::io::Result<Vec<_>>>().map_err(err)?;
    app.0.root.pins.fetch_add(1, Ordering::AcqRel);
    root.0.root.pins.fetch_add(1, Ordering::AcqRel);
    let owner = Arc::new(Owner { root: root.0.clone(), app: app.0.clone(), marker, ready: ready_reader, stores, blobs, reserved,
        binding: Binding { marker: descriptor, ready }, cohort: RwLock::new(None), admission: RwLock::new(None),
        closed: AtomicBool::new(false), _root_custody: Custody(root.0.root.clone()),
        _app_custody: Custody(app.0.root.clone()) });
    owners.insert(root.0.path.clone(), Arc::downgrade(&owner));
    Ok(ResourceArc::new(OwnerHandle(Mutex::new(Some(owner)))))
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Observation { version: u8, data_generation: Selection, writes_admitted: bool }

/// Observation comes from the retained native claims, never an Owner record's
/// copied paths/flags. It grants no authority and keeps the owner alive while
/// checking protocol files and the actual native admission latch.
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_status(handle: ResourceArc<OwnerHandle>) -> NifResult<String> {
    let owner = handle.0.lock().map_err(err)?.clone().ok_or_else(|| err("generation owner closed"))?;
    owner.check().map_err(err)?;
    trusted_directory(&owner.app.path, false).map_err(err)?;
    trusted_directory(&owner.root.path, true).map_err(err)?;
    trusted_file(&owner.marker).map_err(err)?; trusted_file(&owner.ready).map_err(err)?;
    let bound = &owner.binding;
    let cohort = owner.cohort.read().map_err(err)?;
    let observed = Observation { version: 1, writes_admitted: owner.writable().map_err(err)?,
        data_generation: Selection { version: 1, application: bound.ready.application.clone(),
            writer_root: owner.app.path.to_string_lossy().into_owned(), root: owner.root.path.to_string_lossy().into_owned(),
            generation: bound.marker.generation.clone(), ready: bound.marker.ready.clone(),
            key_format: bound.marker.key_format, data_version: bound.marker.data_version,
            code: cohort.as_ref().map_or_else(|| bound.ready.code.clone(), |c| c.code.clone()),
            runtime: cohort.as_ref().map_or_else(|| bound.ready.tool.clone(), |c| c.runtime.clone()),
            dynamic_stores: cohort.as_ref().and_then(|c| c.dynamic_stores) } };
    serde_json::to_string(&observed).map_err(err)
}

fn selected_activation(owner: &Owner, journal: &Arc<Directory>) -> NifResult<(Activation, Reader)> {
    owner.check().map_err(err)?; journal.check().map_err(err)?;
    // The fixed writer directory determines the ONE journal authority. A
    // stale root-owned journal copied elsewhere is never interchangeable.
    if owner.app.path.file_name().and_then(|p| p.to_str()) != Some("writer")
        || owner.app.path.parent() != Some(journal.path.as_path())
        || journal.path != journal.root.path {
        return Err(err("generation journal authority mismatch"));
    }
    trusted_directory(&journal.path, false).map_err(err)?;
    trusted_directory(&owner.app.path, false).map_err(err)?;
    trusted_directory(&owner.root.path, true).map_err(err)?;
    trusted_file(&owner.marker).map_err(err)?;
    let mut ready = owner.root.open_file("READY.json").map_err(err)?;
    trusted_file(&ready).map_err(err)?;
    let current: Ready = bounded_json(&mut ready, 16 * LIMIT).map_err(err)?;
    let mut reader = journal.open_file("activation.json").map_err(err)?;
    trusted_file(&reader).map_err(err)?;
    let record: Activation = bounded_json(&mut reader, LIMIT).map_err(err)?;
    let selected = &record.data_generation;
    let bound = &owner.binding;
    if record.version != 1 || record.journal_revision == 0 || record.journal_revision > i64::MAX as u64
        || !matches!(record.phase.as_str(), "starting" | "read-only-ready" | "write-admitted" | "verified")
        || selected.version != 1 || selected.application != bound.ready.application
        || selected.writer_root != owner.app.path.to_string_lossy() || selected.root != owner.root.path.to_string_lossy()
        || selected.generation != bound.marker.generation || selected.ready != bound.marker.ready
        || selected.key_format != bound.marker.key_format || selected.data_version != bound.marker.data_version
        || record.data_version != selected.data_version
        || record.candidate_release_id != selected.code || !digest(&selected.code) || !digest(&selected.runtime)
        || selected.dynamic_stores.is_some_and(|version| version != 1)
        || current.code != bound.ready.code || current.tool != bound.ready.tool
        || current.generation != bound.marker.generation || current.application != bound.ready.application {
        return Err(err("journal does not durably admit this generation/code/runtime"));
    }
    Ok((record, reader))
}

/// Pin the executing cohort from the ONE protected activation journal. READY
/// remains immutable birth evidence; it does not pin every future compatible
/// application/runtime to the converter's original code. No write grant here.
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_select(handle: ResourceArc<OwnerHandle>, journal: ResourceArc<DirectoryHandle>, runtime: String) -> NifResult<bool> {
    let owner = handle.0.lock().map_err(err)?.clone().ok_or_else(|| err("generation owner closed"))?;
    let (record, reader) = selected_activation(&owner, &journal.0)?;
    if !digest(&runtime) || record.data_generation.runtime != runtime {
        return Err(err("selected generation requires another runtime cohort"));
    }
    let selected = Cohort { code: record.data_generation.code, runtime, dynamic_stores: record.data_generation.dynamic_stores };
    let mut cohort = owner.cohort.write().map_err(err)?;
    if cohort.as_ref().is_some_and(|old| old != &selected) {
        return Err(err("generation owner cohort is already pinned"));
    }
    if owner.admission.read().map_err(err)?.as_ref().is_some_and(|old| old.code != selected.code || old.runtime != selected.runtime) {
        return Err(err("admitted generation cannot change its running cohort"));
    }
    reader.check().map_err(err)?; owner.check().map_err(err)?;
    *cohort = Some(selected);
    Ok(true)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_admit(handle: ResourceArc<OwnerHandle>, journal: ResourceArc<DirectoryHandle>, runtime: String) -> NifResult<bool> {
    let owner = handle.0.lock().map_err(err)?.clone().ok_or_else(|| err("generation owner closed"))?;
    let (record, reader) = selected_activation(&owner, &journal.0)?;
    let selected = &record.data_generation;
    let cohort = owner.cohort.read().map_err(err)?;
    let code = cohort.as_ref().map_or(&owner.binding.ready.code, |c| &c.code);
    let expected_runtime = cohort.as_ref().map_or(&owner.binding.ready.tool, |c| &c.runtime);
    if !matches!(record.phase.as_str(), "write-admitted" | "verified") || !record.writes_admitted
        || &selected.code != code || &selected.runtime != expected_runtime || selected.runtime != runtime
        || selected.dynamic_stores != cohort.as_ref().and_then(|c| c.dynamic_stores) {
        return Err(err("journal does not durably admit this pinned generation/code/runtime"));
    }
    // Repeat the actual file+directory flush before publishing the in-memory
    // grant, including reconciliation of a lost host reply. No flag can skip it.
    reader.sync().map_err(err)?; journal.0.file.sync_all().map_err(err)?;
    owner.check().map_err(err)?; journal.0.check().map_err(err)?;
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
