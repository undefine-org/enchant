//! Directory capabilities used by offline preparation. All traversal is relative
//! to pinned fds; source capabilities cannot create or replace anything. This
//! module never opens a Fjall engine. Root/manifest policy belongs to the caller.
use super::{err, to_binary};
use rustler::{Binary, Encoder, Env, NifResult, Resource, ResourceArc, Term};
use std::ffi::CString;
use std::collections::HashSet;
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::{fs::{MetadataExt, OpenOptionsExt, DirBuilderExt}};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering}};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(1);
const MAX_META: usize = 16 * 1024 * 1024;
const TEMP_PREFIX: &str = ".bl-copy-";

fn failure(message: &'static str) -> std::io::Error { std::io::Error::other(message) }
pub(crate) fn name(value: &str) -> std::io::Result<CString> {
    if value.is_empty() || value == "." || value == ".." || value.contains('/') || value.len() > 255 {
        return Err(failure("invalid directory entry name"));
    }
    CString::new(value).map_err(|_| failure("invalid directory entry name"))
}
pub(crate) fn identity(a: &Metadata, b: &Metadata) -> bool {
    a.dev() == b.dev() && a.ino() == b.ino() && a.file_type() == b.file_type()
}
pub(crate) fn unchanged(a: &Metadata, b: &Metadata) -> bool {
    identity(a,b) && a.len() == b.len() && a.mtime() == b.mtime() && a.mtime_nsec() == b.mtime_nsec()
        && a.ctime() == b.ctime() && a.ctime_nsec() == b.ctime_nsec()
}
pub(crate) fn open_at(parent: &File, child: &str, flags: i32, mode: u32) -> std::io::Result<File> {
    let child = name(child)?;
    let fd = unsafe { libc::openat(parent.as_raw_fd(), child.as_ptr(),
        flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK, mode) };
    if fd < 0 { Err(std::io::Error::last_os_error()) } else { Ok(unsafe { File::from_raw_fd(fd) }) }
}
pub(crate) fn pinned(parent: &File, child: &str) -> PathBuf {
    PathBuf::from(format!("/proc/self/fd/{}", parent.as_raw_fd())).join(child)
}
pub(crate) struct Root {
    pub(crate) file: File, pub(crate) path: PathBuf, metadata: Metadata,
    readonly: bool, closed: AtomicBool, pub(crate) write: Mutex<()>,
    pub(crate) sealed: Mutex<Option<PathBuf>>,
    pub(crate) engines: Mutex<HashSet<PathBuf>>,
    pub(crate) pins: AtomicUsize,
}
impl Root {
    pub(crate) fn check(&self) -> std::io::Result<()> {
        if self.closed.load(Ordering::Acquire) { return Err(failure("directory claim closed")); }
        let observed = fs::symlink_metadata(&self.path)?;
        if !identity(&self.metadata, &observed) || (self.readonly && !unchanged(&self.metadata, &observed)) {
            return Err(failure("directory claim identity or sealed namespace changed"));
        }
        Ok(())
    }
}
pub(crate) struct Directory {
    pub(crate) file: File, pub(crate) path: PathBuf, pub(crate) metadata: Metadata, pub(crate) root: Arc<Root>,
    // Keep parent directory identity and optional child flock alive.
    parent: Option<Arc<Directory>>,
}
impl Directory {
    pub(crate) fn check(&self) -> std::io::Result<()> {
        self.root.check()?;
        if let Some(parent) = &self.parent { parent.check()?; }
        let observed = fs::symlink_metadata(&self.path)?;
        if !identity(&self.metadata, &observed) || (self.root.readonly && !unchanged(&self.metadata, &observed)) {
            return Err(failure("directory entry identity or sealed namespace changed"));
        }
        Ok(())
    }
    pub(crate) fn readonly(&self) -> bool { self.root.readonly }
    pub(crate) fn writable(&self) -> std::io::Result<()> {
        self.check()?;
        self.writable_path(&self.path)
    }
    fn writable_path(&self, path: &Path) -> std::io::Result<()> {
        if self.root.readonly { return Err(failure("sealed source is read-only")); }
        let sealed = self.root.sealed.lock().map_err(|_| failure("sealed target lock poisoned"))?;
        if sealed.as_ref().is_some_and(|frozen| path.starts_with(frozen)) {
            return Err(failure("offline target is sealed"));
        }
        super::generation::check_write(path)?;
        Ok(())
    }
    pub(crate) fn child(self: &Arc<Self>, child: &str, create: bool, lock: bool) -> std::io::Result<Arc<Self>> {
        self.check()?; let cname = name(child)?;
        if create {
            self.writable()?; self.writable_path(&self.path.join(child))?;
            let result = unsafe { libc::mkdirat(self.file.as_raw_fd(), cname.as_ptr(), 0o700) };
            if result < 0 && std::io::Error::last_os_error().kind() != std::io::ErrorKind::AlreadyExists {
                return Err(std::io::Error::last_os_error());
            }
        }
        let file = open_at(&self.file, child, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        let metadata = file.metadata()?;
        if !metadata.is_dir() || !identity(&metadata, &fs::symlink_metadata(pinned(&self.file, child))?) {
            return Err(failure("child directory identity changed"));
        }
        if lock { file.try_lock().map_err(std::io::Error::other)?; }
        self.check()?;
        if create { self.file.sync_all()?; }
        Ok(Arc::new(Self { file, path: self.path.join(child), metadata,
            root: self.root.clone(), parent: Some(self.clone()) }))
    }
    pub(crate) fn open_file(self: &Arc<Self>, child: &str) -> std::io::Result<Reader> {
        self.check()?;
        let file = open_at(&self.file, child, libc::O_RDONLY, 0)?;
        let metadata = file.metadata()?;
        if !metadata.is_file() || metadata.nlink() != 1
            || !identity(&metadata, &fs::symlink_metadata(pinned(&self.file, child))?) {
            return Err(failure("source must be an unaliased regular file"));
        }
        Ok(Reader { parent: self.clone(), name: child.into(), metadata, file, offset: 0 })
    }
    pub(crate) fn owned_child(self: &Arc<Self>, child: &str, permit: &super::generation::WriteGuard<'_>)
        -> std::io::Result<Arc<Self>> {
        permit.directory(self)?; let cname = name(child)?;
        let result = unsafe { libc::mkdirat(self.file.as_raw_fd(), cname.as_ptr(), 0o700) };
        if result < 0 && std::io::Error::last_os_error().kind() != std::io::ErrorKind::AlreadyExists {
            return Err(std::io::Error::last_os_error());
        }
        let directory = self.child(child, false, false)?;
        self.file.sync_all()?; permit.directory(self)?;
        Ok(directory)
    }
}
pub(crate) struct DirectoryHandle(pub(crate) Arc<Directory>);
#[rustler::resource_impl]
impl Resource for DirectoryHandle {}

/// A private job capability is minted only from its already claimed directory
/// and an exact durable marker. A path or a copied BL record cannot mint it.
pub(crate) struct OfflineScope {
    pub(crate) directory: Arc<Directory>, pub(crate) marker: Reader,
    pub(crate) source: Mutex<Option<Arc<super::source::Original>>>,
}
#[rustler::resource_impl]
impl Resource for OfflineScope {}

pub(crate) struct OfflineAccess {
    scope: ResourceArc<OfflineScope>, directory: Arc<Directory>, readonly: bool,
    // An aborted caller may detach Scope.source, but accepted engine work
    // must retain the actual original claims through its own resource drop.
    _original: Option<Arc<super::source::Original>>,
}
impl OfflineAccess {
    pub(crate) fn readonly(&self) -> bool { self.readonly }
    pub(crate) fn write_guard(&self) -> std::io::Result<std::sync::MutexGuard<'_, ()>> {
        let guard = self.scope.directory.root.write.lock().map_err(|_| failure("offline job writer lock poisoned"))?;
        self.scope.marker.check()?;
        self.directory.writable()?;
        if self.readonly { return Err(failure("offline extraction is logically read-only")); }
        Ok(guard)
    }
    pub(crate) fn check_live(&self) -> std::io::Result<()> {
        if self.scope.directory.root.closed.load(Ordering::Acquire) {
            return Err(failure("offline job claim closed"));
        }
        Ok(())
    }
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_scope(directory: ResourceArc<DirectoryHandle>, expected: Binary)
 -> NifResult<ResourceArc<OfflineScope>> {
    directory.0.writable().map_err(err)?;
    // Never manufacture a conversion escape hatch under an enrolled app root.
    for ancestor in directory.0.path.ancestors() {
        for name in [".bl-generation", ".bl-offline-job"] {
            if name == ".bl-offline-job" && ancestor == directory.0.path { continue; }
            match fs::symlink_metadata(ancestor.join(name)) {
                Ok(_) => return Err(err("offline job overlaps a protected root")),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                Err(e) => return Err(err(e)),
            }
        }
    }
    let mut marker = directory.0.open_file(".bl-offline-job").map_err(err)?;
    if expected.is_empty() || expected.len() > 1048576 || marker.metadata.len() != expected.len() as u64 {
        return Err(err("invalid offline job binding"));
    }
    let bytes = marker.read(1048576).map_err(err)?;
    if bytes != expected.as_slice() { return Err(err("offline job binding mismatch")); }
    marker.file.sync_all().map_err(err)?;
    directory.0.file.sync_all().map_err(err)?;
    Ok(ResourceArc::new(OfflineScope { directory: directory.0.clone(), marker, source: Mutex::new(None) }))
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_offline_open<'a>(env: Env<'a>, scope: ResourceArc<OfflineScope>, relative: String, create: bool)
 -> NifResult<Term<'a>> {
    let _guard = scope.directory.root.write.lock().map_err(err)?;
    scope.directory.writable().map_err(err)?;
    scope.marker.check().map_err(err)?;
    let parts: Vec<_> = relative.split('/').collect();
    if parts.len() < 2 || parts.len() > 128 || !matches!(parts[0], "extract" | "target" | "scratch") {
        return Err(err("invalid offline store role"));
    }
    let readonly = parts[0] == "extract";
    if readonly && create { return Err(err("cannot initialize an extraction store")); }
    let mut directory = scope.directory.clone();
    for (index, part) in parts.iter().enumerate() {
        if create && index + 1 == parts.len() {
            match fs::symlink_metadata(pinned(&directory.file, part)) {
                Ok(_) => return Err(err("offline new store already exists")),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
                Err(e) => return Err(err(e)),
            }
        }
        directory = directory.child(part, create, false).map_err(err)?;
    }
    directory.writable().map_err(err)?;
    if scope.directory.root.engines.lock().map_err(err)?.len() >= 65536 {
        return Err(err("offline engine inventory bound exceeded"));
    }
    let claim = super::claim_store_mode(&directory.path, !create)
        .map_err(|_| err("offline engine claim or supported reader refused"))?;
    scope.directory.root.engines.lock().map_err(err)?.insert(directory.path.clone());
    let original = scope.source.lock().map_err(err)?.clone();
    let handle = super::DbHandle {
        path: directory.path.clone(), keyspace: claim.engine.keyspace.clone(),
        datoms: claim.engine.datoms.clone(), lock: claim.engine.lock.clone(), _claim: claim,
        _offline: Some(OfflineAccess { scope: scope.clone(), directory, readonly, _original: original }),
    };
    scope.marker.check().map_err(err)?;
    let path = handle.path.to_string_lossy().into_owned();
    Ok((ResourceArc::new(handle), path).encode(env))
}

pub(crate) struct Reader { parent: Arc<Directory>, name: String, metadata: Metadata, file: File, offset: u64 }
impl Reader {
    pub(crate) fn len(&self) -> u64 { self.metadata.len() }
    pub(crate) fn metadata(&self) -> &Metadata { &self.metadata }
    pub(crate) fn sync(&self) -> std::io::Result<()> { self.check()?; self.file.sync_all()?; self.check() }
    pub(crate) fn check(&self) -> std::io::Result<()> {
        self.parent.check()?;
        if !unchanged(&self.metadata, &self.file.metadata()?)
            || !unchanged(&self.metadata, &fs::symlink_metadata(pinned(&self.parent.file, &self.name))?) {
            return Err(failure("file changed while reading"));
        }
        Ok(())
    }
    pub(crate) fn read(&mut self, limit: usize) -> std::io::Result<Vec<u8>> {
        if limit == 0 || limit > 1048576 { return Err(failure("invalid file read byte bound")); }
        self.check()?;
        let n = usize::try_from((self.metadata.len()-self.offset).min(limit as u64)).unwrap();
        let mut bytes = vec![0; n]; self.file.read_exact(&mut bytes)?;
        self.offset += n as u64; self.check()?; Ok(bytes)
    }
}
struct FileHandle(Mutex<Reader>);
#[rustler::resource_impl]
impl Resource for FileHandle {}

fn claim(path: &Path, readonly: bool, create: bool) -> std::io::Result<Arc<Directory>> {
    if !path.is_absolute() { return Err(failure("absolute canonical directory required")); }
    if create {
        super::generation::check_write(path)?;
        let parent = path.parent().ok_or_else(|| failure("directory needs a parent"))?;
        if fs::canonicalize(parent)? != parent { return Err(failure("directory parent is not canonical")); }
        fs::DirBuilder::new().mode(0o700).create(path)?;
    }
    if fs::canonicalize(path)? != path { return Err(failure("directory aliases are not accepted")); }
    let file = OpenOptions::new().read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC).open(path)?;
    let metadata = file.metadata()?;
    if !identity(&metadata, &fs::symlink_metadata(path)?) { return Err(failure("directory identity changed")); }
    file.try_lock().map_err(std::io::Error::other)?;
    let root = Arc::new(Root { file: file.try_clone()?, path: path.into(), metadata: metadata.clone(),
        readonly, closed: AtomicBool::new(false), write: Mutex::new(()),
        sealed: Mutex::new(None), engines: Mutex::new(HashSet::new()), pins: AtomicUsize::new(0) });
    Ok(Arc::new(Directory { file, path: path.into(), metadata, root, parent: None }))
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_open(path: String, readonly: bool, create: bool) -> NifResult<ResourceArc<DirectoryHandle>> {
    if readonly && create { return Err(err("cannot create a sealed source")); }
    Ok(ResourceArc::new(DirectoryHandle(claim(Path::new(&path), readonly, create).map_err(err)?)))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_child(parent: ResourceArc<DirectoryHandle>, name: String, create: bool, lock: bool)
 -> NifResult<ResourceArc<DirectoryHandle>> {
    let _guard = parent.0.root.write.lock().map_err(err)?;
    Ok(ResourceArc::new(DirectoryHandle(parent.0.child(&name, create, lock).map_err(err)?)))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_close(handle: ResourceArc<DirectoryHandle>) -> NifResult<bool> {
    let _write = handle.0.root.write.lock().map_err(err)?;
    if handle.0.root.pins.load(Ordering::Acquire) != 0 {
        return Err(err("sealed or accepted publication still owns this job"));
    }
    let observed = handle.0.check();
    if !handle.0.root.closed.swap(true, Ordering::AcqRel) { handle.0.root.file.unlock().map_err(err)?; }
    observed.map_err(err)?;
    Ok(true)
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_entries<'a>(env: Env<'a>, handle: ResourceArc<DirectoryHandle>, after: Option<String>, limit: usize)
 -> NifResult<Term<'a>> {
    if limit == 0 || limit > 512 { return Err(err("invalid directory page bound")); }
    handle.0.check().map_err(err)?;
    let mut names = Vec::new();
    for entry in fs::read_dir(format!("/proc/self/fd/{}", handle.0.file.as_raw_fd())).map_err(err)? {
        if names.len() >= 65536 { return Err(err("directory entry budget exceeded")); }
        let entry = entry.map_err(err)?;
        let name = entry.file_name().into_string().map_err(|_| err("directory names must be UTF-8"))?;
        let metadata = fs::symlink_metadata(entry.path()).map_err(err)?;
        let kind = if metadata.is_dir() { "directory" } else if metadata.is_file() && metadata.nlink() == 1 { "file" }
            else { return Err(err("unexpected link or special file in captured root")); };
        names.push((name, kind.to_string(), metadata.len()));
    }
    names.sort_by(|a,b| a.0.cmp(&b.0));
    let remaining: Vec<_> = names.into_iter().filter(|row| after.as_ref().map_or(true, |a| row.0 > *a)).collect();
    let done = remaining.len() <= limit;
    let rows: Vec<_> = remaining.into_iter().take(limit).collect();
    let last = rows.last().map(|row| row.0.clone());
    handle.0.check().map_err(err)?;
    Ok((rows, last, done).encode(env))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_file(handle: ResourceArc<DirectoryHandle>, name: String) -> NifResult<ResourceArc<FileHandle>> {
    Ok(ResourceArc::new(FileHandle(Mutex::new(handle.0.open_file(&name).map_err(err)?))))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_read<'a>(env: Env<'a>, handle: ResourceArc<FileHandle>, limit: usize) -> NifResult<Term<'a>> {
    let mut reader = handle.0.lock().map_err(err)?;
    let bytes = reader.read(limit).map_err(err)?;
    Ok((to_binary(env, &bytes)?, reader.offset == reader.metadata.len()).encode(env))
}

pub(crate) struct Temporary<'a> { parent: &'a Directory, pub(crate) name: String }
impl Drop for Temporary<'_> {
    fn drop(&mut self) {
        if let Ok(name) = name(&self.name) { unsafe { libc::unlinkat(self.parent.file.as_raw_fd(), name.as_ptr(), 0); } }
    }
}
pub(crate) fn temporary(parent: &Directory) -> std::io::Result<(File, Temporary<'_>)> {
    loop {
        let name = format!("{}{}-{}", TEMP_PREFIX, std::process::id(), NEXT_TEMP.fetch_add(1, Ordering::Relaxed));
        match open_at(&parent.file, &name, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL, 0o600) {
            Ok(file) => return Ok((file, Temporary { parent, name })),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e),
        }
    }
}
fn rename(parent: &Directory, temporary: &str, target: &str, no_replace: bool) -> std::io::Result<()> {
    parent.writable()?; parent.writable_path(&parent.path.join(target))?;
    rename_anchored(parent, temporary, target, no_replace)
}
fn rename_anchored(parent: &Directory, temporary: &str, target: &str, no_replace: bool) -> std::io::Result<()> {
    parent.check()?;
    let from = name(temporary)?; let to = name(target)?;
    let flags = if no_replace { libc::RENAME_NOREPLACE } else { 0 };
    if unsafe { libc::renameat2(parent.file.as_raw_fd(), from.as_ptr(), parent.file.as_raw_fd(), to.as_ptr(), flags) } < 0 {
        return Err(std::io::Error::last_os_error());
    }
    parent.file.sync_all()?; parent.check()
}

