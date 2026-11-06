// builder.rs — getting a build into the store: fetch a release, or build a tree.
// (included via include! into launcher.rs — no //! inner docs allowed here)
//
//   self_update(store, spec, me)  the verb `bl self-update [SPEC]`
//   build_tree(store, tree, me)   seal a source tree with `bin/bl self-build`
//   fetch_release(store, tag)     download + verify a GitHub release asset
//
// Nothing here is on the hot path: it runs when a build is missing, from a
// hook, or by hand. It may run git and curl; the resolver may not.
//
// ONE BUILD AT A TIME on the machine (`BuildLock`): a build holds ~1.3 GB per
// compiler process on a host already under memory pressure, and `self-build`
// stages into one fixed directory.

use std::process::Stdio;

/// The GitHub repository releases come from (`:repo` in the config).
pub fn release_repo() -> String {
    config_literal("repo").unwrap_or_else(|| "undefine-org/enchant".to_string())
}

/// This platform's release asset name, as `.github/workflows/release.yml`
/// names them.
pub fn asset_name() -> Option<&'static str> {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("linux", "x86_64") => Some("bl-linux-x86_64"),
        ("linux", "aarch64") => Some("bl-linux-aarch64"),
        ("macos", "aarch64") => Some("bl-macos-arm64"),
        ("macos", "x86_64") => Some("bl-macos-x86_64"),
        _ => None,
    }
}

fn cache_dir() -> PathBuf {
    std::env::var("XDG_CACHE_HOME")
        .ok()
        .filter(|x| !x.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| expand_home("~/.cache"))
        .join("bl")
}

fn say(msg: &str) {
    eprintln!("bl: {msg}");
}

/// Every failure a verb returns starts with `bl: `, once.
fn bl_err(msg: String) -> String {
    if msg.starts_with("bl:") { msg } else { format!("bl: {msg}") }
}

// ── the machine-wide build lock ─────────────────────────────────────────────

pub struct BuildLock {
    // Keep the open kernel object for the whole build. The readable PID is
    // diagnostic data; it never authorizes acquisition or stale-lock removal.
    _file: std::fs::File,
    followers: PathBuf,
    diagnostic: PathBuf,
    owner: String,
}

impl BuildLock {
    /// One permanent inode serializes cooperating bootstrap builders, before
    /// any BEAM/NIF exists. Do not unlink it during release or crash recovery.
    /// Drain surviving external commands before admitting a replacement build.
    pub fn take(store: &Store) -> Result<BuildLock, String> {
        use std::fs::{OpenOptions, TryLockError};
        use std::io::Write;
        let locks = store.meta().join("locks");
        std::fs::create_dir_all(&locks)
            .map_err(|e| format!("cannot prepare build custody {}: {e}", locks.display()))?;
        let anchor = locks.join("build.kernel");
        let file = OpenOptions::new().read(true).write(true).create(true).truncate(false)
            .open(&anchor).map_err(|e| format!("cannot open build custody {}: {e}", anchor.display()))?;
        match file.try_lock() {
            Ok(()) => {}
            Err(TryLockError::WouldBlock) => {
                say("another bootstrap build holds kernel custody; waiting for it");
                file.lock().map_err(|e| format!("cannot acquire build custody {}: {e}", anchor.display()))?;
            }
            Err(TryLockError::Error(e)) => return Err(format!("cannot acquire build custody {}: {e}", anchor.display())),
        }
        let followers = locks.join("build.kernel.followers");
        let barrier = OpenOptions::new().read(true).write(true).create(true).truncate(false)
            .open(&followers).map_err(|e| format!("cannot open build followers: {e}"))?;
        match barrier.try_lock() {
            Ok(()) => {},
            Err(TryLockError::WouldBlock) => {
                say("surviving bootstrap commands hold child custody; waiting for them");
                barrier.lock().map_err(|e| format!("cannot drain build followers: {e}"))?;
            }
            Err(TryLockError::Error(e)) => return Err(format!("cannot drain build followers: {e}")),
        }
        let diagnostic = locks.join("build");
        let owner = std::process::id().to_string();
        let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| e.to_string())?.as_nanos();
        let temporary = locks.join(format!("build.writing-{owner}-{nonce}"));
        let publish = (|| -> std::io::Result<()> {
            let mut output = OpenOptions::new().write(true).create_new(true).open(&temporary)?;
            output.write_all(owner.as_bytes())?;
            drop(output);
            // Replace an old diagnostic symlink; never write through it.
            std::fs::rename(&temporary, &diagnostic)
        })();
        if let Err(error) = publish {
            let _ = std::fs::remove_file(&temporary);
            return Err(format!("cannot publish build owner {}: {error}", diagnostic.display()));
        }
        drop(barrier);
        Ok(BuildLock { _file: file, followers, diagnostic, owner })
    }

    /// Join the already-admitted build before spawning. Only the forked child's
    /// descriptor loses CLOEXEC; unrelated concurrent spawns never inherit it.
    /// Descendants must preserve this descriptor when they exec/fork again.
    fn prepare_command(&self, command: &mut Command) -> Result<(), String> {
        #[cfg(unix)] {
            use std::fs::OpenOptions;
            use std::os::fd::AsRawFd;
            use std::os::unix::process::CommandExt;
            extern "C" {
                #[link_name = "fcntl"]
                fn custody_fcntl(fd: i32, command: i32, ...) -> i32;
            }
            let follower = OpenOptions::new().read(true).write(true).open(&self.followers)
                .map_err(|e| format!("cannot open child build custody: {e}"))?;
            follower.try_lock_shared().map_err(|e| format!("cannot admit child build custody: {e}"))?;
            // File owns the descriptor captured by Command, so it cannot be
            // reused before spawn. In the post-fork closure call only fcntl:
            // no allocation, locks, pathname lookup, or authority reconstruction.
            unsafe {
                command.pre_exec(move || {
                    const F_SETFD: i32 = 2;
                    if custody_fcntl(follower.as_raw_fd(), F_SETFD, 0_i32) == -1 {
                        Err(std::io::Error::last_os_error())
                    } else { Ok(()) }
                });
            }
            Ok(())
        }
        #[cfg(not(unix))] {
            let _ = command;
            Err("external build custody is not implemented on this target".into())
        }
    }
}

impl Drop for BuildLock {
    fn drop(&mut self) {
        if std::fs::read_to_string(&self.diagnostic).ok().as_deref() == Some(self.owner.as_str()) {
            let _ = std::fs::remove_file(&self.diagnostic);
        }
        // The descriptor drops after diagnostic cleanup. Its inode stays.
    }
}

// ── running things ──────────────────────────────────────────────────────────

/// Minutes one build step may run before it is killed (`BL_BUILD_TIMEOUT_MIN`).
/// A self-build compiles every tier, so a namespace that DOES something at load
/// (a server's `(run)` at top level) parks it forever; measured: a step that
/// normally takes ~6 minutes sat serving an MCP endpoint instead.
const DEFAULT_BUILD_TIMEOUT_MIN: u64 = 45;

/// Run `cmd`, appending its output to `log`. Ok on exit 0; else the last lines
/// of the log, so a failure names its own cause. A step past its deadline is
/// killed (with its process group) and reported as such.
fn run_logged(mut cmd: Command, log: &Path, what: &str, custody: &BuildLock) -> Result<(), String> {
    use std::io::Write;
    custody.prepare_command(&mut cmd)?;
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log)
        .map_err(|e| format!("cannot open log {}: {e}", log.display()))?;
    let _ = writeln!(f, "\n=== {what}");
    let out = f.try_clone().map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0);
    }
    let mut child = cmd
        .stdin(Stdio::null())
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(f))
        .spawn()
        .map_err(|e| format!("{what}: could not start: {e}"))?;
    let limit = std::time::Duration::from_secs(60 * hours_env("BL_BUILD_TIMEOUT_MIN", DEFAULT_BUILD_TIMEOUT_MIN));
    let started = std::time::Instant::now();
    let status = loop {
        match child.try_wait().map_err(|e| e.to_string())? {
            Some(s) => break s,
            None if started.elapsed() > limit => {
                #[cfg(unix)]
                {
                    let _ = Command::new("kill").args(["-9", &format!("-{}", child.id())]).status();
                }
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!(
                    "{what} ran past {} minutes and was stopped (BL_BUILD_TIMEOUT_MIN); log {}",
                    limit.as_secs() / 60,
                    log.display()
                ));
            }
            None => std::thread::sleep(std::time::Duration::from_millis(500)),
        }
    };
    if status.success() {
        Ok(())
    } else {
        let text = std::fs::read_to_string(log).unwrap_or_default();
        let tail: Vec<&str> = text.lines().rev().take(15).collect();
        let tail: Vec<&str> = tail.into_iter().rev().collect();
        Err(format!("{what} failed ({status}); log {}:\n{}", log.display(), tail.join("\n")))
    }
}

