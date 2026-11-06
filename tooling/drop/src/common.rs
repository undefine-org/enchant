// Shared format + payload handling between `drop pack` and `drop-launcher`.
// Trailer layout is the contract — docs/native-bundler.md §2.1.
// (included via include! — no //! inner docs allowed here)

pub const MAGIC: &[u8; 4] = b"DRP1";
pub const FORMAT_VERSION: u16 = 1;
/// offset u64 + len u64 + sha256 32B + os u8 + arch u8 + version u16 + magic 4B
pub const TRAILER_LEN: usize = 8 + 8 + 32 + 1 + 1 + 2 + 4;

/// Eval-mode entry handed to the release's `bin/bl eval`.
/// Trailing args land in System.argv() verbatim (a `--` would leak into argv —
/// verified empirically). The CLI entry starts the supervised application using
/// the native launcher's shared policy; eval-mode releases start no apps for it.
pub const CLI_ENTRY: &str = "BeamLisp.Launcher.start_app!(System.argv(), %{})";

/// The layout names shared by the launcher, the packer, and the store. One
/// spelling each, so a rename cannot drift between the two that read them.
#[allow(dead_code)] // pack.rs includes this file but does not use them all
pub const PROJECT_FILE: &str = "env.bl";
/// The release entry script, relative to a payload or payload tree.
#[allow(dead_code)]
pub const LAUNCHER_REL: &str = "bin/bl";
/// A file every beam-lisp tree root has; the launcher walks up to find it.
#[allow(dead_code)]
pub const TREE_MARKER: &str = "priv/boot/core.bl";
/// A payload's printed build facts; the launcher reads one field from it.
#[allow(dead_code)]
pub const BUILD_INFO_FILE: &str = "BUILD_INFO.bl";

pub const OS_LINUX: u8 = 0;
pub const OS_DARWIN: u8 = 1;
pub const OS_WINDOWS: u8 = 2;
pub const ARCH_X86_64: u8 = 0;
pub const ARCH_AARCH64: u8 = 1;
pub const ARCH_UNIVERSAL: u8 = 2;

pub struct Trailer {
    pub offset: u64,
    pub len: u64,
    pub sha256: [u8; 32],
    pub os: u8,
    pub arch: u8,
}

/// "linux/x86_64" etc → (os tag, arch tag).
pub fn parse_target(s: &str) -> Option<(u8, u8)> {
    let (os, arch) = s.split_once('/')?;
    let o = match os {
        "linux" => OS_LINUX,
        "macos" => OS_DARWIN,
        "windows" => OS_WINDOWS,
        _ => return None,
    };
    let a = match arch {
        "x86_64" | "x64" => ARCH_X86_64,
        "aarch64" => ARCH_AARCH64,
        // macOS bundles are dual-arch universal; the tag rides the trailer
        // as its own arch value.
        "universal" if o == OS_DARWIN => ARCH_UNIVERSAL,
        _ => return None,
    };
    Some((o, a))
}

/// (os tag, arch tag) → "linux/x86_64" etc., the inverse of `parse_target`.
/// An unknown tag is shown as its number, never guessed.
#[allow(dead_code)]
pub fn target_name(os: u8, arch: u8) -> String {
    let o = match os {
        OS_LINUX => "linux".to_string(),
        OS_DARWIN => "macos".to_string(),
        OS_WINDOWS => "windows".to_string(),
        n => format!("os{n}"),
    };
    let a = match arch {
        ARCH_X86_64 => "x86_64".to_string(),
        ARCH_AARCH64 => "aarch64".to_string(),
        ARCH_UNIVERSAL => "universal".to_string(),
        n => format!("arch{n}"),
    };
    format!("{o}/{a}")
}

pub fn parse_trailer(data: &[u8]) -> Option<Trailer> {
    if data.len() < TRAILER_LEN {
        return None;
    }
    let t = &data[data.len() - TRAILER_LEN..];
    if &t[52..56] != MAGIC {
        return None;
    }
    let version = u16::from_le_bytes([t[50], t[51]]);
    if version != FORMAT_VERSION {
        return None;
    }
    let mut sha = [0u8; 32];
    sha.copy_from_slice(&t[16..48]);
    Some(Trailer {
        offset: u64::from_le_bytes(t[0..8].try_into().ok()?),
        len: u64::from_le_bytes(t[8..16].try_into().ok()?),
        sha256: sha,
        os: t[48],
        arch: t[49],
    })
}