/// Only the sealed publisher can call this. Never unfreeze the data subtree:
/// two fixed metadata names have a separate absent-or-identical write path.
pub(crate) fn put_protocol(parent: &Arc<Directory>, target: &str, value: &[u8]) -> std::io::Result<()> {
    parent.check()?;
    if parent.root.readonly || !matches!(target, "READY.json" | ".bl-generation") || value.len() > MAX_META {
        return Err(failure("invalid sealed protocol publication"));
    }
    match parent.open_file(target) {
        Ok(mut reader) => {
            if reader.metadata.len() != value.len() as u64 { return Err(failure("sealed protocol content differs")); }
            let mut offset = 0;
            loop {
                let part = reader.read(1048576)?;
                if part != value[offset..offset + part.len()] { return Err(failure("sealed protocol content differs")); }
                offset += part.len(); if part.is_empty() { break; }
            }
            reader.file.sync_all()?; parent.file.sync_all()?;
            return parent.check();
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e),
    }
    let (mut file, temp) = temporary(parent)?;
    file.write_all(value)?; file.sync_all()?;
    rename_anchored(parent, &temp.name, target, true)
}
/// Root-owned readers can observe a committed journal without replacing it.
/// Metadata permissions are set on the private inode BEFORE fsync and rename;
/// a crash cannot publish a grant and then lose its permission transition.
fn put_metadata(handle: ResourceArc<DirectoryHandle>, target: String, expected: Option<Binary>, value: Binary,
                read_group: Option<u32>) -> NifResult<bool> {
    if value.len() > MAX_META || expected.as_ref().is_some_and(|v| v.len() > MAX_META) { return Err(err("metadata byte bound exceeded")); }
    let _write = handle.0.root.write.lock().map_err(err)?;
    handle.0.writable().map_err(err)?; name(&target).map_err(err)?;
    handle.0.writable_path(&handle.0.path.join(&target)).map_err(err)?;
    if let Some(gid) = read_group {
        let metadata = handle.0.file.metadata().map_err(err)?;
        if unsafe { libc::geteuid() } != 0 || gid == 0 || gid == u32::MAX || metadata.uid() != 0 || metadata.gid() != gid
            || metadata.mode() & 0o777 != 0o750 {
            return Err(err("shared publication requires a protected root-owned reader-group directory"));
        }
    }
    let old = match handle.0.open_file(&target) {
        Ok(mut reader) => {
            if reader.metadata.len() > MAX_META as u64 { return Err(err("metadata byte bound exceeded")); }
            let mut old = Vec::new();
            loop { let part = reader.read(1048576).map_err(err)?; if part.is_empty() { break; } old.extend_from_slice(&part); }
            Some(old)
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(err(e)),
    };
    if old.as_deref() != expected.as_ref().map(|b| b.as_slice()) { return Ok(false); }
    let (mut file, temp) = temporary(&handle.0).map_err(err)?;
    if let Some(gid) = read_group {
        if unsafe { libc::fchown(file.as_raw_fd(), 0, gid) } < 0
            || unsafe { libc::fchmod(file.as_raw_fd(), 0o640) } < 0 {
            return Err(err(std::io::Error::last_os_error()));
        }
    }
    file.write_all(value.as_slice()).map_err(err)?; file.sync_all().map_err(err)?;
    rename(&handle.0, &temp.name, &target, expected.is_none()).map_err(err)?;
    Ok(true)
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_put(handle: ResourceArc<DirectoryHandle>, target: String, expected: Option<Binary>, value: Binary)
 -> NifResult<bool> { put_metadata(handle, target, expected, value, None) }
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_put_shared(handle: ResourceArc<DirectoryHandle>, target: String, expected: Option<Binary>, value: Binary, gid: u32)
 -> NifResult<bool> { put_metadata(handle, target, expected, value, Some(gid)) }
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_share_read(handle: ResourceArc<DirectoryHandle>, gid: u32) -> NifResult<bool> {
    let _write = handle.0.root.write.lock().map_err(err)?;
    handle.0.writable().map_err(err)?;
    let metadata = handle.0.file.metadata().map_err(err)?;
    if unsafe { libc::geteuid() } != 0 || gid == 0 || gid == u32::MAX || metadata.uid() != 0 {
        return Err(err("only root can configure a protected reader group"));
    }
    if unsafe { libc::fchown(handle.0.file.as_raw_fd(), 0, gid) } < 0
        || unsafe { libc::fchmod(handle.0.file.as_raw_fd(), 0o750) } < 0 {
        return Err(err(std::io::Error::last_os_error()));
    }
    handle.0.file.sync_all().map_err(err)?;
    handle.0.check().map_err(err)?;
    Ok(true)
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_copy(source: ResourceArc<DirectoryHandle>, from: String, destination: ResourceArc<DirectoryHandle>, to: String)
 -> NifResult<bool> {
    let _write = destination.0.root.write.lock().map_err(err)?;
    destination.0.writable().map_err(err)?; name(&to).map_err(err)?;
    destination.0.writable_path(&destination.0.path.join(&to)).map_err(err)?;
    let mut source_file = source.0.open_file(&from).map_err(err)?;
    match destination.0.open_file(&to) {
        Ok(mut existing) => {
            if existing.metadata.len() != source_file.metadata.len() { return Err(err("existing destination differs")); }
            loop {
                let left = source_file.read(1048576).map_err(err)?;
                let right = existing.read(1048576).map_err(err)?;
                if left != right { return Err(err("existing destination differs")); }
                if left.is_empty() { break; }
            }
            existing.file.sync_all().map_err(err)?;
            destination.0.file.sync_all().map_err(err)?;
            destination.0.check().map_err(err)?; source_file.check().map_err(err)?;
            return Ok(false);
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(err(e)),
    }
    let (mut file, temp) = temporary(&destination.0).map_err(err)?;
    loop { let bytes = source_file.read(1048576).map_err(err)?; if bytes.is_empty() { break; } file.write_all(&bytes).map_err(err)?; }
    source_file.check().map_err(err)?; file.sync_all().map_err(err)?;
    rename(&destination.0, &temp.name, &to, true).map_err(err)?;
    Ok(true)
}

#[rustler::nif(schedule = "DirtyIo")]
fn fjall_directory_sync(handle: ResourceArc<DirectoryHandle>) -> NifResult<bool> {
    let _write = handle.0.root.write.lock().map_err(err)?;
    handle.0.writable().map_err(err)?;
    handle.0.file.sync_all().map_err(err)?;
    handle.0.check().map_err(err)?;
    Ok(true)
}
