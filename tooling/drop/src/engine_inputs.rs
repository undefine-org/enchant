//! A single command's checked engine bytes. The format and policy are the
//! existing scripts/sdk-inputs protocol; Python remains its independent verifier
//! during immutable source capture. Evidence is never retained between commands.
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{self, Read};
use std::path::{Path, PathBuf};

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

#[cfg(target_os = "linux")]
#[derive(Clone, Debug, PartialEq, Eq)]
struct Stamp {
    device: u64, inode: u64, size: u64, mode: u32,
    mtime: (i64, i64), ctime: (i64, i64),
}

#[cfg(target_os = "linux")]
impl Stamp {
    fn file(meta: &Metadata) -> Self {
        use std::os::unix::fs::MetadataExt;
        Self { device: meta.dev(), inode: meta.ino(), size: meta.size(), mode: meta.mode(),
            mtime: (meta.mtime(), meta.mtime_nsec()), ctime: (meta.ctime(), meta.ctime_nsec()) }
    }
    fn directory(meta: &Metadata) -> Self {
        let mut value = Self::file(meta);
        value.size = 0;
        value.mode &= libc::S_IFMT;
        value
    }
}

struct Policy {
    roots: Vec<String>, excluded: Vec<String>, reserved: Vec<String>, targets: Vec<String>,
    entries: u64, file_bytes: u64, total_bytes: u64, depth: u64,
}

impl Policy {
    fn read(root: &Path) -> io::Result<Self> {
        let path = root.join("nix/engine-inputs.json");
        let mut bytes = Vec::new();
        #[cfg(target_os = "linux")]
        let input = {
            use std::os::unix::fs::OpenOptionsExt;
            OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW).open(path)?
        };
        #[cfg(not(target_os = "linux"))]
        let input = File::open(path)?;
        input.take(65537).read_to_end(&mut bytes)?;
        if bytes.len() > 65536 { return Err(invalid("engine-input policy exceeds capacity")); }
        let value: serde_json::Value = serde_json::from_slice(&bytes).map_err(|e| invalid(e.to_string()))?;
        let object = value.as_object().ok_or_else(|| invalid("invalid engine-input policy"))?;
        let keys: BTreeSet<_> = object.keys().map(String::as_str).collect();
        if keys != BTreeSet::from(["version", "roots", "excluded", "reserved", "targetRoots", "limits"])
            || value["version"] != 1 {
            return Err(invalid("unsupported engine-input policy"));
        }
        let paths = |key: &str, reserved: bool| -> io::Result<Vec<String>> {
            let rows = value[key].as_array().ok_or_else(|| invalid("malformed engine-input paths"))?;
            if !reserved && rows.is_empty() { return Err(invalid("empty engine-input paths")); }
            rows.iter().map(|row| {
                let name = row.as_str().ok_or_else(|| invalid("invalid engine-input path"))?;
                if (reserved && (name.is_empty() || name.contains('/')))
                    || (!reserved && name.split('/').any(|part| ["", ".", ".."].contains(&part))) {
                    return Err(invalid("engine-input paths must be relative"));
                }
                Ok(name.to_owned())
            }).collect()
        };
        let limits = value["limits"].as_object().ok_or_else(|| invalid("invalid engine-input limits"))?;
        if limits.keys().map(String::as_str).collect::<BTreeSet<_>>()
            != BTreeSet::from(["entries", "fileBytes", "totalBytes", "depth"]) {
            return Err(invalid("invalid engine-input limits"));
        }
        let limit = |name: &str| limits[name].as_u64().filter(|n| *n > 0)
            .ok_or_else(|| invalid("invalid engine-input limit"));
        Ok(Self { roots: paths("roots", false)?, excluded: paths("excluded", false)?,
            reserved: paths("reserved", true)?, targets: paths("targetRoots", false)?,
            entries: limit("entries")?, file_bytes: limit("fileBytes")?,
            total_bytes: limit("totalBytes")?, depth: limit("depth")? })
    }
}

fn beneath(parent: &[u8], child: &[u8]) -> bool {
    child == parent || (child.starts_with(parent) && child.get(parent.len()) == Some(&b'/'))
}

