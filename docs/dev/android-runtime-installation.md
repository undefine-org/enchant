# Android runtime installation

The APK installer runs before ERTS starts. Runtime files live under the app's
`files/otp` directory. Application files can also live there, so installation
uses an explicit file ownership receipt rather than replacing the directory.
The Kotlin installer and Source push receiver share this protocol.

`otp/.bl-runtime-files` contains one line per installed regular runtime file:

```text
<64 lowercase SHA-256 digits>  relative/path
```

Paths are relative to `otp`, unique and free of traversal, backslashes and
line breaks. The receipt excludes itself. The Kotlin installer derives the
receipt from the actual checksum-verified ZIP members. A receipt supplied in
the archive does not grant ownership of other files.

An upgrade replaces incoming runtime files and prunes an obsolete file only
when its current hash still equals the previous receipt's hash. Unrecorded
files, changed obsolete files and directories remain. A legacy installation
without a receipt supplies no pruning authority.

An incoming path that contains an unrecorded or modified regular file is copied
before replacement. Kotlin retains these copies under
`files/.bl-runtime-backups/install-*`; the Source push receiver retains them in
`files/.bl-runtime-preserved.*`. Both backup locations remain after success and
across retries. File/directory type
conflicts and symbolic-link destinations or ancestors refuse installation.
Existing fixed `.bl-runtime-install` and `.bl-runtime-previous` directories are
preserved because they can contain data from an older interrupted installer.

Each attempt owns a fresh staging directory. ZIP paths and the archive checksum
are checked before active files change. File publication and metadata replacement
use same-filesystem atomic moves. The new ownership receipt is committed before
the APK digest marker `files/.bl-runtime`; a failed marker publication therefore
requires a retry. Failed attempts retain user backups. This is a file projection,
not an atomic database migration or a transaction spanning the entire directory.

Both installers acquire `files/.bl-runtime-install.lock` with atomic directory
creation. An existing lock refuses a second writer. The owner removes only its
empty lock. A process crash or permission failure can leave a stale lock: stop
all runtime and installer processes, inspect it, then remove only the empty lock
directory before retrying. Lock ownership is never inferred from age. Runtime
installation and Source push must run while ERTS and application data writers
are stopped.

The Kotlin path requires Java NIO filesystem APIs available from Android API 26. Its JVM tests exercise disposable directories,
including legacy data, receipt interoperability, symlinks, collisions, failure
publication, retry and competing installers. Run them on the configured station:

```sh
systemd-run --user --collect --wait --pipe --working-directory="$PWD" \
  --property=MemoryMax=4G --property=MemorySwapMax=0 \
  nix-build test/nix/android-runtime-installer.nix --argstr source "$PWD" \
  --max-jobs 0 --out-link .local/android-installer-proof
```

Inspect the output's `result.json` and require `status: passed`. This finite
JVM check compiles only the installer and its tests; it produces no SDK and
writes only disposable JVM test fixtures.

Beam Lisp application compilation uses the managed Nix application producer.
The Android Rust products also build through Nix with the configured worker
policy. The Android command runs Zig's Mob/JNI bridge and Gradle's APK assembly
in the local pinned toolchain, retaining their per-ABI caches. Device checks
need an explicit disposable app/device and a bounded emulator; signing keys
belong outside Nix outputs and Git.

Runtime staging pairs Android's OTP and native runtime with the selected SDK's
exact Elixir application files. Mixing Elixir patch versions changes the
compiler cache identity and cannot establish valid application replay. The
device `beam_lisp.app` resource is rendered into an owned cache before file
synchronization, rather than modifying a copied read-only Nix file.

The Android native product uses Bionic `flock` for nonblocking shared and
exclusive cache locks. Rust 1.95's standard `File::try_lock` methods return
`Unsupported` on Android before making a system call; see the
[Rust implementation](https://github.com/rust-lang/rust/blob/1.95.0/library/std/src/sys/fs/unix.rs#L1562-L1641).
The replacement retains the open file descriptor, owner monitor and
close-to-release rules. Other platforms keep the standard implementation.
Neither an unavailable lock nor a missing cache entry permits replay without
its complete producer evidence.
