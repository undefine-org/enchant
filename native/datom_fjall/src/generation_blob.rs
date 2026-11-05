//! Declared FS blob tiers borrow the same generation owner as ordinary stores.
//! No path flag becomes authority; all reads walk from its pinned root fd.
use super::{directory::{Directory, Reader}, generation::{self, Owner}, err, to_binary};
use rustler::{Encoder, Env, NifResult, Resource, ResourceArc, Term};
use std::fs::{self, ReadDir};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

mod atoms { rustler::atoms! { nil } }
struct Blob { owner: Arc<Owner>, parts: Vec<String>, path: PathBuf }
struct BlobHandle(Mutex<Option<Arc<Blob>>>);
#[rustler::resource_impl]
impl Resource for BlobHandle {}
struct ReadState { owner: Arc<Owner>, reader: Reader }
struct BlobReader(Mutex<Option<ReadState>>);
#[rustler::resource_impl]
impl Resource for BlobReader {}
struct Frame { directory: Arc<Directory>, entries: ReadDir, prefix: String }
struct Scan { owner: Arc<Owner>, frames: Vec<Frame> }
struct BlobScan(Mutex<Option<Scan>>);
#[rustler::resource_impl]
impl Resource for BlobScan {}
fn failure(message: &'static str) -> std::io::Error { std::io::Error::other(message) }
fn live(handle: &BlobHandle) -> NifResult<Arc<Blob>> {
    let blob = handle.0.lock().map_err(err)?.clone().ok_or_else(|| err("blob handle closed"))?;
    blob.owner.check().map_err(err)?; Ok(blob)
}
fn hex(value: &str, length: usize) -> bool {
    value.len() == length && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn canonical_missing(path: &Path) -> std::io::Result<PathBuf> {
    let mut current = if path.is_absolute() { path.into() } else { std::env::current_dir()?.join(path) };
    let mut missing = Vec::new();
    loop {
        match fs::symlink_metadata(&current) {
            Ok(_) => break,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                let leaf = current.file_name().and_then(|p| p.to_str()).ok_or_else(|| failure("invalid blob path"))?;
                super::directory::name(leaf)?; missing.push(leaf.to_owned());
                if !current.pop() { return Err(failure("blob path has no ancestor")); }
            }
            Err(e) => return Err(e),
        }
    }
    let mut canonical = fs::canonicalize(current)?;
    for leaf in missing.into_iter().rev() { canonical.push(leaf); }
    Ok(canonical)
}
fn directory(blob: &Blob) -> std::io::Result<Option<Arc<Directory>>> {
    blob.owner.check()?;
    let mut current = blob.owner.root.clone();
    for part in &blob.parts {
        current = match current.child(part, false, false) {
            Ok(value) => value,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e),
        };
    }
    Ok(Some(current))
}
fn reader(blob: &Blob, sha: &str) -> std::io::Result<Option<Reader>> {
    if !hex(sha, 64) { return Err(failure("invalid content digest")); }
    let Some(mut current) = directory(blob)? else { return Ok(None); };
    for shard in [&sha[..2], &sha[2..4]] {
        current = match current.child(shard, false, false) {
            Ok(value) => value,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e),
        };
    }
    match current.open_file(sha) {
        Ok(value) => Ok(Some(value)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e),
    }
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_open<'a>(env: Env<'a>, path: String) -> NifResult<Term<'a>> {
    super::refuse_offline_path(Path::new(&path)).map_err(err)?;
    let Some(owner) = generation::access(Path::new(&path)).map_err(err)? else { return Ok(atoms::nil().encode(env)); };
    let canonical = canonical_missing(Path::new(&path)).map_err(err)?;
    if !owner.blobs.contains(&canonical) { return Err(err("blob tier outside generation inventory")); }
    let relative = canonical.strip_prefix(&owner.root.path).map_err(err)?;
    let parts = super::sealing::relative(relative.to_str().ok_or_else(|| err("invalid blob path"))?).map_err(err)?
        .into_iter().map(str::to_owned).collect();
    let blob = Arc::new(Blob { owner, parts, path: canonical });
    // Existing tiers must be actual directories; missing empty tiers stay
    // absent until admission, including their .tmp directory.
    directory(&blob).map_err(err)?;
    let path = blob.path.to_string_lossy().into_owned();
    Ok((ResourceArc::new(BlobHandle(Mutex::new(Some(blob)))), path).encode(env))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_close(handle: ResourceArc<BlobHandle>) -> NifResult<bool> {
    handle.0.lock().map_err(err)?.take(); Ok(true)
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_identity(handle: ResourceArc<BlobHandle>) -> NifResult<String> {
    Ok(live(&handle)?.path.to_string_lossy().into_owned())
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_has(handle: ResourceArc<BlobHandle>, sha: String) -> NifResult<bool> {
    let blob = live(&handle)?;
    Ok(reader(&blob, &sha).map_err(err)?.is_some())
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_reader<'a>(env: Env<'a>, handle: ResourceArc<BlobHandle>, sha: String) -> NifResult<Term<'a>> {
    let blob = live(&handle)?;
    let Some(reader) = reader(&blob, &sha).map_err(err)? else { return Ok(atoms::nil().encode(env)); };
    Ok(ResourceArc::new(BlobReader(Mutex::new(Some(ReadState { owner: blob.owner.clone(), reader })))).encode(env))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_chunk<'a>(env: Env<'a>, handle: ResourceArc<BlobReader>, limit: usize) -> NifResult<Term<'a>> {
    let mut state = handle.0.lock().map_err(err)?;
    let current = state.as_mut().ok_or_else(|| err("blob reader closed"))?;
    current.owner.check().map_err(err)?;
    let part = current.reader.read(limit).map_err(err)?;
    let done = part.len() < limit;
    if done { state.take(); }
    Ok((to_binary(env, &part)?, done).encode(env))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_reader_close(handle: ResourceArc<BlobReader>) -> NifResult<bool> {
    handle.0.lock().map_err(err)?.take(); Ok(true)
}
fn frame(directory: Arc<Directory>, prefix: String) -> std::io::Result<Frame> {
    directory.check()?;
    let entries = fs::read_dir(super::directory::pinned(&directory.file, "."))?;
    Ok(Frame { directory, entries, prefix })
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_scan(handle: ResourceArc<BlobHandle>) -> NifResult<ResourceArc<BlobScan>> {
    let blob = live(&handle)?;
    let frames = directory(&blob).map_err(err)?.map(|d| frame(d, String::new())).transpose().map_err(err)?.into_iter().collect();
    Ok(ResourceArc::new(BlobScan(Mutex::new(Some(Scan { owner: blob.owner.clone(), frames })))))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_page(handle: ResourceArc<BlobScan>, limit: usize) -> NifResult<(Vec<String>, bool)> {
    if limit == 0 || limit > 512 { return Err(err("invalid blob page bound")); }
    let mut state = handle.0.lock().map_err(err)?;
    let Some(scan) = state.as_mut() else { return Ok((Vec::new(), true)); };
    scan.owner.check().map_err(err)?;
    let mut rows = Vec::new();
    // Bound work as well as results, including directories full of orphans.
    let mut visited = 0;
    while !scan.frames.is_empty() && rows.len() < limit && visited < 4096 {
        let frame = scan.frames.last_mut().unwrap(); frame.directory.check().map_err(err)?;
        let Some(entry) = frame.entries.next() else { scan.frames.pop(); continue; };
        let entry = entry.map_err(err)?; visited += 1;
        let name = entry.file_name().into_string().map_err(|_| err("non-UTF8 blob entry"))?;
        if frame.prefix.len() < 4 {
            if !hex(&name, 2) { continue; }
            if entry.file_type().map_err(err)?.is_file() { continue; }
            let child = frame.directory.child(&name, false, false).map_err(err)?;
            let prefix = format!("{}{}", frame.prefix, name);
            scan.frames.push(self::frame(child, prefix).map_err(err)?);
        } else if hex(&name, 64) && name.starts_with(&frame.prefix) {
            // Validate a pinned regular, unaliased file even when listing.
            frame.directory.open_file(&name).map_err(err)?;
            rows.push(name);
        }
    }
    let done = scan.frames.is_empty();
    if done { state.take(); }
    Ok((rows, done))
}
#[rustler::nif(schedule = "DirtyIo")]
fn fjall_generation_blob_scan_close(handle: ResourceArc<BlobScan>) -> NifResult<bool> {
    handle.0.lock().map_err(err)?.take(); Ok(true)
}