/// A `git -C dir` command that names its repository by `dir` alone: git's
/// per-invocation variables (set when we run under a hook) would otherwise
/// point it at the worktree that fired the hook, index and all.
fn git_at(dir: &Path) -> Command {
    let mut cmd = Command::new("git");
    cmd.arg("-C").arg(dir);
    scrub_git_env(&mut cmd);
    cmd
}

fn git_out(dir: &Path, args: &[&str]) -> Option<String> {
    let o = git_at(dir).args(args).stderr(Stdio::null()).output().ok()?;
    o.status.success().then(|| String::from_utf8_lossy(&o.stdout).trim().to_string())
}

/// The main worktree of the repository `tree` belongs to (the parent of the
/// common git dir).
pub fn main_worktree(tree: &Path) -> Option<PathBuf> {
    let common = git_out(tree, &["rev-parse", "--path-format=absolute", "--git-common-dir"])?;
    let p = PathBuf::from(common);
    (p.file_name()? == ".git").then(|| p.parent().map(Path::to_path_buf)).flatten()
}

/// Copy the gitignored PINNED assets a build needs (`priv/z3`, `priv/embed`)
/// from `from` into `tree` when `tree` has none: downloaded artefacts, the same
/// bytes for every commit. Reflinked where the filesystem can.
///
/// `priv/native` is NOT one of them: those `.so` files are built from
/// `native/*` of the commit being built, and a copy is the checkout's crate
/// source, not this commit's (measured: a `latest` seeded from a checkout with
/// an edited `datom_fjall` crate shipped that crate's NIF and died at load with
/// `:nif_not_loaded`). `build_natives` compiles them from the tree instead.
fn seed_assets(from: &Path, tree: &Path, log: &Path, custody: &BuildLock) -> Result<(), String> {
    if from == tree {
        return Ok(());
    }
    for rel in ["priv/z3", "priv/embed"] {
        let (src, dst) = (from.join(rel), tree.join(rel));
        let empty = std::fs::read_dir(&dst).map(|mut d| d.next().is_none()).unwrap_or(true);
        if src.is_dir() && empty {
            let _ = std::fs::create_dir_all(&dst);
            let mut cmd = Command::new("cp");
            cmd.arg("-a").arg("--reflink=auto").arg(format!("{}/.", src.display())).arg(&dst);
            run_logged(cmd, log, &format!("seed {rel} from {}", tildify(from)), custody)?;
        }
    }
    Ok(())
}

// The preboot publisher joins claim/artifact-scope's kernel protocol without
// loading a BEAM/NIF. These descriptors grant filesystem exclusion only.
struct NativePublication {
    destination: PathBuf,
    _writer: std::fs::File,
    _followers: std::fs::File,
}

impl NativePublication {
    fn take(destination: &Path) -> Result<Self, String> {
        use std::fs::{OpenOptions, TryLockError};
        let name = destination.file_name().ok_or("native destination needs a filename")?;
        // Resolve directory aliases, but replace a destination symlink itself.
        let parent = std::fs::canonicalize(destination.parent().filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."))).map_err(|e| e.to_string())?;
        let scope = parent.join(".bl/artifact-custody").join(name);
        std::fs::create_dir_all(&scope).map_err(|e| e.to_string())?;
        let scope = std::fs::canonicalize(scope).map_err(|e| e.to_string())?;
        let base = scope.file_name().ok_or("native custody needs a filename")?;
        let anchors = scope.parent().ok_or("native custody needs a parent")?
            .join(if base == ".bl" { ".bl-locks" } else { ".bl" }).join("locks");
        std::fs::create_dir_all(&anchors).map_err(|e| e.to_string())?;
        let anchor = anchors.join(scope.file_name().ok_or("native custody needs a filename")?);
        let lock = |path: &Path| -> Result<std::fs::File, String> {
            let file = OpenOptions::new().read(true).write(true).create(true).truncate(false)
                .open(path).map_err(|e| format!("cannot open native publication custody: {e}"))?;
            match file.try_lock() {
                Ok(()) => Ok(file),
                Err(TryLockError::WouldBlock) => Err("native publication custody held".into()),
                Err(TryLockError::Error(e)) => Err(format!("cannot acquire native publication custody: {e}")),
            }
        };
        let writer = lock(&anchor)?;
        let mut follower_name = anchor.as_os_str().to_os_string();
        follower_name.push(".followers");
        let followers = lock(Path::new(&follower_name))?;
        // No old Source follower may enter after this publisher releases. Keep
        // the follower barrier through invalidation and destination publication.
        match std::fs::remove_file(scope.join(".claim")) {
            Ok(()) => {},
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {},
            Err(e) => return Err(format!("cannot invalidate native publication cohort: {e}")),
        }
        Ok(Self { destination: parent.join(name), _writer: writer, _followers: followers })
    }
}

fn publish_native_artifact(source: &Path, destination: &Path) -> Result<(), String> {
    use std::fs::OpenOptions;
    use std::io::Write;
    let custody = NativePublication::take(destination)?;
    let destination = &custody.destination;
    let bytes = std::fs::read(source).map_err(|e| e.to_string())?;
    if std::fs::symlink_metadata(destination).is_ok_and(|m| m.is_file())
        && std::fs::read(destination).is_ok_and(|installed| installed == bytes) {
        return Ok(());
    }
    let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| e.to_string())?.as_nanos();
    let temporary = destination.with_file_name(format!("{}.tmp-{}-{nonce}",
        destination.file_name().ok_or("native destination needs a filename")?.to_string_lossy(), std::process::id()));
    // Never follow or truncate a preexisting temporary. Only remove a file we
    // actually created; create_new failure leaves somebody else's bytes intact.
    let mut output = OpenOptions::new().write(true).create_new(true).open(&temporary).map_err(|e| e.to_string())?;
    let publish = (|| -> std::io::Result<()> {
        output.write_all(&bytes)?;
        output.set_permissions(std::fs::metadata(source)?.permissions())?;
        drop(output);
        std::fs::rename(&temporary, destination)
    })();
    if let Err(error) = publish {
        let _ = std::fs::remove_file(&temporary);
        return Err(error.to_string());
    }
    Ok(())
}

/// Select a verified immutable product under the existing destination admission.
/// Old mapped libraries retain their immutable inodes; each request keeps a root.
fn publish_native_reference(source: &Path, destination: &Path) -> Result<(), String> {
    #[cfg(unix)] {
        let custody = NativePublication::take(destination)?;
        let destination = &custody.destination;
        if std::fs::read_link(destination).is_ok_and(|path| path == source) { return Ok(()); }
        let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
        let temporary = destination.with_extension(format!("nix-{}-{nonce}", std::process::id()));
        std::os::unix::fs::symlink(source, &temporary).map_err(|e| e.to_string())?;
        let result = std::fs::rename(&temporary, destination).map_err(|e| e.to_string());
        if result.is_err() { let _ = std::fs::remove_file(&temporary); }
        result
    }
    #[cfg(not(unix))] {
        let _ = (source, destination);
        Err("immutable native selection is unsupported on this target".into())
    }
}

/// Prepare every declared native crate through the pinned immutable recipe.
/// Cargo is confined to Nix workers; unsupported environments fail explicitly.
fn build_natives(tree: &Path, _log: &Path, custody: &BuildLock) -> Result<(), String> {
    if std::env::var("BL_NATIVE_PROVIDER").is_ok_and(|provider| provider != "nix") {
        return Err("native production requires Nix; local providers are unsupported".into());
    }
    let native = tree.join("native");
    let dest = tree.join("priv/native");
    std::fs::create_dir_all(&dest).map_err(|e| e.to_string())?;
    let Ok(rd) = std::fs::read_dir(&native) else { return Ok(()) };
    let mut crates: Vec<PathBuf> = rd.flatten().map(|e| e.path()).filter(|p| p.join("Cargo.toml").is_file()).collect();
    crates.sort();
    for dir in crates {
        let name = dir.file_name().unwrap().to_string_lossy().into_owned();
        let library = nix_artifact::prepare(tree, &dir, &name, custody)?;
        publish_native_reference(&library, &dest.join(format!("{name}.so")))?;
    }
    Ok(())
}