// Match Python's filesystem surrogateescape and JSON ensure_ascii, including
// non-UTF8 Unix names. Sort by Unicode code points as Python does, not OS bytes.
fn points(mut bytes: &[u8]) -> Vec<u32> {
    let mut result = Vec::new();
    while !bytes.is_empty() {
        match std::str::from_utf8(bytes) {
            Ok(text) => { result.extend(text.chars().map(u32::from)); break; }
            Err(error) => {
                let valid = error.valid_up_to();
                result.extend(std::str::from_utf8(&bytes[..valid]).unwrap().chars().map(u32::from));
                let count = error.error_len().unwrap_or(bytes.len() - valid);
                result.extend(bytes[valid..valid + count].iter().map(|byte| 0xdc00 + u32::from(*byte)));
                bytes = &bytes[valid + count..];
            }
        }
    }
    result
}

fn json_name(name: &[u32]) -> String {
    use std::fmt::Write;
    let mut out = String::from("\"");
    for &point in name {
        match point {
            0x22 => out.push_str("\\\""), 0x5c => out.push_str("\\\\"),
            8 => out.push_str("\\b"), 9 => out.push_str("\\t"), 10 => out.push_str("\\n"),
            12 => out.push_str("\\f"), 13 => out.push_str("\\r"),
            0x20..=0x7e => out.push(char::from_u32(point).unwrap()),
            0..=0xffff => { write!(out, "\\u{point:04x}").unwrap(); }
            _ => {
                let high = 0xd800 + ((point - 0x10000) >> 10);
                let low = 0xdc00 + ((point - 0x10000) & 0x3ff);
                write!(out, "\\u{high:04x}\\u{low:04x}").unwrap();
            }
        }
    }
    out.push('"');
    out
}

#[cfg(target_os = "linux")]
pub struct Snapshot {
    pub fingerprint: String,
    files: BTreeMap<PathBuf, (Stamp, [u8; 32])>,
    directories: Vec<(PathBuf, Stamp)>,
    policy: (PathBuf, Stamp),
}

#[cfg(target_os = "linux")]
impl Snapshot {
    pub fn capture(root: &Path) -> io::Result<Self> {
        let root = fs::canonicalize(root)?;
        if root.parent().is_none() || !root.is_dir() { return Err(invalid("invalid engine-input root")); }
        let policy_path = root.join("nix/engine-inputs.json");
        let policy_info = fs::symlink_metadata(&policy_path)?;
        if !policy_info.is_file() { return Err(invalid("engine-input policy must be a regular file")); }
        let policy_stamp = Stamp::file(&policy_info);
        let policy = Policy::read(&root)?;
        let mut capture = Capture { policy, entries: 0, bytes: 0, seen: BTreeSet::new(),
            rows: Vec::new(), snapshot: Self { fingerprint: String::new(), files: BTreeMap::new(), directories: Vec::new(), policy: (policy_path, policy_stamp) } };
        capture.walk(&root, &[], 0)?;
        if capture.policy.roots.iter().any(|path| !capture.seen.contains(path.as_bytes())) {
            return Err(invalid("required engine-input root is missing"));
        }
        capture.rows.sort_by(|a, b| a.0.cmp(&b.0));
        let mut hash = Sha256::new();
        hash.update(b"beam-lisp-engine-inputs-v1\0[");
        for (index, (_, row)) in capture.rows.iter().enumerate() {
            if index != 0 { hash.update(b","); }
            hash.update(row.as_bytes());
        }
        hash.update(b"]");
        capture.snapshot.fingerprint = format!("{:x}", hash.finalize());
        capture.snapshot.verify()?;
        Ok(capture.snapshot)
    }

    // A command may reuse only the digest of this exact captured pathname.
    // External paths and generated/non-selected files are read independently.
    pub fn digest(&self, path: &Path) -> Option<&[u8; 32]> {
        self.files.get(path).map(|(_, digest)| digest)
    }

    pub fn verify(&self) -> io::Result<()> {
        if Stamp::file(&fs::symlink_metadata(&self.policy.0)?) != self.policy.1 {
            return Err(invalid("engine-input policy changed during capture"));
        }
        for (path, (stamp, _)) in &self.files {
            if Stamp::file(&fs::symlink_metadata(path)?) != *stamp {
                return Err(invalid("engine input changed after capture"));
            }
        }
        for (path, stamp) in &self.directories {
            if Stamp::directory(&fs::symlink_metadata(path)?) != *stamp {
                return Err(invalid("engine input directory changed after capture"));
            }
        }
        Ok(())
    }
}