pub fn encode_trailer(offset: u64, len: u64, sha256: &[u8; 32], os: u8, arch: u8) -> Vec<u8> {
    let mut v = Vec::with_capacity(TRAILER_LEN);
    v.extend_from_slice(&offset.to_le_bytes());
    v.extend_from_slice(&len.to_le_bytes());
    v.extend_from_slice(sha256);
    v.push(os);
    v.push(arch);
    v.extend_from_slice(&FORMAT_VERSION.to_le_bytes());
    v.extend_from_slice(MAGIC);
    v
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let d = Sha256::digest(bytes);
    hex(&d)
}

/// Raw sha256 digest bytes (the daemon tree fingerprint).
#[allow(dead_code)]
pub fn sha256_bytes(bytes: &[u8]) -> Vec<u8> {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes).to_vec()
}

/// Hex-encode raw bytes (no hashing) — for displaying a stored digest.
pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// First-install location (docs/native-bundler.md §6.2).
/// A service can keep reproducible drop storage separate from its durable XDG data.
/// DROP_STORE_ROOT names the store itself (no implicit /drop suffix).
fn explicit_store_root(value: &std::ffi::OsStr) -> Result<std::path::PathBuf, &'static str> {
    let path = std::path::PathBuf::from(value);
    let raw = value.to_string_lossy();
    if raw.split(['/', '\\']).any(|part| part == ".") || !path.is_absolute() || path.components().any(|c| matches!(c, std::path::Component::ParentDir | std::path::Component::CurDir)) {
        return Err("DROP_STORE_ROOT must be an absolute path without . or .. components");
    }
    if path.parent().is_none() {
        return Err("DROP_STORE_ROOT must not be a filesystem root");
    }
    Ok(path)
}

pub fn install_dir() -> std::path::PathBuf {
    if let Some(value) = std::env::var_os("DROP_STORE_ROOT") {
        return explicit_store_root(&value).unwrap_or_else(|message| {
            eprintln!("drop: {message}");
            std::process::exit(2)
        });
    }
    if cfg!(target_os = "windows") {
        if let Ok(l) = std::env::var("LOCALAPPDATA") {
            return std::path::PathBuf::from(l).join("drop");
        }
        return std::path::PathBuf::from(r"C:\Program Files\drop");
    }
    if cfg!(target_os = "macos") {
        if let Ok(h) = std::env::var("HOME") {
            return std::path::PathBuf::from(h).join("Library/Application Support/drop");
        }
    } else if let Ok(x) = std::env::var("XDG_DATA_HOME") {
        if !x.is_empty() {
            return std::path::PathBuf::from(x).join("drop");
        }
    }
    if let Ok(h) = std::env::var("HOME") {
        return std::path::PathBuf::from(h).join(".local/share/drop");
    }
    std::path::PathBuf::from("/tmp/drop")
}

/// Zip-slip guard: reject absolute paths and `..` components.
pub fn safe_path(base: &std::path::Path, rel: &std::path::Path) -> std::io::Result<std::path::PathBuf> {
    if rel.is_absolute() {
        return Err(std::io::Error::other(format!(
            "payload contains absolute path: {}",
            rel.display()
        )));
    }
    let mut out = base.to_path_buf();
    for c in rel.components() {
        match c {
            std::path::Component::Normal(p) => out.push(p),
            std::path::Component::CurDir => {}
            _ => {
                return Err(std::io::Error::other(format!(
                    "payload contains unsafe path component: {}",
                    rel.display()
                )))
            }
        }
    }
    Ok(out)
}

