//! OS custody for cache generations and build workspaces. Lock files are
//! permanent anchors outside the directory being protected: never unlink one.
use rustler::{Atom, Env, LocalPid, Monitor, NifResult, ResourceArc, Term};
use std::fs::{File, OpenOptions, TryLockError};
use std::io::{Read, Write};
use std::sync::Mutex;

rustler::atoms! { ok, busy, child }

// Rust 1.95's File locks report Unsupported on Android before making a
// syscall. Bionic provides flock on our Android API floor. Keep the same
// nonblocking, open-file-description custody and close-to-release semantics.
#[cfg(any(target_os = "android", all(test, unix)))]
fn try_flock(file: &File, shared: bool) -> Result<(), TryLockError> {
    use std::os::fd::AsRawFd;
    let operation = (if shared { libc::LOCK_SH } else { libc::LOCK_EX }) | libc::LOCK_NB;
    loop {
        // SAFETY: the borrowed File keeps this descriptor live for the call;
        // flock takes no pointers and does not take ownership of the descriptor.
        if unsafe { libc::flock(file.as_raw_fd(), operation) } == 0 {
            return Ok(());
        }
        let error = std::io::Error::last_os_error();
        match error.kind() {
            std::io::ErrorKind::Interrupted => continue,
            std::io::ErrorKind::WouldBlock => return Err(TryLockError::WouldBlock),
            _ => return Err(TryLockError::Error(error)),
        }
    }
}

fn try_lock(file: &File, shared: bool) -> Result<(), TryLockError> {
    #[cfg(target_os = "android")]
    { try_flock(file, shared) }
    #[cfg(not(target_os = "android"))]
    { if shared { file.try_lock_shared() } else { file.try_lock() } }
}

struct Claim {
    path: std::path::PathBuf,
}

fn claim_path(path: &str) -> std::io::Result<std::path::PathBuf> {
    let path = std::path::Path::new(path);
    let name = path.file_name().ok_or_else(|| std::io::Error::other("claim needs a filename"))?;
    Ok(std::fs::canonicalize(path.parent().unwrap_or(std::path::Path::new(".")))?.join(name))
}

pub struct FileLock {
    file: Mutex<Option<File>>,
    owner: Option<LocalPid>,
    shared: bool,
    claim: Option<Claim>,
}

impl FileLock {
    fn close(&self) {
        self.file.lock().unwrap_or_else(|e| e.into_inner()).take();
    }
}

#[rustler::resource_impl]
impl rustler::Resource for FileLock {
    fn down(&self, _env: Env<'_>, _pid: LocalPid, _monitor: Monitor) {
        self.close();
    }
}