#[cfg(target_os = "linux")]
struct Capture {
    policy: Policy, entries: u64, bytes: u64, seen: BTreeSet<Vec<u8>>,
    rows: Vec<(Vec<u32>, String)>, snapshot: Snapshot,
}

#[cfg(target_os = "linux")]
impl Capture {
    fn walk(&mut self, directory: &Path, relative: &[u8], depth: u64) -> io::Result<()> {
        use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
        if depth > self.policy.depth { return Err(invalid("engine-input depth limit exceeded")); }
        let before = fs::symlink_metadata(directory)?;
        if !before.is_dir() { return Err(invalid("engine input directory changed type")); }
        let mut children = Vec::new();
        for entry in fs::read_dir(directory)? {
            self.entries += 1;
            if self.entries > self.policy.entries { return Err(invalid("engine-input entry limit exceeded")); }
            children.push(entry?);
        }
        children.sort_by_key(|entry| points(entry.file_name().as_encoded_bytes()));
        for entry in children {
            let name = entry.file_name();
            let name = name.as_encoded_bytes();
            let mut path = relative.to_vec();
            if !path.is_empty() { path.push(b'/'); }
            path.extend_from_slice(name);
            if self.policy.reserved.iter().any(|value| value.as_bytes() == name)
                || (name == b"target" && self.policy.targets.iter().any(|value| beneath(value.as_bytes(), &path)))
                || self.policy.excluded.iter().any(|value| beneath(value.as_bytes(), &path)) { continue; }
            if !self.policy.roots.iter().any(|value| beneath(value.as_bytes(), &path) || beneath(&path, value.as_bytes())) { continue; }
            let physical = entry.path();
            let info = fs::symlink_metadata(&physical)?;
            self.seen.insert(path.clone());
            let key = points(&path);
            let encoded = json_name(&key);
            if info.is_dir() {
                self.rows.push((key, format!("[{encoded},\"directory\"]")));
                self.walk(&physical, &path, depth + 1)?;
            } else if info.is_file() {
                if info.len() > self.policy.file_bytes { return Err(invalid("engine-input file size limit exceeded")); }
                let mut input = OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW).open(&physical)?;
                let stamp = Stamp::file(&input.metadata()?);
                if stamp != Stamp::file(&info) { return Err(invalid("engine input changed during open")); }
                let mut hash = Sha256::new();
                let mut buffer = [0u8; 65536];
                let mut count = 0u64;
                loop {
                    let read = input.read(&mut buffer)?;
                    if read == 0 { break; }
                    count += read as u64;
                    self.bytes += read as u64;
                    if count > self.policy.file_bytes || self.bytes > self.policy.total_bytes { return Err(invalid("engine-input byte limit exceeded")); }
                    hash.update(&buffer[..read]);
                }
                if stamp != Stamp::file(&input.metadata()?) || stamp != Stamp::file(&fs::symlink_metadata(&physical)?) || count != info.len() {
                    return Err(invalid("engine input changed while hashing"));
                }
                let digest: [u8; 32] = hash.finalize().into();
                let hex = digest.iter().map(|byte| format!("{byte:02x}")).collect::<String>();
                let executable = info.mode() & 0o100 != 0;
                self.rows.push((key, format!("[{encoded},\"regular\",{executable},\"{hex}\"]")));
                self.snapshot.files.insert(physical, (stamp, digest));
            } else { return Err(invalid("selected engine input must be a regular file or directory")); }
        }
        let stamp = Stamp::directory(&before);
        if stamp != Stamp::directory(&fs::symlink_metadata(directory)?) {
            return Err(invalid("engine input directory changed while hashing"));
        }
        self.snapshot.directories.push((directory.to_owned(), stamp));
        Ok(())
    }
}

#[cfg(not(target_os = "linux"))]
pub struct Snapshot { pub fingerprint: String }

#[cfg(not(target_os = "linux"))]
impl Snapshot {
    pub fn capture(_: &Path) -> io::Result<Self> { Err(invalid("checkout engine capture requires Linux")) }
    pub fn digest(&self, _: &Path) -> Option<&[u8; 32]> { None }
    pub fn verify(&self) -> io::Result<()> { Ok(()) }
}
