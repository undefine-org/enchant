//! The pre-BEAM consumer of the same fixed native artifact recipe used by Source.
use std::path::{Path, PathBuf};
use serde_json::{json, Value};

pub(super) fn store_object(path: &str) -> bool {
    let Some(name) = path.strip_prefix("/nix/store/") else { return false };
    name.len() > 33 && name.as_bytes()[32] == b'-' && !name.contains('/')
        && name.as_bytes()[..32].iter().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
}

/// Build resolution includes the selected trusted recipe/lock, even when the
/// platform lives outside the application's source tree.
pub(super) fn stamp_inputs(platform: &Path) -> Vec<String> {
    let mut inputs: Vec<PathBuf> = ["nix/native-artifact.nix", "nix/native-source.nix", "nix/native-snapshot.nix", "nix/native-workspace.nix", "nix/bounded-build.nix", "flake.lock",
        "nix/artifact-platform.nix", "nix/command-executor.nix", "nix/prepare-platform.nix", "executor.json",
        "tooling/drop/Cargo.toml", "tooling/drop/Cargo.lock"].iter().map(PathBuf::from).collect();
    if let Ok(entries) = std::fs::read_dir(platform.join("tooling/drop/src")) {
        inputs.extend(entries.flatten().map(|entry| entry.path()).filter(|path| path.extension().is_some_and(|ext| ext == "rs"))
            .map(|path| path.strip_prefix(platform).unwrap().to_path_buf()));
    }
    inputs.sort();
    inputs.into_iter().map(|relative| {
        let digest = std::fs::read(platform.join(&relative)).map(|bytes| crate::sha256_hex(&bytes))
            .unwrap_or_else(|_| "missing".into());
        format!("artifact-platform {} {digest}", relative.display())
    }).collect()
}