/// Require Cargo's successful, read-only answer. A guessed target can publish
/// an unrelated old library after failed metadata discovery.
fn cargo_target_dir(dir: &Path, custody: &BuildLock) -> Result<PathBuf, String> {
    let mut command = Command::new("cargo");
    command
        .args(["metadata", "--locked", "--format-version", "1", "--no-deps", "--manifest-path"])
        .arg(dir.join("Cargo.toml"));
    custody.prepare_command(&mut command)?;
    let output = command.output().map_err(|e| format!("native Cargo metadata could not start for {}: {e}", dir.display()))?;
    if !output.status.success() {
        return Err(format!("native Cargo metadata failed for {} ({}): {}",
            dir.display(), output.status, String::from_utf8_lossy(&output.stderr).trim()));
    }
    let metadata: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("native Cargo metadata was not valid JSON for {}: {e}", dir.display()))?;
    let target = metadata.get("target_directory").and_then(serde_json::Value::as_str)
        .map(PathBuf::from).filter(|p| p.is_absolute())
        .ok_or_else(|| format!("native Cargo metadata omitted an absolute target_directory for {}", dir.display()))?;
    Ok(target)
}

fn tree_bl(tree: &Path, args: &[&str]) -> Command {
    // The in-tree `bin/bl` is a shell script that starts one fresh VM; it has no
    // transport to choose, so it is given no transport flag. (`--cold` here made
    // every tree whose CLI predates the flag, main's among them, refuse to build.)
    let mut cmd = Command::new(tree.join(LAUNCHER_REL));
    cmd.args(args)
        .current_dir(tree)
        .env_remove("BL_BUILD_ID")
        .env_remove("BL_USE");
    cmd
}

// ── building a tree ─────────────────────────────────────────────────────────

pub struct Built {
    pub id: String,
    pub key: Option<String>,
    pub commit: Option<String>,
}

/// Build the source tree at `tree` into the store, sealed with `launcher` (a
/// payload-less launcher: the PATH `bl` itself), and record it as the tree's
/// bleeding-edge and under its source key. `extra` are more pointers to move to
/// it (`channels/latest`).
pub fn build_tree(store: &Store, tree: &Path, launcher: &Path, extra: &[&str]) -> Result<Built, String> {
    let custody = BuildLock::take(store)?;
    let before = stamp(tree);

    // The lock was waited for: another build may have produced exactly this.
    if let Some(p) = store.read(&store.bleeding_edge_key(&tree_id(tree))) {
        if p.get("stamp") == Some(before.as_str()) && store.has(&p.build) {
            for rel in extra {
                store.write(rel, &p).map_err(|e| e.to_string())?;
            }
            say(&format!("{} is already built as {}", tildify(tree), p.build));
            return Ok(Built { id: p.build.clone(), key: p.get("key").map(str::to_string), commit: p.get("commit").map(str::to_string) });
        }
    }

    let logs = store.meta().join("logs");
    std::fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    let log = logs.join(format!("{}.log", tree_id(tree)));
    let _ = std::fs::write(&log, "");
    say(&format!("building {} (several minutes; log {})", tildify(tree), tildify(&log)));

    if let Some(main) = main_worktree(tree) {
        seed_assets(&main, tree, &log, &custody)?;
    }
    let incoming = store.meta().join("incoming");
    std::fs::create_dir_all(&incoming).map_err(|e| e.to_string())?;
    let out = incoming.join(format!("build-{}.drop", std::process::id()));
    let scratch = cache_dir().join("scratch");

    build_natives(tree, &log, &custody)?;
    run_logged(tree_bl(tree, &["deps", "fetch"]), &log, "bl deps fetch", &custody)?;
    run_logged(tree_bl(tree, &["deps", "compile"]), &log, "bl deps compile", &custody)?;
    let seal = tree_bl(
        tree,
        &[
            "self-build",
            "--bin",
            &launcher.to_string_lossy(),
            "--out",
            &out.to_string_lossy(),
            "--scratch",
            &scratch.to_string_lossy(),
        ],
    );
    run_logged(seal, &log, "bl self-build", &custody)?;

    let id = publish_drop(store, &out)?;
    let after = stamp(tree);
    let payload = store.payload(&id);
    let key = build_info_field(&payload, "source-key");
    let commit = build_info_field(&payload, "commit");

    let mut p = Pointer::new(&id)
        .with("root", &tree.to_string_lossy())
        .with("branch", &head_branch(tree).unwrap_or_default())
        .with("commit", commit.as_deref().unwrap_or(""))
        .with("key", key.as_deref().unwrap_or(""));
    if before == after {
        p = p.with("stamp", &before);
    } else {
        say("the tree changed while it was building; this build is kept, and the tree runs from source until it is built again");
    }
    store.write(&store.bleeding_edge_key(&tree_id(tree)), &p).map_err(|e| e.to_string())?;
    if let Some(k) = &key {
        store.write(&store.source_key(k), &p).map_err(|e| e.to_string())?;
    }
    for rel in extra {
        store.write(rel, &p).map_err(|e| e.to_string())?;
    }
    say(&format!("built {} → {id}", tildify(tree)));
    Ok(Built { id, key, commit })
}

/// Verify and extract the sealed drop at `file` into the store, then remove the
/// file. Returns its build id.
pub fn publish_drop(store: &Store, file: &Path) -> Result<String, String> {
    let t = try_read_trailer(file).ok_or_else(|| format!("{} is not a drop", file.display()))?;
    let id = sha8_of(&t);
    if !payload_ready(&store.payload(&id)) {
        extract_checked(file, &t, &store.payload(&id))?;
    }
    let _ = std::fs::remove_file(file);
    Ok(id)
}

fn extract_checked(file: &Path, t: &Trailer, dest: &Path) -> Result<(), String> {
    use std::io::{Read, Seek, SeekFrom};
    let mut f = std::fs::File::open(file).map_err(|e| e.to_string())?;
    f.seek(SeekFrom::Start(t.offset)).map_err(|e| e.to_string())?;
    let mut payload = vec![0u8; t.len as usize];
    f.read_exact(&mut payload).map_err(|e| e.to_string())?;
    let got = sha256_hex(&payload);
    let want = hex(&t.sha256);
    if got != want {
        return Err(format!("{}: payload digest {got} does not match its trailer {want}", file.display()));
    }
    extract_tar_gz(&payload, dest).map_err(|e| format!("extracting {}: {e}", file.display()))
}

/// Build commit `sha` of the repository at `source` in a detached worktree
/// under the cache (reused for the same commit).
pub fn build_commit(store: &Store, source: &Path, sha: &str, launcher: &Path, extra: &[&str]) -> Result<Built, String> {
    let full = git_out(source, &["rev-parse", "--verify", &format!("{sha}^{{commit}}")])
        .ok_or_else(|| format!("{} has no commit {sha} (fetch it first)", tildify(source)))?;
    let tree = cache_dir().join("build-trees").join(&full[..12]);
    if !tree.join(".git").exists() {
        let _ = std::fs::create_dir_all(tree.parent().unwrap());
        let mut cmd = git_at(source);
        cmd.args(["worktree", "add", "--detach", "--force"]).arg(&tree).arg(&full);
        let log = cache_dir().join("worktree-add.log");
        let _ = std::fs::create_dir_all(cache_dir());
        let custody = BuildLock::take(store)?;
        run_logged(cmd, &log, &format!("git worktree add {}", &full[..12]), &custody)?;
    }
    let tree = std::fs::canonicalize(&tree).unwrap_or(tree);
    build_tree(store, &tree, launcher, extra)
}

// ── releases ────────────────────────────────────────────────────────────────

fn curl_text(url: &str) -> Result<String, String> {
    let o = Command::new("curl")
        .args(["-fsSL", "--retry", "2", "-H", "Accept: application/vnd.github+json", url])
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("curl could not start: {e}"))?;
    if o.status.success() {
        Ok(String::from_utf8_lossy(&o.stdout).into_owned())
    } else {
        Err(format!("GET {url}: {}", String::from_utf8_lossy(&o.stderr).trim()))
    }
}

/// The value of the first `"key": "value"` in a JSON text (a scan: the
/// launcher carries no JSON parser, and these are flat string fields).
pub fn json_string(text: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let at = text.find(&needle)? + needle.len();
    let rest = text[at..].trim_start().strip_prefix(':')?.trim_start().strip_prefix('"')?;
    Some(rest[..rest.find('"')?].to_string())
}