/// Cheap startup validation shared by every stored-payload execution path.
/// A bin directory alone survives some interrupted extractions. Follow the
/// release's own version selection, so a missing start_erl.data never turns
/// into an attempted exec of releases//elixir. No whole-payload hash on warm use.
pub fn payload_ready(root: &std::path::Path) -> bool {
    payload_status(root).unwrap_or(false)
}
fn payload_status(root: &std::path::Path) -> std::io::Result<bool> {
    use std::io::Read;
    fn component(value: &str) -> bool {
        !value.is_empty() && value.len() <= 128 && value != "." && value != ".."
            && value.bytes().all(|c| c.is_ascii_alphanumeric() || b"._-+".contains(&c))
    }
    fn metadata(path: std::path::PathBuf) -> std::io::Result<Option<std::fs::Metadata>> {
        match std::fs::metadata(path) {
            Ok(value) => Ok(Some(value)),
            Err(e) if matches!(e.kind(), std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory) => Ok(None),
            Err(e) => Err(e),
        }
    }
    fn regular(path: std::path::PathBuf) -> std::io::Result<bool> {
        Ok(metadata(path)?.is_some_and(|m| m.is_file() && m.len() != 0))
    }
    let path = root.join("releases/start_erl.data");
    if !regular(path.clone())? { return Ok(false); }
    let file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(e) => return Err(e),
    };
    let mut bytes = Vec::new();
    file.take(513).read_to_end(&mut bytes)?;
    if bytes.len() > 512 { return Ok(false); }
    let Ok(text) = std::str::from_utf8(&bytes) else { return Ok(false) };
    let fields: Vec<_> = text.split_whitespace().collect();
    if fields.len() != 2 || !fields.iter().all(|v| component(v)) { return Ok(false); }
    let release = root.join("releases").join(fields[1]);
    let erts = root.join(format!("erts-{}/bin", fields[0]));
    let unix = regular(root.join(LAUNCHER_REL))? && regular(release.join("elixir"))?
        && regular(erts.join("erl"))? && regular(erts.join("beam.smp"))?;
    let windows = regular(root.join("bin/bl.bat"))? && regular(release.join("elixir.bat"))?
        && regular(erts.join("erl.exe"))? && regular(erts.join("beam.smp.dll"))?;
    Ok((unix || windows) && metadata(root.join("lib"))?.is_some_and(|m| m.is_dir()))
}

/// Persist all file contents and directory entries before publishing the root.
/// Unix directory fsync is essential: a successful rename alone is not a
/// power-loss boundary. Windows retains its existing directory-flush behavior.
fn sync_payload_tree(root: &std::path::Path) -> std::io::Result<()> {
    for entry in std::fs::read_dir(root)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        if kind.is_dir() { sync_payload_tree(&entry.path())?; }
        else if kind.is_file() { std::fs::File::open(entry.path())?.sync_all()?; }
    }
    sync_payload_directory(root)
}
fn sync_payload_directory(root: &std::path::Path) -> std::io::Result<()> {
    #[cfg(unix)]
    std::fs::File::open(root)?.sync_all()?;
    #[cfg(not(unix))]
    let _ = root;
    Ok(())
}

/// Atomic extraction. Staging names are unique even for concurrent calls in
/// one process; publication/repair holds a permanent per-destination kernel
/// lock. A process death releases custody without deleting its lock inode.
pub fn extract_tar_gz(payload: &[u8], dest: &std::path::Path) -> std::io::Result<()> {
    if dest.file_name().is_none() {
        return Err(std::io::Error::other("payload destination has no name"));
    }
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    std::fs::create_dir_all(dest.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(std::path::Path::new(".")))?;
    let tmp = loop {
        let sequence = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let path = dest.with_extension(format!("tmp-{}-{sequence}", std::process::id()));
        match std::fs::create_dir(&path) {
            Ok(()) => break path,
            // A reboot can reuse a PID. Leave an interrupted staging tree
            // intact; it is never authority to delete another invocation.
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e),
        }
    };
    let result = (|| {
        unpack_into(payload, &tmp)?;
        if !payload_ready(&tmp) { return Err(std::io::Error::other("payload lacks a complete BEAM release")); }
        sync_payload_tree(&tmp)?;
        publish(&tmp, dest)
    })();
    if result.is_err() { let _ = std::fs::remove_dir_all(&tmp); }
    result
}

/// Unpack the payload into an existing, empty staging dir.
fn unpack_into(payload: &[u8], tmp: &std::path::Path) -> std::io::Result<()> {
    let gz = flate2::read::GzDecoder::new(payload);
    let mut ar = tar::Archive::new(gz);
    ar.set_preserve_permissions(true);
    for e in ar.entries()? {
        let mut e = e?;
        let rel = e.path()?.into_owned();
        let out = safe_path(tmp, &rel)?;
        if let Some(parent) = out.parent() {
            std::fs::create_dir_all(parent)?;
        }
        e.unpack(&out)?;
    }
    make_entry_executable(tmp, LAUNCHER_REL);
    Ok(())
}

