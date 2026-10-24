use sha2::{Digest, Sha256};
use std::{env, fs, path::Path, process::Command};

fn sources(dir: &Path, files: &mut Vec<std::path::PathBuf>) {
    for entry in fs::read_dir(dir).expect("native source directory") {
        let path = entry.expect("native source entry").path();
        if path.is_dir() {
            sources(&path, files);
        } else if path.extension().is_some_and(|extension| extension == "rs") {
            files.push(path);
        }
    }
}

fn field(hash: &mut Sha256, name: &str, bytes: &[u8]) {
    hash.update((name.len() as u64).to_le_bytes());
    hash.update(name.as_bytes());
    hash.update((bytes.len() as u64).to_le_bytes());
    hash.update(bytes);
}

fn main() {
    // A conservative producer identity, reported by the library actually
    // loaded in BEAM. It is neither a pathname nor a hash of a replaceable
    // file after loading, and makes no ABI equivalence claim across builds.
    let mut files = vec!["Cargo.toml".into(), "Cargo.lock".into(), "build.rs".into()];
    sources(Path::new("src"), &mut files);
    files.sort();
    let mut hash = Sha256::new();
    field(&mut hash, "schema", b"beam-lisp-lazy-memo-build-v1");
    for path in files {
        println!("cargo:rerun-if-changed={}", path.display());
        field(&mut hash, path.to_str().expect("UTF-8 source path"), &fs::read(&path).expect("native source"));
    }
    let mut settings: Vec<_> = env::vars().filter(|(key, _)|
        key.starts_with("CARGO_CFG_") || key.starts_with("CARGO_FEATURE_") ||
        ["TARGET", "HOST", "PROFILE", "OPT_LEVEL", "DEBUG", "CARGO_ENCODED_RUSTFLAGS"].contains(&key.as_str())
    ).collect();
    settings.sort();
    for (key, value) in settings {
        println!("cargo:rerun-if-env-changed={key}");
        field(&mut hash, &key, value.as_bytes());
    }
    let rustc = Command::new(env::var_os("RUSTC").expect("RUSTC"))
        .arg("--version").arg("--verbose").output().expect("rustc version");
    assert!(rustc.status.success(), "rustc version failed");
    field(&mut hash, "rustc", &rustc.stdout);
    println!("cargo:rustc-env=BEAM_LISP_NATIVE_BUILD_ID={:x}", hash.finalize());
}