/// Download release `tag` (None = the newest non-prerelease) for this platform,
/// verify it against its published `.sha256`, extract it, and record it under
/// `tags/<tag>`. Returns (tag, build id). An asset already stored with the same
/// digest is not downloaded again.
pub fn fetch_release(store: &Store, tag: Option<&str>) -> Result<(String, String), String> {
    let repo = release_repo();
    let asset = asset_name().ok_or("no release asset is published for this platform")?;
    let api = match tag {
        None => format!("https://api.github.com/repos/{repo}/releases/latest"),
        Some(t) => format!("https://api.github.com/repos/{repo}/releases/tags/{t}"),
    };
    let json = curl_text(&api)?;
    let tag = json_string(&json, "tag_name").ok_or_else(|| format!("{api}: no tag_name in the answer"))?;
    let base = format!("https://github.com/{repo}/releases/download/{tag}");
    let sums = curl_text(&format!("{base}/{asset}.sha256"))?;
    let want = sums.split_whitespace().next().unwrap_or("").to_ascii_lowercase();
    if want.len() != 64 {
        return Err(format!("{base}/{asset}.sha256 does not hold a sha256"));
    }

    if let Some(p) = store.read(&store.tag_key(&tag)) {
        if p.get("asset-sha256") == Some(want.as_str()) && store.has(&p.build) {
            return Ok((tag, p.build));
        }
    }

    let incoming = store.meta().join("incoming");
    std::fs::create_dir_all(&incoming).map_err(|e| e.to_string())?;
    let file = incoming.join(format!("{asset}-{tag}.{}", std::process::id()));
    say(&format!("downloading {repo} {tag} ({asset})"));
    let st = Command::new("curl")
        .args(["-fL", "--retry", "2", "--progress-bar", "-o"])
        .arg(&file)
        .arg(format!("{base}/{asset}"))
        .stdin(Stdio::null())
        .status()
        .map_err(|e| format!("curl could not start: {e}"))?;
    if !st.success() {
        let _ = std::fs::remove_file(&file);
        return Err(format!("downloading {base}/{asset} failed ({st})"));
    }
    let got = std::fs::read(&file).map(|b| sha256_hex(&b)).map_err(|e| e.to_string())?;
    if got != want {
        let _ = std::fs::remove_file(&file);
        return Err(format!("{asset} {tag}: sha256 {got} does not match the published {want}"));
    }
    let id = publish_drop(store, &file)?;
    let p = Pointer::new(&id).with("tag", &tag).with("asset-sha256", &want);
    store.write(&store.tag_key(&tag), &p).map_err(|e| e.to_string())?;
    say(&format!("{tag} → {id}"));
    Ok((tag, id))
}

// ── the verb ────────────────────────────────────────────────────────────────

/// The beam-lisp checkout builds come from: the config's `:source`, else the
/// main worktree of the source tree `cwd` is in.
pub fn source_for(cwd: &Path) -> Option<PathBuf> {
    source_repo().or_else(|| source_tree(cwd).and_then(|t| main_worktree(&t)))
}

/// `bl self-update [SPEC]`: put SPEC's build in the store (and move its
/// channel). With no SPEC: `stable`, then `latest`.
pub fn self_update(store: &Store, spec: Option<&str>, me: &Path, cwd: &Path) -> Result<String, String> {
    let Some(spec) = spec else {
        let s = self_update(store, Some("stable"), me, cwd)?;
        let l = self_update(store, Some("latest"), me, cwd).unwrap_or_else(|e| format!("latest: {e}"));
        return Ok(format!("stable {s}; latest {l}"));
    };
    match parse_spec(spec)? {
        Spec::Channel(c) if c == "stable" => {
            let (tag, id) = fetch_release(store, None)?;
            store.write(&store.channel_key("stable"), &Pointer::new(&id).with("tag", &tag)).map_err(|e| e.to_string())?;
            Ok(format!("{id} ({tag})"))
        }
        Spec::Channel(_) => match source_repo() {
            // A machine with the source checkout: `latest` is ITS main, built here.
            Some(src) => {
                let latest = store.channel_key("latest");
                let b = build_commit(store, &src, "main", me, &[latest.as_str()])?;
                Ok(format!("{} (main {})", b.id, b.commit.as_deref().map(|c| &c[..8.min(c.len())]).unwrap_or("?")))
            }
            // Without one: the rolling `latest` pre-release CI publishes from main.
            None => {
                let (_, id) = fetch_release(store, Some("latest"))?;
                store.write(&store.channel_key("latest"), &Pointer::new(&id).with("tag", "latest")).map_err(|e| e.to_string())?;
                Ok(id)
            }
        },
        Spec::Tag(t) => fetch_release(store, Some(&t)).map(|(_, id)| id),
        Spec::Commit(c) => {
            let src = source_for(cwd).ok_or("building a commit needs the beam-lisp checkout: set :source in the config")?;
            build_commit(store, &src, &c, me, &[]).map(|b| b.id)
        }
        Spec::BleedingEdge(which) => {
            let tree = match which {
                None => source_tree(cwd).or_else(source_repo),
                Some(x) => Some(std::fs::canonicalize(expand_home(&x)).map_err(|e| format!("{x}: {e}"))?),
            }
            .ok_or("no beam-lisp tree to build: run inside one, or name it (bleeding-edge:DIR)")?;
            build_tree(store, &tree, me, &[]).map(|b| b.id)
        }
        Spec::Build(id) => {
            if store.has(&id) { Ok(id) } else { Err(format!("build {id} is not stored and cannot be fetched by id")) }
        }
        Spec::Path(p) => {
            let tmp = store.meta().join("incoming").join(format!("import-{}", std::process::id()));
            let _ = std::fs::create_dir_all(tmp.parent().unwrap());
            std::fs::copy(&p, &tmp).map_err(|e| format!("{}: {e}", p.display()))?;
            let id = publish_drop(store, &tmp)?;
            index_imported_source(store, &id)?;
            Ok(id)
        }
    }
}

/// A verified imported build should satisfy the same project commit pin as a
/// locally built one. Otherwise importing an already sealed runtime triggers
/// another full compiler/native build on the first ordinary app command.
/// Dirty source keys remain distinct and never satisfy a clean commit pin.
fn index_imported_source(store: &Store, id: &str) -> Result<(), String> {
    let payload = store.payload(id);
    let Some(key) = build_info_field(&payload, "source-key") else { return Ok(()) };
    let (commit, diff) = key.split_once('+').map_or((key.as_str(), None), |(c,d)| (c,Some(d)));
    let hex = |value: &str, len: usize| value.len() == len && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b));
    if !hex(commit, 40) || diff.is_some_and(|d| !hex(d, 12))
        || build_info_field(&payload, "commit").as_deref() != Some(commit) {
        return Err("imported build has inconsistent source provenance; no source pointer published".into());
    }
    let pointer = Pointer::new(id).with("key", &key).with("commit", commit);
    store.write(&store.source_key(&key), &pointer).map_err(|e| e.to_string())
}

// ── installing the launcher ─────────────────────────────────────────────────

/// Set `:key "value"` in the config text: replace it where it stands, else add
/// it before the closing brace (or start a map).
pub fn config_set(text: &str, key: &str, value: &str) -> String {
    let needle = format!(":{key} \"");
    if let Some(at) = text.find(&needle) {
        let start = at + needle.len();
        if let Some(end) = text[start..].find('"') {
            return format!("{}{}{}", &text[..start], value, &text[start + end..]);
        }
    }
    match text.rfind('}') {
        Some(close) => format!("{}\n :{key} \"{value}\"{}", text[..close].trim_end(), &text[close..]),
        None => format!(";; ~/.config/bl/config.bl — the PATH launcher's settings (read by scan, never evaluated).\n{{:{key} \"{value}\"}}\n"),
    }
}

/// `bl self-install [--source DIR]`: copy this launcher to `~/.local/bin/bl`
/// (`BL_INSTALL_BIN` overrides), atomically, replacing whatever was there — a
/// symlink into some checkout, or a drop someone copied. Records `:source`.
pub fn self_install(me: &Path, args: &[String], cwd: &Path) -> Result<String, String> {
    let dest = std::env::var("BL_INSTALL_BIN").map(PathBuf::from).unwrap_or_else(|_| expand_home("~/.local/bin/bl"));
    let mut report = vec![];
    let was = match std::fs::symlink_metadata(&dest) {
        Ok(m) if m.file_type().is_symlink() => Some(format!("a symlink to {}", std::fs::read_link(&dest).map(|p| p.display().to_string()).unwrap_or_default())),
        Ok(_) if try_read_trailer(&dest).is_some() => Some("a drop (a whole build copied onto PATH)".to_string()),
        Ok(_) => Some("an earlier launcher".to_string()),
        Err(_) => None,
    };
    if std::fs::canonicalize(&dest).ok() != std::fs::canonicalize(me).ok() {
        let tmp = dest.with_extension(format!("tmp-{}", std::process::id()));
        std::fs::create_dir_all(dest.parent().unwrap()).map_err(|e| e.to_string())?;
        std::fs::copy(me, &tmp).map_err(|e| format!("copy to {}: {e}", tmp.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o755));
        }
        std::fs::rename(&tmp, &dest).map_err(|e| format!("install {}: {e}", dest.display()))?;
        report.push(format!("installed the launcher at {}{}", tildify(&dest), was.map(|w| format!(" (replacing {w})")).unwrap_or_default()));
    } else {
        report.push(format!("{} is already this launcher", tildify(&dest)));
    }

    let source = match args.iter().position(|a| a == "--source") {
        Some(i) => Some(std::fs::canonicalize(expand_home(args.get(i + 1).ok_or("--source needs a directory")?)).map_err(|e| e.to_string())?),
        None => source_tree(cwd).and_then(|t| main_worktree(&t)),
    };
    if let Some(src) = source {
        let path = config_path();
        let text = std::fs::read_to_string(&path).unwrap_or_default();
        write_atomic(&path, config_set(&text, "source", &src.to_string_lossy()).as_bytes()).map_err(|e| e.to_string())?;
        report.push(format!("builds come from {} (:source in {})", tildify(&src), tildify(&path)));
    }
    Ok(report.join("\n"))
}