/// The same Linux executable/mapping inventory protects GC and cache repair.
/// Other platforms retain their existing GC observation limits.
fn running_payloads(install: &std::path::Path) -> std::collections::HashSet<String> {
    let mut out = std::collections::HashSet::new();
    let prefix = format!("{}/", install.display());
    let Ok(rd) = std::fs::read_dir("/proc") else { return out };
    let mut note = |s: &str| {
        if let Some(id) = s.strip_prefix(&prefix).and_then(|r| r.split('/').next()) {
            out.insert(id.to_string());
        }
    };
    for e in rd.flatten() {
        if !e.file_name().to_string_lossy().bytes().all(|b| b.is_ascii_digit()) {
            continue;
        }
        let p = e.path();
        if let Ok(exe) = std::fs::read_link(p.join("exe")) {
            note(&exe.to_string_lossy());
        }
        if let Ok(maps) = std::fs::read_to_string(p.join("maps")) {
            for line in maps.lines() {
                if let Some(i) = line.find(&prefix) {
                    note(&line[i..]);
                }
            }
        }
    }
    out
}

/// Repair and publication share one lock. Recheck after acquiring it: an
/// extractor that observed debris must never remove a newly published winner.
/// This lock file is permanent, outside the version tree and never unlinked.
fn publish(tmp: &std::path::Path, dest: &std::path::Path) -> std::io::Result<()> {
    let parent = dest.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(std::path::Path::new("."));
    let name = dest.file_name().ok_or_else(|| std::io::Error::other("payload destination has no name"))?;
    let mut lock_name = std::ffi::OsString::from(".");
    lock_name.push(name); lock_name.push(".extract.lock");
    let lock = std::fs::OpenOptions::new().read(true).write(true).create(true).truncate(false)
        .open(parent.join(lock_name))?;
    lock.lock()?;
    // I/O or permission failure is not evidence that a tree is disposable.
    if payload_status(dest)? {
        // A winner may have died after rename and before parent fsync. Sync
        // its publication before conceding the race, without replacing it.
        sync_payload_directory(parent)?;
        std::fs::remove_dir_all(tmp)?;
        return Ok(());
    }
    match std::fs::symlink_metadata(dest) {
        Ok(m) if m.is_dir() => {
            let actual = std::fs::canonicalize(dest)?;
            let parent = actual.parent().ok_or_else(|| std::io::Error::other("payload root has no parent"))?;
            let name = actual.file_name().unwrap().to_string_lossy();
            if running_payloads(parent).contains(name.as_ref()) {
                return Err(std::io::Error::other("incomplete payload is still in use; refusing destructive repair"));
            }
            std::fs::remove_dir_all(dest)?;
        },
        Ok(_) => std::fs::remove_file(dest)?,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e),
    }
    std::fs::rename(tmp, dest)?;
    sync_payload_directory(parent)
}

#[cfg(unix)]
pub fn make_entry_executable(dir: &std::path::Path, rel: &str) {
    use std::os::unix::fs::PermissionsExt;
    let p = dir.join(rel);
    if p.is_file() {
        if let Ok(meta) = std::fs::metadata(&p) {
            let mut perms = meta.permissions();
            perms.set_mode(perms.mode() | 0o755);
            let _ = std::fs::set_permissions(&p, perms);
        }
    }
}
#[cfg(not(unix))]
pub fn make_entry_executable(_dir: &std::path::Path, _rel: &str) {}

#[cfg(test)]
mod store_root_tests {
    use super::explicit_store_root;
    #[test]
    fn explicit_store_is_independent_of_xdg_and_has_no_added_suffix() {
        assert_eq!(explicit_store_root(std::ffi::OsStr::new("/var/cache/app-runtime")).unwrap(), std::path::PathBuf::from("/var/cache/app-runtime"));
    }
    #[test]
    fn explicit_store_rejects_relative_empty_root_and_parent_traversal() {
        for path in ["", "relative", "/", "/var/cache/../data", "/var/./cache"] {
            assert!(explicit_store_root(std::ffi::OsStr::new(path)).is_err(), "{path}");
        }
    }
}

#[cfg(test)]
fn payload_fixture(root: &std::path::Path, launcher: &[u8]) {
    for (path, bytes) in [
        (LAUNCHER_REL, launcher), ("releases/start_erl.data", b"17.0 0.1.0\n".as_slice()),
        ("releases/0.1.0/elixir", b"elixir".as_slice()),
        ("erts-17.0/bin/erl", b"erl".as_slice()), ("erts-17.0/bin/beam.smp", b"beam".as_slice()),
        ("lib/beam_lisp-0.1.0/ebin/beam_lisp.app", b"app".as_slice()),
    ] {
        let path = root.join(path);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, bytes).unwrap();
    }
}