#[rustler::nif(name = "nif_file_lock", schedule = "DirtyIo")]
fn acquire(env: Env<'_>, path: String, shared: bool, monitor_owner: bool)
    -> NifResult<(Atom, Option<ResourceArc<FileLock>>)>
{
    let io_error = |e: std::io::Error| rustler::Error::Term(Box::new(e.to_string()));
    if let Some(parent) = std::path::Path::new(&path).parent() {
        std::fs::create_dir_all(parent).map_err(io_error)?;
    }
    let file = OpenOptions::new().read(true).write(true).create(true)
        .truncate(false).open(path).map_err(io_error)?;
    let locked = try_lock(&file, shared);
    match locked {
        Ok(()) => {
            let resource = ResourceArc::new(FileLock {
                file: Mutex::new(Some(file)),
                owner: monitor_owner.then(|| env.pid()),
                shared,
                claim: None,
            });
            if monitor_owner && resource.monitor(Some(env), &env.pid()).is_none() {
                resource.close();
                return Err(rustler::Error::BadArg);
            }
            Ok((ok(), Some(resource)))
        }
        Err(TryLockError::WouldBlock) => Ok((busy(), None)),
        Err(TryLockError::Error(e)) => Err(io_error(e)),
    }
}

// Verify the open kernel object, not a saved pathname or diagnostic claim.
// Other targets cannot certify reentrant custody with this Unix identity rule.
#[cfg(unix)]
fn same_anchor(file: &File, path: &str) -> bool {
    use std::os::unix::fs::MetadataExt;
    match (file.metadata(), std::fs::metadata(path)) {
        (Ok(held), Ok(expected)) => held.dev() == expected.dev() && held.ino() == expected.ino(),
        _ => false,
    }
}

#[cfg(not(unix))]
fn same_anchor(_file: &File, _path: &str) -> bool { false }

// Mint a claim only after excluding both writers and surviving compiler
// followers. Keep that second barrier through cohort publication: a late old
// follower cannot enter between the drain check and the new record.
#[rustler::nif(name = "nif_file_claim", schedule = "DirtyIo")]
fn claim(env: Env<'_>, anchor: String, path: String, what: String)
    -> NifResult<(Atom, Option<ResourceArc<FileLock>>)>
{
    let io_error = |e: std::io::Error| rustler::Error::Term(Box::new(e.to_string()));
    let open = |path: &str| -> std::io::Result<File> {
        if let Some(parent) = std::path::Path::new(path).parent() {
            std::fs::create_dir_all(parent)?;
        }
        OpenOptions::new().read(true).write(true).create(true).truncate(false).open(path)
    };
    let writer = open(&anchor).map_err(io_error)?;
    match try_lock(&writer, false) {
        Ok(()) => {}
        Err(TryLockError::WouldBlock) => return Ok((busy(), None)),
        Err(TryLockError::Error(error)) => return Err(io_error(error)),
    }
    let followers = open(&format!("{anchor}.followers")).map_err(io_error)?;
    match try_lock(&followers, false) {
        Ok(()) => {}
        Err(TryLockError::WouldBlock) => return Ok((child(), None)),
        Err(TryLockError::Error(error)) => return Err(io_error(error)),
    }
    // The caller supplies descriptive text, never the cohort capability. Mint
    // a fresh nonce here so a handcrafted request cannot republish an old child
    // context while obtaining a genuinely admitted native resource.
    let mut nonce = [0u8; 16];
    File::open("/dev/urandom").and_then(|mut source| source.read_exact(&mut nonce)).map_err(io_error)?;
    let token: String = nonce.iter().map(|byte| format!("{byte:02x}")).collect();
    let time = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default().as_millis();
    let record = format!("[:claim-v2 {} {time} {token} {what}]", std::process::id());
    let path = claim_path(&path).map_err(io_error)?;
    let temporary = path.with_file_name(format!(".claim-{token}.tmp"));
    let publish = (|| -> std::io::Result<()> {
        let mut file = OpenOptions::new().write(true).create_new(true).open(&temporary)?;
        file.write_all(record.as_bytes())?;
        drop(file);
        // Do not follow a preexisting diagnostic symlink or expose a partial
        // cohort. Diagnostic content stays data, not a custody credential.
        std::fs::rename(&temporary, &path)
    })();
    if let Err(error) = publish {
        let _ = std::fs::remove_file(&temporary);
        return Err(io_error(error));
    }
    let resource = ResourceArc::new(FileLock {
        file: Mutex::new(Some(writer)), owner: Some(env.pid()), shared: false,
        claim: Some(Claim { path }),
    });
    if resource.monitor(Some(env), &env.pid()).is_none() {
        resource.close();
        return Err(rustler::Error::BadArg);
    }
    // Publication is complete before this exclusive follower barrier drops.
    drop(followers);
    Ok((ok(), Some(resource)))
}

#[rustler::nif(name = "nif_file_claim_owned", schedule = "DirtyIo")]
fn owned(env: Env<'_>, handle: Term<'_>, anchor: String, path: String) -> bool {
    let Ok(resource) = handle.decode::<ResourceArc<FileLock>>() else { return false; };
    if resource.shared || resource.owner != Some(env.pid()) {
        return false;
    }
    let Some(claim) = &resource.claim else { return false; };
    let file = resource.file.lock().unwrap_or_else(|e| e.into_inner());
    file.as_ref().is_some_and(|file| same_anchor(file, &anchor))
        && claim_path(&path).ok().as_ref() == Some(&claim.path)
}

#[rustler::nif(name = "nif_file_unlock", schedule = "DirtyIo")]
fn release(env: Env<'_>, resource: ResourceArc<FileLock>) -> NifResult<Atom> {
    let mut file = resource.file.lock().unwrap_or_else(|e| e.into_inner());
    // VM-scoped leases intentionally have no process owner. Closed resources
    // remain harmless/idempotent, including after their owner's DOWN.
    if file.is_some() && resource.owner.is_some_and(|owner| owner != env.pid()) {
        return Err(rustler::Error::BadArg);
    }
    file.take();
    Ok(ok())
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn android_flock_keeps_shared_exclusive_and_close_custody() {
        let path = std::env::temp_dir().join(format!("bl-file-lock-{}-{}",
            std::process::id(), std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
        let open = || OpenOptions::new().read(true).write(true).create(true)
            .truncate(false).open(&path).unwrap();
        let first = open();
        let second = open();
        let writer = open();
        try_flock(&first, true).unwrap();
        try_flock(&second, true).unwrap();
        assert!(matches!(try_flock(&writer, false), Err(TryLockError::WouldBlock)));
        drop(first);
        assert!(matches!(try_flock(&writer, false), Err(TryLockError::WouldBlock)));
        drop(second);
        try_flock(&writer, false).unwrap();

        // Interoperate with the host's standard flock implementation. The
        // replacement must protect the same kernel anchor, not a local mutex.
        let reader = open();
        assert!(matches!(try_lock(&reader, true), Err(TryLockError::WouldBlock)));
        drop(writer);
        try_lock(&reader, true).unwrap();
        let writer = open();
        assert!(matches!(try_flock(&writer, false), Err(TryLockError::WouldBlock)));
        drop(reader);
        try_flock(&writer, false).unwrap();
        drop(writer);
        std::fs::remove_file(path).unwrap();
    }
}