#[cfg(test)]
mod builder_tests {
    use super::*;

    fn source_fixture(label: &str, key: Option<&str>, commit: &str) -> (Store, PathBuf, String) {
        use std::io::Write;
        let root = std::env::temp_dir().join(format!("drop-import-{label}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let store = Store { root: root.join("store") };
        let info = match key {
            Some(k) => format!("{{:commit \"{commit}\" :source-key \"{k}\"}}"),
            None => format!("{{:commit \"{commit}\"}}"),
        };
        let mut ar = tar::Builder::new(flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default()));
        for (path, body) in [(BUILD_INFO_FILE, info.as_bytes()), (LAUNCHER_REL, b"#!/bin/sh\nexit 0\n".as_slice()),
            ("releases/start_erl.data", b"17.0 0.1.0\n".as_slice()),
            ("releases/0.1.0/elixir", b"elixir".as_slice()),
            ("erts-17.0/bin/erl", b"erl".as_slice()), ("erts-17.0/bin/beam.smp", b"beam".as_slice()),
            ("lib/beam_lisp-0.1.0/ebin/beam_lisp.app", b"app".as_slice())] {
            let mut h = tar::Header::new_gnu();
            h.set_size(body.len() as u64); h.set_mode(0o755); h.set_cksum();
            ar.append_data(&mut h, path, body).unwrap();
        }
        let bytes = ar.into_inner().unwrap().finish().unwrap();
        let digest: [u8;32] = sha256_bytes(&bytes).try_into().unwrap();
        let file = root.join("fixture.drop");
        let mut out = std::fs::File::create(&file).unwrap();
        out.write_all(&bytes).unwrap();
        out.write_all(&encode_trailer(0, bytes.len() as u64, &digest, OS_LINUX, ARCH_X86_64)).unwrap();
        (store, file, hex(&digest)[..8].to_string())
    }

    #[test]
    fn imported_clean_build_satisfies_a_normal_project_commit_pin() {
        let commit = "1cf72d26294b95444125fbea569a592f1f37c1af";
        let (store, file, id) = source_fixture("clean", Some(commit), commit);
        assert_eq!(self_update(&store, Some(&format!("path:{}", file.display())), &file, file.parent().unwrap()).unwrap(), id);
        let project = file.parent().unwrap().join("project");
        std::fs::create_dir_all(&project).unwrap();
        std::fs::write(project.join(PROJECT_FILE), format!("{{:bl \"commit:{commit}\"}}")).unwrap();
        assert_eq!(resolve_with(&store, &project, None, None).target, Target::Build(id));
        let _ = std::fs::remove_dir_all(file.parent().unwrap());
    }

    #[test]
    fn dirty_import_does_not_satisfy_a_clean_pin() {
        let commit = "1cf72d26294b95444125fbea569a592f1f37c1af";
        let key = format!("{commit}+ac81415ef986");
        let (store,file,id) = source_fixture("dirty", Some(&key), commit);
        assert_eq!(self_update(&store, Some(&format!("path:{}", file.display())), &file, file.parent().unwrap()).unwrap(), id);
        assert!(store.read(&store.source_key(&key)).is_some());
        assert!(matches!(lookup(&store, &format!("commit:{commit}"), &mut vec![]), Target::Missing {..}));
        let _ = std::fs::remove_dir_all(file.parent().unwrap());
    }

    #[test]
    fn inconsistent_import_cannot_publish_a_source_pointer() {
        let commit = "1cf72d26294b95444125fbea569a592f1f37c1af";
        for (label,key) in [("mismatch", "abcdefabcdefabcdefabcdefabcdefabcdefabcd"), ("escape", "../escape")] {
            let (store,file,_) = source_fixture(label,Some(key),commit);
            assert!(self_update(&store, Some(&format!("path:{}", file.display())), &file, file.parent().unwrap()).is_err());
            assert!(list(&store,SOURCES_DIR).is_empty());
            let _ = std::fs::remove_dir_all(file.parent().unwrap());
        }
    }

    #[test]
    fn json_scan_reads_flat_strings() {
        let j = r#"{"url":"x","tag_name": "v2026.4","name":"v2026.4","prerelease":false}"#;
        assert_eq!(json_string(j, "tag_name").as_deref(), Some("v2026.4"));
        assert_eq!(json_string(j, "missing"), None);
    }

    #[test]
    fn config_set_replaces_or_adds() {
        let t = config_set("", "source", "/a");
        assert!(t.contains("{:source \"/a\"}"));
        assert_eq!(scan_literal(&t, "source").as_deref(), Some("/a"));
        let t2 = config_set(&t, "source", "/b");
        assert_eq!(scan_literal(&t2, "source").as_deref(), Some("/b"));
        let t3 = config_set(&t2, "default", "latest");
        assert_eq!(scan_literal(&t3, "default").as_deref(), Some("latest"));
        assert_eq!(scan_literal(&t3, "source").as_deref(), Some("/b"));
    }

    /// A git run under a hook inherits `GIT_INDEX_FILE` naming the FIRING
    /// worktree's index; `git_at` must not let a `worktree add` of another
    /// commit write into it.
    #[test]
    fn git_at_ignores_a_hooks_index_and_git_dir() {
        let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let d = std::env::temp_dir().join(format!("drop-gitenv-{}-{nanos}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let sh = |args: &[&str], dir: &Path| {
            assert!(Command::new("git").arg("-C").arg(dir).args(args).env("GIT_AUTHOR_NAME", "t")
                .env("GIT_AUTHOR_EMAIL", "t@t").env("GIT_COMMITTER_NAME", "t").env("GIT_COMMITTER_EMAIL", "t@t")
                .stdout(Stdio::null()).stderr(Stdio::null()).status().unwrap().success(), "git {args:?}");
        };
        let r = d.join("r");
        std::fs::create_dir_all(&r).unwrap();
        sh(&["init", "-q"], &r);
        sh(&["commit", "-q", "--allow-empty", "-m", "a"], &r);
        std::fs::write(r.join("f"), "x").unwrap();
        sh(&["add", "f"], &r);
        sh(&["commit", "-q", "-m", "b"], &r);
        sh(&["worktree", "add", "-q", "--detach", d.join("wt").to_str().unwrap(), "HEAD"], &r);
        let wt_index = r.join(".git/worktrees/wt/index");
        // the worktree's index CONTENT as git reads it (stat caches may be
        // refreshed by any git run; the tracked files may not change)
        let staged = || {
            let mut c = Command::new("git");
            c.arg("-C").arg(d.join("wt")).args(["ls-files", "--stage"]);
            scrub_git_env(&mut c);
            let o = c.output().unwrap();
            String::from_utf8_lossy(&o.stdout).to_string()
        };
        let before = staged();
        assert!(before.contains("\tf"), "the worktree tracks f: {before}");
        // what a hook fired in `wt` sees
        std::env::set_var("GIT_INDEX_FILE", &wt_index);
        std::env::set_var("GIT_DIR", r.join(".git/worktrees/wt"));
        let mut cmd = git_at(&r);
        cmd.args(["worktree", "add", "-q", "--detach", "--force"]).arg(d.join("other")).arg("HEAD~1");
        let ok = cmd.stdout(Stdio::null()).stderr(Stdio::null()).status().unwrap().success();
        std::env::remove_var("GIT_INDEX_FILE");
        std::env::remove_var("GIT_DIR");
        assert!(ok, "worktree add ran");
        assert_eq!(staged(), before, "the firing worktree's index still holds its own tree");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn this_platform_has_an_asset_name() {
        if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
            assert_eq!(asset_name(), Some("bl-linux-x86_64"));
        }
    }

    pub(crate) fn custody_source_identity() {
        // A shared Cargo target selected a different tree's cached test binary
        // in the original replay. Bind the code compiled into this test image.
        if let Ok(expected) = std::env::var("BL_CUSTODY_TEST_SOURCE_SHA256") {
            use sha2::{Digest, Sha256};
            let mut digest = Sha256::new();
            for (path, source) in [
            ("Cargo.toml", include_str!("../Cargo.toml")),
            ("Cargo.lock", include_str!("../Cargo.lock")),
            ("src/builder.rs", include_str!("builder.rs")),
            ("src/nix_artifact.rs", include_str!("nix_artifact.rs")),
            ("src/checkout.rs", include_str!("checkout.rs")),
            ("src/command_domain.rs", include_str!("command_domain.rs")),
            ("src/common.rs", include_str!("common.rs")),
            ("src/daemon.rs", include_str!("daemon.rs")),
            ("src/hooks.rs", include_str!("hooks.rs")),
            ("src/launcher.rs", include_str!("launcher.rs")),
            ("src/pack.rs", include_str!("pack.rs")),
            ("src/store.rs", include_str!("store.rs")),
            ("src/transport.rs", include_str!("transport.rs")),
            ] {
                digest.update(path.as_bytes()); digest.update([0]);
                digest.update(source.as_bytes()); digest.update([0]);
            }
            let actual = hex(&digest.finalize());
            assert_eq!(actual, expected, "requested custody Source differs from compiled test image");
            eprintln!("BUILD-CUSTODY-SOURCE {actual}");
        }
    }

    // Only launched by the exact subprocess test below; no build tool or BEAM.
    #[test]
    #[ignore = "explicit custody subprocess worker"]
    fn custody_subprocess_worker() {
        custody_source_identity();
        let root = PathBuf::from(std::env::var_os("BL_CUSTODY_TEST_ROOT").expect("private test root"));
        let store = Store { root: root.clone() };
        std::fs::write(root.join("ready"), "ready").unwrap();
        let _guard = BuildLock::take(&store).unwrap();
        assert_eq!(std::fs::read_to_string(store.meta().join("locks/build")).unwrap(),
                   std::process::id().to_string());
        std::fs::write(root.join("entered"), "entered").unwrap();
        while !root.join("finish").exists() {
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }

    #[test]
    #[ignore = "explicit native-publication subprocess worker"]
    fn native_publication_subprocess_worker() {
        custody_source_identity();
        let source = PathBuf::from(std::env::var_os("BL_PUBLICATION_TEST_SOURCE").expect("test source"));
        let destination = PathBuf::from(std::env::var_os("BL_PUBLICATION_TEST_DESTINATION").expect("test destination"));
        let result = PathBuf::from(std::env::var_os("BL_PUBLICATION_TEST_RESULT").expect("test result"));
        if let Some(finish) = std::env::var_os("BL_PUBLICATION_TEST_HOLD_UNTIL") {
            let _guard = NativePublication::take(&destination).unwrap();
            std::fs::write(&result, "held").unwrap();
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
            while !Path::new(&finish).exists() {
                assert!(std::time::Instant::now() < deadline, "publication holder timed out");
                std::thread::sleep(std::time::Duration::from_millis(5));
            }
            return;
        }
        let verdict = publish_native_artifact(&source, &destination);
        std::fs::write(&result, match verdict { Ok(()) => "ok".to_string(), Err(error) => format!("error:{error}") }).unwrap();
    }

    #[test]
    fn native_publication_preserves_old_bytes_and_releases_failed_operations() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("native-publication-failure-{}", std::process::id()));
        let _cleanup = CustodyDirectory(root.clone());
        std::fs::create_dir_all(&root).unwrap();
        let source = root.join("built.so");
        let destination = root.join("installed.so");
        std::fs::write(&destination, "old").unwrap();
        assert!(publish_native_artifact(&source, &destination).is_err());
        assert_eq!(std::fs::read(&destination).unwrap(), b"old");
        std::fs::write(&source, "new").unwrap();
        std::fs::remove_file(&destination).unwrap();
        std::fs::create_dir(&destination).unwrap();
        assert!(publish_native_artifact(&source, &destination).is_err());
        assert!(destination.is_dir());
        assert!(!std::fs::read_dir(&root).unwrap().flatten().any(|e| e.file_name().to_string_lossy().starts_with("installed.so.tmp-")));
        std::fs::remove_dir(&destination).unwrap();
        let diagnostic = root.join(".bl/artifact-custody/installed.so/.claim");
        std::fs::create_dir(&diagnostic).unwrap();
        assert!(publish_native_artifact(&source, &destination).unwrap_err().contains("invalidate"));
        std::fs::remove_dir(&diagnostic).unwrap();
        publish_native_artifact(&source, &destination).unwrap();
        assert_eq!(std::fs::read(&destination).unwrap(), b"new");
        #[cfg(unix)] {
            let other = root.join("untouched.so");
            std::fs::write(&other, "untouched").unwrap();
            std::fs::remove_file(&destination).unwrap();
            std::os::unix::fs::symlink(&other, &destination).unwrap();
            publish_native_artifact(&source, &destination).unwrap();
            assert!(!std::fs::symlink_metadata(&destination).unwrap().is_symlink());
            assert_eq!(std::fs::read(&other).unwrap(), b"untouched");
            assert_eq!(std::fs::read(&destination).unwrap(), b"new");
        }
    }