#[cfg(test)]
mod payload_cache_tests {
    use super::*;
    fn scratch(label: &str) -> std::path::PathBuf {
        let path = std::env::temp_dir().join(format!("drop-payload-{label}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(&path).unwrap(); path
    }
    fn archive(root: &std::path::Path) -> Vec<u8> {
        let mut tar = tar::Builder::new(flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default()));
        tar.append_dir_all(".", root).unwrap();
        tar.into_inner().unwrap().finish().unwrap()
    }
    #[test]
    fn release_selection_must_be_bounded_complete_and_cannot_escape_the_root() {
        let root = scratch("validation");
        payload_fixture(&root, b"entry"); assert!(payload_ready(&root));
        for malformed in ["", "17.0", "17.0 0.1.0 extra", "../escape 0.1.0", "17.0 ../../escape", "17.0 .", "17.0 /absolute"] {
            std::fs::write(root.join("releases/start_erl.data"), malformed).unwrap();
            assert!(!payload_ready(&root), "{malformed}");
        }
        std::fs::write(root.join("releases/start_erl.data"), vec![b'x'; 513]).unwrap();
        assert!(!payload_ready(&root));
        for missing in ["bin/bl", "releases/start_erl.data", "releases/0.1.0/elixir", "erts-17.0/bin/erl", "erts-17.0/bin/beam.smp"] {
            payload_fixture(&root, b"entry"); std::fs::remove_file(root.join(missing)).unwrap();
            assert!(!payload_ready(&root), "missing {missing}");
        }
        payload_fixture(&root, b"entry");
        std::fs::write(root.join("erts-17.0/bin/beam.smp"), b"").unwrap();
        assert!(!payload_ready(&root));
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn bin_present_release_metadata_missing_is_repaired_and_retry_keeps_the_winner() {
        let parent = scratch("repair"); let dest = parent.join("12345678");
        let source = parent.join("source"); payload_fixture(&source, b"complete");
        let bytes = archive(&source);
        payload_fixture(&dest, b"broken");
        std::fs::remove_file(dest.join("releases/start_erl.data")).unwrap();
        assert!(dest.join("bin").is_dir()); assert!(!payload_ready(&dest));
        extract_tar_gz(&bytes, &dest).unwrap();
        assert!(payload_ready(&dest));
        std::fs::write(dest.join("winner-preserved"), b"retain").unwrap();
        extract_tar_gz(&bytes, &dest).unwrap();
        assert_eq!(std::fs::read(dest.join("winner-preserved")).unwrap(), b"retain");
        assert!(parent.join(".12345678.extract.lock").is_file());
        assert!(!std::fs::read_dir(&parent).unwrap().any(|e| e.unwrap().file_name().to_string_lossy().contains(".tmp-")));
        let _ = std::fs::remove_dir_all(parent);
    }
    #[test]
    fn concurrent_repair_and_extraction_share_one_publication() {
        let parent = scratch("concurrent"); let source = parent.join("source");
        payload_fixture(&source, b"complete"); let bytes = std::sync::Arc::new(archive(&source));
        let dest = parent.join("abcdef01"); std::fs::create_dir_all(dest.join("bin")).unwrap();
        let barrier = std::sync::Arc::new(std::sync::Barrier::new(8));
        let children: Vec<_> = (0..8).map(|_| {
            let (bytes, barrier, dest) = (bytes.clone(), barrier.clone(), dest.clone());
            std::thread::spawn(move || {
                barrier.wait(); extract_tar_gz(&bytes, &dest).unwrap();
                assert!(payload_ready(&dest));
                #[cfg(unix)] { use std::os::unix::fs::MetadataExt; std::fs::metadata(&dest).unwrap().ino() }
                #[cfg(not(unix))] { 0 }
            })
        }).collect();
        let inodes: Vec<_> = children.into_iter().map(|t| t.join().unwrap()).collect();
        assert!(inodes.iter().all(|i| *i == inodes[0]), "a valid winner is never replaced");
        let _ = std::fs::remove_dir_all(parent);
    }
    #[test]
    #[cfg(target_os = "linux")]
    fn mapped_runtime_files_block_destructive_repair() {
        use std::os::fd::AsRawFd;
        struct Mapping(*mut libc::c_void);
        impl Drop for Mapping { fn drop(&mut self) { unsafe { libc::munmap(self.0, 4); } } }
        let parent = scratch("mapped-runtime"); let dest = parent.join("12345678");
        let source = parent.join("source"); payload_fixture(&source, b"complete");
        payload_fixture(&dest, b"preserve");
        let file = std::fs::File::open(dest.join(LAUNCHER_REL)).unwrap();
        let address = unsafe { libc::mmap(std::ptr::null_mut(), 4, libc::PROT_READ, libc::MAP_PRIVATE, file.as_raw_fd(), 0) };
        assert_ne!(address, libc::MAP_FAILED); let mapping = Mapping(address);
        std::fs::remove_file(dest.join("releases/start_erl.data")).unwrap();
        assert!(!payload_ready(&dest));
        assert!(extract_tar_gz(&archive(&source), &dest).is_err());
        assert_eq!(std::fs::read(dest.join(LAUNCHER_REL)).unwrap(), b"preserve");
        drop(mapping); drop(file);
        extract_tar_gz(&archive(&source), &dest).unwrap(); assert!(payload_ready(&dest));
        let _ = std::fs::remove_dir_all(parent);
    }
    #[test]
    #[cfg(unix)]
    fn ambiguous_probe_errors_preserve_the_destination() {
        let parent = scratch("probe-error"); let dest = parent.join("12345678");
        let source = parent.join("source"); payload_fixture(&source, b"complete");
        payload_fixture(&dest, b"preserve");
        let selection = dest.join("releases/start_erl.data");
        std::fs::remove_file(&selection).unwrap();
        std::os::unix::fs::symlink("start_erl.data", &selection).unwrap();
        assert!(payload_status(&dest).is_err());
        assert!(extract_tar_gz(&archive(&source), &dest).is_err());
        assert_eq!(std::fs::read(dest.join(LAUNCHER_REL)).unwrap(), b"preserve");
        assert!(std::fs::symlink_metadata(selection).unwrap().is_symlink());
        let _ = std::fs::remove_dir_all(parent);
    }
    #[test]
    fn cross_target_windows_layout_is_recognised_without_host_execution() {
        let root = scratch("windows");
        for path in ["bin/bl.bat", "releases/start_erl.data", "releases/0.1.0/elixir.bat",
                     "erts-17.0/bin/erl.exe", "erts-17.0/bin/beam.smp.dll"] {
            let file = root.join(path); std::fs::create_dir_all(file.parent().unwrap()).unwrap();
            std::fs::write(file, if path.ends_with("start_erl.data") { b"17.0 0.1.0".as_slice() } else { b"fixture".as_slice() }).unwrap();
        }
        std::fs::create_dir(root.join("lib")).unwrap();
        assert!(payload_ready(&root));
        std::fs::remove_file(root.join("erts-17.0/bin/beam.smp.dll")).unwrap();
        assert!(!payload_ready(&root));
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn reused_pid_staging_and_unnamed_destinations_cannot_break_extraction() {
        let parent = scratch("stale-pid"); let source = parent.join("source");
        payload_fixture(&source, b"complete"); let bytes = archive(&source);
        let dest = parent.join("12345678");
        // NEXT is process-global; reserve many names, so this control works
        // beside the other extraction tests without resetting shared state.
        let debris: Vec<_> = (0..256).map(|i| dest.with_extension(format!("tmp-{}-{i}", std::process::id()))).collect();
        for path in &debris { std::fs::create_dir(path).unwrap(); std::fs::write(path.join("keep"), b"old").unwrap(); }
        extract_tar_gz(&bytes, &dest).unwrap(); assert!(payload_ready(&dest));
        for path in &debris { assert_eq!(std::fs::read(path.join("keep")).unwrap(), b"old"); }
        for path in ["/", ".", ".."] { assert!(extract_tar_gz(&bytes, std::path::Path::new(path)).is_err()); }
        let _ = std::fs::remove_dir_all(parent);
    }
    #[test]
    fn invalid_payload_never_replaces_an_existing_tree() {
        let parent = scratch("invalid"); let source = parent.join("source");
        std::fs::create_dir_all(source.join("bin")).unwrap();
        std::fs::write(source.join("bin/bl"), b"not a release").unwrap();
        let dest = parent.join("12345678"); payload_fixture(&dest, b"winner");
        assert!(extract_tar_gz(&archive(&source), &dest).is_err());
        assert_eq!(std::fs::read(dest.join(LAUNCHER_REL)).unwrap(), b"winner");
        assert!(payload_ready(&dest));
        let _ = std::fs::remove_dir_all(parent);
    }
}