fn rust_identifier(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128
        && value.bytes().next().is_some_and(|b| b.is_ascii_alphabetic() || b == b'_')
        && value.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

fn cargo_package(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128
        && value.bytes().next().is_some_and(|b| b.is_ascii_alphanumeric() || b == b'_')
        && value.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

fn workspace_member(value: &str) -> bool {
    value == "." || (!value.is_empty() && value.len() <= 4096
        && value.split('/').all(|part| !part.is_empty() && part.len() <= 255
            && ![".", "..", ".git", ".bl", "target"].contains(&part)
            && !part.starts_with('-')
            && part.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'.' || b == b'-')))
}

/// Closed data contract shared by preparation and the final byte verifier.
/// A mutable absolute source is accepted only before the rooted snapshot step.
fn validate_request(request: &Value, immutable_source: bool) -> Result<u64, String> {
    let fields = request.as_object().ok_or("native request must be an object")?;
    let version = request.get("version").and_then(Value::as_u64).ok_or("invalid native request version")?;
    let expected: &[&str] = match version {
        1 => &["version", "source", "crate", "abi", "target"],
        2 => &["version", "source", "member", "package", "crate", "abi", "target"],
        _ => return Err("unsupported native request version".into()),
    };
    if fields.len() != expected.len() || expected.iter().any(|key| !fields.contains_key(*key)) {
        return Err("native request contains missing or unknown fields".into());
    }
    let name = request["crate"].as_str().ok_or("missing native crate")?;
    let abi = request["abi"].as_str().ok_or("missing native ABI")?;
    let source = request["source"].as_str().ok_or("missing native source")?;
    if !rust_identifier(name) || abi.is_empty() || abi.len() > 128 || abi.contains('\0')
        || source.len() > 4096 || source.contains('\0') || !Path::new(source).is_absolute() || source == "/"
        || request["target"] != "x86_64-linux" {
        return Err("invalid native request identity or source".into());
    }
    if immutable_source && !store_object(source) {
        return Err("native product source must be a top-level store object".into());
    }
    if version == 2 && (!request["member"].as_str().is_some_and(workspace_member)
        || !request["package"].as_str().is_some_and(cargo_package)) {
        return Err("invalid native workspace member or Cargo package".into());
    }
    Ok(version)
}

pub(super) fn verify(output: &Path, request: &Value) -> Result<PathBuf, String> {
    let version = validate_request(request, true)?;
    let address = output.to_str().ok_or("native output address is not UTF-8")?;
    if !store_object(address) { return Err("native output must be a top-level store object".into()); }
    let manifest: Value = serde_json::from_slice(&std::fs::read(output.join("artifact.json"))
        .map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    let name = request["crate"].as_str().ok_or("missing native crate")?;
    let relative = format!("lib/{name}.so");
    if manifest["version"].as_u64() != Some(version) || manifest["kind"] != "native-library"
        || manifest["library"] != relative
        || ["crate", "source", "target", "abi"].iter().any(|key| manifest[*key] != request[*key]) {
        return Err("native product identity disagrees with its request".into());
    }
    if version == 2 && ["member", "package"].iter().any(|key| manifest[*key] != request[*key]) {
        return Err("native workspace provenance disagrees with its request".into());
    }
    let library = output.join(relative);
    if !std::fs::symlink_metadata(&library).map_err(|e| e.to_string())?.file_type().is_file() {
        return Err("native product is not a regular library".into());
    }
    let digest = crate::sha256_hex(&std::fs::read(&library).map_err(|e| e.to_string())?);
    if manifest["sha256"].as_str() != Some(&digest) {
        return Err("native product digest disagrees".into());
    }
    if version == 2 {
        let cargo_library = manifest["cargoLibrary"].as_str().filter(|name| rust_identifier(name))
            .ok_or("native workspace product omitted its Cargo library name")?;
        let compiled = manifest["compiled"].as_str().filter(|path| store_object(path))
            .ok_or("native workspace product omitted its compiled store object")?;
        let original = Path::new(compiled).join(format!("lib/{cargo_library}.so"));
        if !std::fs::symlink_metadata(&original).map_err(|e| e.to_string())?.file_type().is_file()
            || crate::sha256_hex(&std::fs::read(&original).map_err(|e| e.to_string())?) != digest {
            return Err("native Cargo library provenance or final bytes disagree".into());
        }
    }
    if manifest["toolchain"]["name"] != "rustc"
        || !manifest["toolchain"]["identity"].as_str().is_some_and(|id| id.len() == 64 && id.bytes().all(|b| b.is_ascii_hexdigit()))
        || !manifest["toolchain"]["version"].is_string() {
        return Err("native product omitted its toolchain closure".into());
    }
    Ok(library)
}

pub(super) fn prepare(tree: &Path, source: &Path, name: &str,
                       custody: &crate::BuildLock) -> Result<PathBuf, String> {
    let source = std::fs::canonicalize(source).map_err(|e| e.to_string())?;
    let source = source.to_str().ok_or("native source address is not UTF-8")?;
    prepare_request(tree, &json!({"version":1,"source":source,"crate":name,
                                 "abi":format!("beam-lisp-native-{name}-v1"),"target":"x86_64-linux"}), custody)
}

/// Prepare a closed standalone/workspace request using the same rooted source
/// and product recipe as Source. No caller expression or tool argv is accepted.
pub(super) fn prepare_request(tree: &Path, requested: &Value,
                              custody: &crate::BuildLock) -> Result<PathBuf, String> {
    if !cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        return Err("Nix native products currently support x86_64-linux".into());
    }
    let version = validate_request(requested, false)?;
    let name = requested["crate"].as_str().ok_or("missing native crate")?;
    let source = Path::new(requested["source"].as_str().ok_or("missing native source")?);
    let platform = std::env::var_os("BL_ARTIFACT_PLATFORM").map(PathBuf::from)
        .unwrap_or_else(|| tree.to_path_buf());
    let platform = std::fs::canonicalize(platform).map_err(|e| e.to_string())?;
    let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| e.to_string())?.as_nanos();
    let cache = std::env::var_os("XDG_CACHE_HOME").map(PathBuf::from)
        .unwrap_or_else(|| crate::expand_home("~/.cache"));
    let retained = cache.join("beam_lisp/artifacts").join(format!("native-rust-{}-{nonce}", std::process::id()));
    std::fs::create_dir_all(&retained).map_err(|e| e.to_string())?;
    let result = (|| {
        let source = std::fs::canonicalize(source).map_err(|e| e.to_string())?;
        if !source.is_dir() || source == Path::new("/") {
            return Err("native source must be a self-contained directory".into());
        }
        let source = source.to_str().ok_or("native source address is not UTF-8")?;
        let snapshot_root = retained.join("source-retained");
        let mut snapshot_args = vec![
            "build".into(), "--impure".into(), "--file".into(),
            platform.join("nix/native-snapshot.nix").to_string_lossy().into_owned(),
            "--argstr".into(), "source".into(), source.into(),
            "--argstr".into(), "crate".into(), name.into(), "--json".into(),
            "--out-link".into(), snapshot_root.to_string_lossy().into_owned(),
            "--max-jobs".into(), "0".into()];
        if version == 2 {
            snapshot_args.extend([
                "--arg".into(), "version".into(), "2".into(),
                "--argstr".into(), "member".into(), requested["member"].as_str().ok_or("missing workspace member")?.into(),
                "--argstr".into(), "package".into(), requested["package"].as_str().ok_or("missing Cargo package")?.into()]);
        }
        let snapshot_text = capture(&platform, "nix", &snapshot_args, custody)?;
        let snapshots: Value = serde_json::from_slice(&snapshot_text).map_err(|e| e.to_string())?;
        let rows = snapshots.as_array().filter(|rows| rows.len() == 1).ok_or("expected one native source snapshot")?;
        let snapshot = rows[0]["outputs"]["out"].as_str().ok_or("missing native source snapshot")?;
        if !store_object(snapshot) || std::fs::read_link(&snapshot_root).map_err(|e| e.to_string())? != Path::new(snapshot) {
            return Err("native source snapshot lacks its requester root".into());
        }
        let mut request = requested.clone();
        request["source"] = json!(snapshot);
        let root = retained.join("retained");
        let output = capture(&platform, "nix", &[
            "build".into(), "--impure".into(), "--file".into(),
            platform.join("nix/native-artifact.nix").to_string_lossy().into_owned(),
            "--argstr".into(), "requestJson".into(), request.to_string(), "--json".into(),
            "--out-link".into(), root.to_string_lossy().into_owned(),
            "--max-jobs".into(), "0".into(), "--cores".into(), "1".into(),
            "--option".into(), "timeout".into(), "300".into()], custody)?;
        let rows: Value = serde_json::from_slice(&output).map_err(|e| e.to_string())?;
        let rows = rows.as_array().filter(|rows| rows.len() == 1).ok_or("expected one native output")?;
        let out = rows[0]["outputs"]["out"].as_str().ok_or("missing native output")?;
        let library = verify(Path::new(out), &request)?;
        if std::fs::read_link(&root).map_err(|e| e.to_string())? != Path::new(out) {
            return Err("native retention does not name its product".into());
        }
        let receipt = json!({"request":request,"output":out,"library":library,
                              "manifest":serde_json::from_slice::<Value>(&std::fs::read(Path::new(out).join("artifact.json")).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?,
                              "retention-root":root,"derivation":rows[0]["drvPath"]});
        std::fs::write(retained.join("receipt.json"), receipt.to_string()).map_err(|e| e.to_string())?;
        Ok(library)
    })();
    if result.is_err() { let _ = std::fs::remove_dir_all(retained); }
    result
}

fn capture(platform: &Path, tool: &str, argv: &[String], custody: &crate::BuildLock) -> Result<Vec<u8>, String> {
    let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
    let mut command = std::process::Command::new("systemd-run");
    command.args(["--user", "--quiet", "--wait", "--collect", "--pipe", "--expand-environment=no",
                  "--property=MemoryMax=1G", "--property=MemorySwapMax=0", "--property=RuntimeMaxSec=305",
                  "--property=KillMode=control-group"])
        .arg(format!("--unit=bl-artifact-{}-{nonce}.service", std::process::id()))
        .arg(format!("--working-directory={}", platform.display()))
        .arg("--").arg(tool).args(argv).stderr(std::process::Stdio::inherit());
    custody.prepare_command(&mut command)?;
    let output = command.output().map_err(|e| format!("native artifact command could not start: {e}"))?;
    if !output.status.success() { return Err(format!("native artifact command failed: {}", output.status)); }
    if output.stdout.len() > 65536 { return Err("native machine result exceeds capacity".into()); }
    Ok(output.stdout)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn workspace_requests_are_closed_and_contained() {
        let request = json!({"version":2,"source":"/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-workspace",
            "member":"crates/demo","package":"workspace-demo","crate":"demo_alias",
            "abi":"workspace-v1","target":"x86_64-linux"});
        assert_eq!(validate_request(&request, true).unwrap(), 2);
        for member in ["../demo", "/demo", "crates/../demo", "crates//demo", "target/demo", "crates/.git"] {
            let mut invalid = request.clone();
            invalid["member"] = json!(member);
            assert!(validate_request(&invalid, true).is_err(), "accepted {member}");
        }
        let mut unknown = request.clone();
        unknown["command"] = json!("cargo build");
        assert!(validate_request(&unknown, true).is_err());
        let mut mutable = request.clone();
        mutable["source"] = json!("/tmp/workspace");
        assert!(validate_request(&mutable, false).is_ok());
        assert!(validate_request(&mutable, true).is_err());
        let mut missing = request.clone();
        missing.as_object_mut().unwrap().remove("package");
        assert!(validate_request(&missing, true).is_err());
    }
    #[test]
    fn external_platform_recipe_and_lock_are_build_inputs() {
        crate::builder_tests::custody_source_identity();
        let root = std::env::temp_dir().join(format!("bl-platform-stamp-{}", std::process::id()));
        std::fs::create_dir_all(root.join("nix")).unwrap();
        let initial = stamp_inputs(&root);
        std::fs::write(root.join("nix/native-artifact.nix"), "recipe-v1").unwrap();
        let recipe = stamp_inputs(&root);
        assert_ne!(initial, recipe);
        std::fs::write(root.join("flake.lock"), "lock-v2").unwrap();
        assert_ne!(recipe, stamp_inputs(&root));
        let locked = stamp_inputs(&root);
        std::fs::write(root.join("executor.json"), "executor-v2").unwrap();
        assert_ne!(locked, stamp_inputs(&root));
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn mutable_and_traversing_products_are_refused() {
        crate::builder_tests::custody_source_identity();
        assert!(!store_object("/tmp/old-library"));
        assert!(!store_object(&format!("/nix/store/{}é-tail", "a".repeat(31))));
        assert!(!store_object("/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-demo/../other"));
        assert!(verify(Path::new("/tmp/old-library"), &json!({})).is_err());
    }
    #[test]
    #[ignore = "requires a prepared native artifact receipt"]
    fn actual_source_product_is_bound_to_its_request() {
        crate::builder_tests::custody_source_identity();
        let receipt = std::env::var_os("BL_NIX_ARTIFACT_TEST_RECEIPT").expect("prepared native artifact receipt required");
        let receipt: Value = serde_json::from_slice(&std::fs::read(receipt).unwrap()).unwrap();
        let output = Path::new(receipt["output"].as_str().unwrap());
        let mut request = receipt["request"].clone();
        assert_eq!(verify(output, &request).unwrap(), Path::new(receipt["library"].as_str().unwrap()));
        request["abi"] = json!("wrong-abi");
        assert!(verify(output, &request).is_err());
    }
    #[test]
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    #[ignore = "requires a prepared Source receipt and Nix platform"]
    fn actual_bootstrap_preparation_uses_same_source_product() {
        crate::builder_tests::custody_source_identity();
        let receipt = std::env::var_os("BL_NIX_ARTIFACT_TEST_RECEIPT").expect("prepared native artifact receipt required");
        assert_eq!(std::env::var("BL_NATIVE_PROVIDER").as_deref(), Ok("nix"));
        let receipt: Value = serde_json::from_slice(&std::fs::read(receipt).unwrap()).unwrap();
        let root = std::env::temp_dir().join(format!("bl-nix-bootstrap-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let result = || {
            std::fs::create_dir_all(root.join("native")).unwrap();
            std::os::unix::fs::symlink(receipt["request"]["source"].as_str().unwrap(), root.join("native/lazy_memo")).unwrap();
            let store = crate::Store { root: root.join("store") };
            let custody = crate::BuildLock::take(&store).unwrap();
            crate::build_natives(&root, &root.join("build.log"), &custody).unwrap();
            assert_eq!(std::fs::read_link(root.join("priv/native/lazy_memo.so")).unwrap(),
                       Path::new(receipt["library"].as_str().unwrap()));
            assert_eq!(std::fs::read(root.join("priv/native/lazy_memo.so")).unwrap(),
                       std::fs::read(receipt["library"].as_str().unwrap()).unwrap());
        };
        let panic = std::panic::catch_unwind(result);
        std::fs::remove_dir_all(&root).unwrap();
        if let Err(error) = panic { std::panic::resume_unwind(error); }
    }

}