    #[test]
    #[ignore = "explicit external custody owner worker"]
    fn custody_external_owner_worker() {
        custody_source_identity();
        let root = PathBuf::from(std::env::var_os("BL_CUSTODY_TEST_ROOT").unwrap());
        let store = Store { root: root.clone() };
        let custody = BuildLock::take(&store).unwrap();
        let mut command = if let Some(manifest) = std::env::var_os("BL_CUSTODY_EXTERNAL_CARGO_MANIFEST") {
            let mut cargo = Command::new("cargo");
            cargo.args(["build", "--offline", "--locked", "-j", "1", "--manifest-path"]).arg(manifest)
                .arg("--target-dir").arg(root.join("cargo-target"));
            cargo
        } else {
            let mut worker = Command::new(std::env::current_exe().unwrap());
            worker.args(["--exact", "builder_tests::custody_external_child_worker", "--ignored", "--nocapture"]);
            worker
        };
        command.env("BL_CUSTODY_TEST_ROOT", &root);
        run_logged(command, &root.join("external.log"), "actual external worker", &custody).unwrap();
        std::fs::write(root.join("command-returned"), "returned").unwrap();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        while !root.join("owner-finish").exists() {
            assert!(std::time::Instant::now() < deadline, "external owner timed out");
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }

    #[test]
    #[ignore = "explicit external custody child worker"]
    fn custody_external_child_worker() {
        custody_source_identity();
        let root = PathBuf::from(std::env::var_os("BL_CUSTODY_TEST_ROOT").unwrap());
        if std::env::var_os("BL_CUSTODY_TEST_GRANDCHILD").is_some() {
            let mut grandchild = Command::new(std::env::current_exe().unwrap());
            grandchild.args(["--exact", "builder_tests::custody_external_child_worker", "--ignored", "--nocapture"])
                .env_remove("BL_CUSTODY_TEST_GRANDCHILD");
            grandchild.spawn().unwrap();
            return;
        }
        std::fs::write(root.join("external-pid"), std::process::id().to_string()).unwrap();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        while !root.join("external-finish").exists() {
            assert!(std::time::Instant::now() < deadline, "external child timed out");
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        std::fs::write(root.join("external-exited"), "exited").unwrap();
    }

    // Always release the bounded worker on failure, before removing its root.
    struct ExternalCustodyFinish(PathBuf);
    impl Drop for ExternalCustodyFinish {
        fn drop(&mut self) {
            let _ = std::fs::write(self.0.join("external-finish"), "finish");
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
            while !self.0.join("external-exited").exists() && std::time::Instant::now() < deadline {
                std::thread::sleep(std::time::Duration::from_millis(5));
            }
        }
    }

    #[test]
    #[cfg(unix)]
    fn build_custody_outlives_parent_and_intermediate_external_children() {
        custody_source_identity();
        for grandchild in [false, true] {
            let root = std::env::temp_dir().join(format!("external-custody-{}-{grandchild}", std::process::id()));
            std::fs::create_dir_all(&root).unwrap();
            let _cleanup = CustodyDirectory(root.clone());
            let _finish = ExternalCustodyFinish(root.clone());
            let store = Store { root: root.clone() };
            let mut command = Command::new(std::env::current_exe().unwrap());
            command.args(["--exact", "builder_tests::custody_external_owner_worker", "--ignored", "--nocapture"])
                .env("BL_CUSTODY_TEST_ROOT", &root);
            if grandchild { command.env("BL_CUSTODY_TEST_GRANDCHILD", "1"); }
            let mut owner = CustodyChild(command.spawn().unwrap());
            await_custody_file(&root.join("external-pid"), &mut owner);
            if grandchild { await_custody_file(&root.join("command-returned"), &mut owner); }
            owner.0.kill().unwrap();
            owner.0.wait().unwrap();
            let follower = std::fs::OpenOptions::new().read(true).write(true).create(true).truncate(false)
                .open(store.meta().join("locks/build.kernel.followers")).unwrap();
            assert!(matches!(follower.try_lock(), Err(std::fs::TryLockError::WouldBlock)),
                    "orphaned external child still needs custody (grandchild={grandchild})");
            // A fresh actual build owner must wait while the orphan remains.
            let contender_output = root.join("contender.log");
            let output = std::fs::File::create(&contender_output).unwrap();
            let mut contender = CustodyChild(Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "builder_tests::custody_subprocess_worker", "--ignored", "--nocapture"])
                .env("BL_CUSTODY_TEST_ROOT", &root)
                .stdout(Stdio::from(output.try_clone().unwrap())).stderr(Stdio::from(output)).spawn().unwrap());
            await_custody_file(&root.join("ready"), &mut contender);
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
            while !std::fs::read_to_string(&contender_output).unwrap().contains("surviving bootstrap commands hold child custody") {
                assert!(!root.join("entered").exists(), "replacement admitted before external child exit");
                assert!(contender.0.try_wait().unwrap().is_none(), "contender exited before draining followers");
                assert!(std::time::Instant::now() < deadline, "contender never reached the actual follower barrier");
                std::thread::sleep(std::time::Duration::from_millis(5));
            }
            assert!(!root.join("entered").exists());
            std::fs::write(root.join("external-finish"), "finish").unwrap();
            await_custody_file(&root.join("entered"), &mut contender);
            std::fs::write(root.join("finish"), "finish").unwrap();
            assert!(contender.0.wait().unwrap().success());
            assert!(follower.try_lock().is_ok(), "last child exit releases follower custody");
        }
    }

    #[test]
    #[cfg(unix)]
    fn external_command_partial_admission_never_starts_and_releases_leases() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("external-custody-failure-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let _cleanup = CustodyDirectory(root.clone());
        let store = Store { root: root.clone() };
        let custody = BuildLock::take(&store).unwrap();
        let follower = std::fs::OpenOptions::new().read(true).write(true)
            .open(store.meta().join("locks/build.kernel.followers")).unwrap();
        follower.try_lock().unwrap();
        let mut command = Command::new(std::env::current_exe().unwrap());
        command.args(["--exact", "builder_tests::custody_external_child_worker", "--ignored", "--nocapture"])
            .env("BL_CUSTODY_TEST_ROOT", &root);
        let log = root.join("must-not-start.log");
        assert!(run_logged(command, &log, "blocked external worker", &custody).unwrap_err().contains("admit child"));
        assert!(!log.exists(), "admission refuses before opening the step log");
        assert!(!root.join("external-pid").exists(), "no external child was born");
        drop(follower);
        let log = root.join("failed-start.log");
        assert!(run_logged(Command::new(root.join("nonexistent-executable")), &log, "missing executable", &custody)
            .unwrap_err().contains("could not start"));
        let follower = std::fs::OpenOptions::new().read(true).write(true)
            .open(store.meta().join("locks/build.kernel.followers")).unwrap();
        follower.try_lock().expect("failed spawn released the partial child lease");
        drop(follower);
        // Preparing one command must not make its descriptor inheritable in
        // the parent, where an unrelated concurrent spawn could retain it.
        let mut prepared = Command::new("unused-prepared-command");
        custody.prepare_command(&mut prepared).unwrap();
        let _unrelated = CustodyChild(Command::new("sleep").arg("10").spawn().unwrap());
        drop(prepared);
        drop(custody);
        let follower = std::fs::OpenOptions::new().read(true).write(true)
            .open(store.meta().join("locks/build.kernel.followers")).unwrap();
        follower.try_lock().expect("unrelated child inherited no other command's custody");
    }

    #[test]
    #[cfg(target_os = "linux")]
    fn actual_cargo_build_script_retains_custody_after_parent_and_cargo_death() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("cargo-external-custody-{}", std::process::id()));
        std::fs::create_dir_all(root.join("crate/src")).unwrap();
        let _cleanup = CustodyDirectory(root.clone());
        let _finish = ExternalCustodyFinish(root.clone());
        std::fs::write(root.join("crate/Cargo.toml"), "[package]\nname=\"custody_probe\"\nversion=\"0.0.0\"\nedition=\"2021\"\n[workspace]\n").unwrap();
        std::fs::write(root.join("crate/Cargo.lock"), "version = 4\n[[package]]\nname = \"custody_probe\"\nversion = \"0.0.0\"\n").unwrap();
        std::fs::write(root.join("crate/src/lib.rs"), "pub fn answer() -> u8 { 42 }\n").unwrap();
        std::fs::write(root.join("crate/build.rs"), r#"
fn main() {
    let root = std::path::PathBuf::from(std::env::var_os("BL_CUSTODY_TEST_ROOT").unwrap());
    let status = std::fs::read_to_string("/proc/self/status").unwrap();
    let parent = status.lines().find_map(|line| line.strip_prefix("PPid:")).unwrap().trim();
    std::fs::write(root.join("cargo-pid"), parent).unwrap();
    std::fs::write(root.join("external-pid"), std::process::id().to_string()).unwrap();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    while !root.join("external-finish").exists() {
        assert!(std::time::Instant::now() < deadline, "actual build script timed out");
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    std::fs::write(root.join("external-exited"), "exited").unwrap();
}
"#).unwrap();
        let mut owner = CustodyChild(Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "builder_tests::custody_external_owner_worker", "--ignored", "--nocapture"])
            .env("BL_CUSTODY_TEST_ROOT", &root)
            .env("BL_CUSTODY_EXTERNAL_CARGO_MANIFEST", root.join("crate/Cargo.toml"))
            .spawn().unwrap());
        await_custody_file(&root.join("external-pid"), &mut owner);
        let cargo_pid = std::fs::read_to_string(root.join("cargo-pid")).unwrap();
        // Verify the PID supplied by the real build script belongs to Cargo,
        // then kill both ancestors while the actual build-script process lives.
        let cargo_executable = std::fs::read_link(format!("/proc/{cargo_pid}/exe")).unwrap();
        let cargo_status = std::fs::read_to_string(format!("/proc/{cargo_pid}/status")).unwrap();
        let cargo_parent: u32 = cargo_status.lines().find_map(|line| line.strip_prefix("PPid:")).unwrap().trim().parse().unwrap();
        assert_eq!(owner.0.id(), cargo_parent, "actual Cargo must be the owner's direct child");
        let cargo_name = cargo_executable.file_name().unwrap().to_string_lossy();
        assert!(cargo_name.contains("cargo"), "unexpected actual Cargo executable: {}", cargo_executable.display());
        eprintln!("EXTERNAL-CUSTODY-CARGO executable={} sha256={}", cargo_executable.display(),
                  sha256_hex(&std::fs::read(&cargo_executable).unwrap()));
        owner.0.kill().unwrap();
        owner.0.wait().unwrap();
        assert!(Command::new("kill").args(["-9", cargo_pid.trim()]).status().unwrap().success());
        let store = Store { root: root.clone() };
        let follower = std::fs::OpenOptions::new().read(true).write(true)
            .open(store.meta().join("locks/build.kernel.followers")).unwrap();
        assert!(matches!(follower.try_lock(), Err(std::fs::TryLockError::WouldBlock)),
                "actual orphaned Cargo build script lost custody");
        std::fs::write(root.join("external-finish"), "finish").unwrap();
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        loop {
            if follower.try_lock().is_ok() { break; }
            assert!(std::time::Instant::now() < deadline, "Cargo descendant did not release custody");
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
        assert!(root.join("external-exited").exists());
    }

    #[test]
    fn cargo_target_discovery_requires_successful_real_metadata() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("drop cargo discovery {}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let _cleanup = CustodyDirectory(root.clone());
        let store = Store { root: root.clone() };
        let custody = BuildLock::take(&store).unwrap();
        assert!(cargo_target_dir(&root.join("missing crate"), &custody).is_err(),
                "failed real Cargo metadata must never authorize a guessed target directory");
        let crate_dir = root.join("valid crate");
        std::fs::create_dir_all(crate_dir.join("src")).unwrap();
        std::fs::write(crate_dir.join("Cargo.toml"),
            "[package]\nname=\"target_discovery_probe\"\nversion=\"0.0.0\"\nedition=\"2021\"\n[workspace]\n").unwrap();
        std::fs::write(crate_dir.join("Cargo.lock"),
            "version=4\n[[package]]\nname=\"target_discovery_probe\"\nversion=\"0.0.0\"\n").unwrap();
        std::fs::write(crate_dir.join("src/lib.rs"), "pub fn answer() -> u8 { 42 }\n").unwrap();
        let lock_before = std::fs::read(crate_dir.join("Cargo.lock")).unwrap();
        let discovered = cargo_target_dir(&crate_dir, &custody).unwrap();
        assert!(discovered.is_absolute(), "actual Cargo target is an absolute address");
        if let Some(target) = std::env::var_os("CARGO_TARGET_DIR") {
            let target = PathBuf::from(target);
            if target.is_absolute() { assert_eq!(target, discovered); }
        } else {
            assert_eq!(crate_dir.join("target"), discovered);
        }
        assert_eq!(lock_before, std::fs::read(crate_dir.join("Cargo.lock")).unwrap());
        assert!(!crate_dir.join("target").exists(), "discovery must not compile an artifact");
    }

    #[test]
    fn cargo_metadata_ignores_nested_lookalike_output_directories() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("drop cargo metadata shadow {}", std::process::id()));
        std::fs::create_dir_all(root.join("crate/src")).unwrap();
        let _cleanup = CustodyDirectory(root.clone());
        let store = Store { root: root.clone() };
        let custody = BuildLock::take(&store).unwrap();
        let crate_dir = root.join("crate");
        std::fs::write(crate_dir.join("Cargo.toml"),
            "[package]\nname=\"metadata_shadow_probe\"\nversion=\"0.0.0\"\nedition=\"2021\"\n[workspace]\n[package.metadata]\ntarget_directory=\"/unrelated-old-products\"\n").unwrap();
        std::fs::write(crate_dir.join("Cargo.lock"),
            "version=4\n[[package]]\nname=\"metadata_shadow_probe\"\nversion=\"0.0.0\"\n").unwrap();
        std::fs::write(crate_dir.join("src/lib.rs"), "pub fn answer() -> u8 { 42 }\n").unwrap();
        let discovered = cargo_target_dir(&crate_dir, &custody).unwrap();
        assert_ne!(PathBuf::from("/unrelated-old-products"), discovered,
                   "package metadata must not nominate Cargo's output directory");
        if let Some(target) = std::env::var_os("CARGO_TARGET_DIR") {
            let target = PathBuf::from(target);
            if target.is_absolute() { assert_eq!(target, discovered); }
        }
    }

    #[test]
    fn failed_metadata_prevents_real_native_publication_even_with_a_guessed_library() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("drop native metadata failure {}", std::process::id()));
        let _cleanup = CustodyDirectory(root.clone());
        let project = root.join("project");
        let crate_dir = project.join("native/tiny_discovery");
        std::fs::create_dir_all(crate_dir.join("src")).unwrap();
        std::fs::write(crate_dir.join("Cargo.toml"),
            "[package]\nname=\"tiny_discovery\"\nversion=\"0.0.0\"\nedition=\"2021\"\n[workspace]\n[lib]\ncrate-type=[\"cdylib\"]\n").unwrap();
        std::fs::write(crate_dir.join("Cargo.lock"),
            "version=4\n[[package]]\nname=\"tiny_discovery\"\nversion=\"0.0.0\"\n").unwrap();
        std::fs::write(crate_dir.join("src/lib.rs"), "#[no_mangle]\npub extern \"C\" fn answer() -> u8 { 42 }\n").unwrap();
        // Cargo already read its manifest. Make subsequent real metadata fail
        // after compilation, with an unrelated library waiting at the old guess.
        std::fs::write(crate_dir.join("build.rs"),
            "fn main() { std::fs::remove_file(std::path::PathBuf::from(std::env::var_os(\"CARGO_MANIFEST_DIR\").unwrap()).join(\"Cargo.toml\")).unwrap(); }\n").unwrap();
        let guessed = crate_dir.join("target/release");
        std::fs::create_dir_all(&guessed).unwrap();
        std::fs::write(guessed.join("libtiny_discovery.so"), "unrelated guessed product").unwrap();
        let destination = project.join("priv/native/tiny_discovery.so");
        std::fs::create_dir_all(destination.parent().unwrap()).unwrap();
        std::fs::write(&destination, "old installed library").unwrap();
        let store = Store { root: root.clone() };
        let custody = BuildLock::take(&store).unwrap();
        let log = root.join("build.log");
        let error = build_natives(&project, &log, &custody)
            .expect_err("failed metadata must prevent real native publication");
        assert!(error.contains("native Cargo metadata"), "unexpected failure before metadata: {error}");
        assert!(std::fs::read_to_string(log).unwrap().contains("Finished"), "actual Cargo compilation must succeed first");
        assert!(!crate_dir.join("Cargo.toml").exists());
        assert_eq!(std::fs::read(&destination).unwrap(), b"old installed library");
        assert_eq!(std::fs::read(guessed.join("libtiny_discovery.so")).unwrap(), b"unrelated guessed product");
    }

    struct CustodyChild(std::process::Child);
    impl Drop for CustodyChild {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    struct CustodyDirectory(PathBuf);
    impl Drop for CustodyDirectory {
        fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.0); }
    }
    fn await_custody_file(path: &Path, child: &mut CustodyChild) {
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        while !path.exists() {
            assert!(child.0.try_wait().unwrap().is_none(), "custody worker exited before {}", path.display());
            assert!(std::time::Instant::now() < deadline, "custody worker timed out: {}", path.display());
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }

    #[test]
    fn build_custody_survives_missing_or_forged_diagnostics_and_owner_crash() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("drop-custody-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let _directory = CustodyDirectory(root.clone());
        let store = Store { root: root.clone() };
        let held = BuildLock::take(&store).unwrap();
        let diagnostic = store.meta().join("locks/build");
        let mut child = CustodyChild(Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "builder_tests::custody_subprocess_worker", "--ignored", "--nocapture"])
            .env("BL_CUSTODY_TEST_ROOT", &root).spawn().unwrap());
        await_custody_file(&root.join("ready"), &mut child);
        for diagnostic_bytes in [None, Some(""), Some("999999999"), Some("handmade marker")] {
            match diagnostic_bytes {
                None => { let _ = std::fs::remove_file(&diagnostic); }
                Some(bytes) => std::fs::write(&diagnostic, bytes).unwrap(),
            }
            // The original PID loop sleeps two seconds between probes.
            // Observe beyond that interval; a100ms window can falsely pass.
            std::thread::sleep(std::time::Duration::from_millis(2200));
            assert!(!root.join("entered").exists(), "diagnostic text admitted a competing actual process");
        }
        drop(held);
        await_custody_file(&root.join("entered"), &mut child);
        // SIGKILL bypasses Rust Drop. Actual kernel custody must still release.
        child.0.kill().unwrap();
        child.0.wait().unwrap();
        let recovered = BuildLock::take(&store).unwrap();
        assert_eq!(std::fs::read_to_string(&diagnostic).unwrap(), std::process::id().to_string());
        drop(recovered);
    }

    #[test]
    fn build_custody_reports_io_errors_and_releases_after_publication_failure() {
        custody_source_identity();
        let root = std::env::temp_dir().join(format!("drop-custody-io-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let _directory = CustodyDirectory(root.clone());
        let store = Store { root: root.clone() };
        let locks = store.meta().join("locks");
        let anchor = locks.join("build.kernel");
        std::fs::create_dir_all(&anchor).unwrap();
        assert!(BuildLock::take(&store).err().unwrap().contains("cannot open build custody"));
        std::fs::remove_dir(&anchor).unwrap();
        let followers = locks.join("build.kernel.followers");
        std::fs::create_dir(&followers).unwrap();
        assert!(BuildLock::take(&store).err().unwrap().contains("cannot open build followers"));
        std::fs::File::open(&anchor).unwrap().try_lock().expect("follower open failure releases writer");
        std::fs::remove_dir(&followers).unwrap();
        // Publishing over a directory fails after actual kernel acquisition.
        std::fs::create_dir(locks.join("build")).unwrap();
        assert!(BuildLock::take(&store).err().unwrap().contains("cannot publish build owner"));
        let observer = std::fs::OpenOptions::new().read(true).write(true).open(&anchor).unwrap();
        observer.try_lock().expect("publication failure released its actual kernel descriptor");
        assert!(std::fs::read_dir(&locks).unwrap().all(|entry|
            !entry.unwrap().file_name().to_string_lossy().starts_with("build.writing-")));
        drop(observer);
        std::fs::remove_dir(locks.join("build")).unwrap();
        let acquired = BuildLock::take(&store).unwrap();
        assert!(matches!(std::fs::File::open(&anchor).unwrap().try_lock(), Err(std::fs::TryLockError::WouldBlock)));
        drop(acquired);
        assert!(anchor.is_file(), "the permanent anchor survives release");
        std::fs::File::open(&anchor).unwrap().try_lock().unwrap();
    }

    #[test]
    fn the_build_lock_is_exclusive_and_stale_locks_are_taken() {
        custody_source_identity();
        let d = std::env::temp_dir().join(format!("drop-lock-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        let store = Store { root: d.clone() };
        let path = store.meta().join("locks").join("build");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, "999999999").unwrap(); // a pid that cannot be alive
        {
            let _l = BuildLock::take(&store).unwrap();
            assert_eq!(std::fs::read_to_string(&path).unwrap(), std::process::id().to_string());
        }
        assert!(!path.exists(), "the lock is released on drop");
        let _ = std::fs::remove_dir_all(&d);
    }
}
