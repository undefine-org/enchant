//! The pre-BEAM consumer of the same fixed native artifact recipe used by Source.
use std::path::{Path, PathBuf};
use serde_json::{json, Value};

fn store_object(path: &str) -> bool {
    let Some(name) = path.strip_prefix("/nix/store/") else { return false };
    name.len() > 33 && name.as_bytes()[32] == b'-' && !name.contains('/')
        && name[..32].bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
}

/// Build resolution includes the selected trusted recipe/lock, even when the
/// platform lives outside the application's source tree.
pub(super) fn stamp_inputs(platform: &Path) -> Vec<String> {
    let mut inputs: Vec<PathBuf> = ["nix/native-artifact.nix", "nix/native-source.nix", "flake.lock",
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

pub(super) fn verify(output: &Path, request: &Value) -> Result<PathBuf, String> {
    let address = output.to_str().ok_or("native output address is not UTF-8")?;
    if !store_object(address) { return Err("native output must be a top-level store object".into()); }
    let manifest: Value = serde_json::from_slice(&std::fs::read(output.join("artifact.json"))
        .map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    let name = request.get("crate").and_then(Value::as_str).ok_or("missing crate")?;
    if !name.bytes().next().is_some_and(|b| b.is_ascii_alphabetic() || b == b'_') || !name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_') {
        return Err("invalid native crate name".into());
    }
    let relative = format!("lib/{name}.so");
    if request["version"] != 1 || manifest["version"] != 1 || manifest["kind"] != "native-library"
        || manifest["library"] != relative || request["target"] != "x86_64-linux"
        || ["crate", "source", "target", "abi"].iter().any(|key| request[*key].is_null() || manifest[*key] != request[*key])
        || !request["source"].as_str().is_some_and(store_object) {
        return Err("native product identity disagrees with its request".into());
    }
    let library = output.join(relative);
    if !std::fs::symlink_metadata(&library).map_err(|e| e.to_string())?.file_type().is_file() {
        return Err("native product is not a regular library".into());
    }
    let digest = crate::sha256_hex(&std::fs::read(&library).map_err(|e| e.to_string())?);
    if manifest["sha256"].as_str() != Some(&digest) {
        return Err("native product digest disagrees".into());
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
    if !cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        return Err("Nix native products currently support x86_64-linux".into());
    }
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
        let snapshot_text = capture(&platform, "nix-instantiate", &[
            "--eval".into(), "--strict".into(), "--json".into(), "--read-write-mode".into(),
            platform.join("nix/native-source.nix").to_string_lossy().into_owned(),
            "--argstr".into(), "source".into(), source.to_string_lossy().into_owned(),
            "--argstr".into(), "crate".into(), name.into()], custody)?;
        let snapshot: String = serde_json::from_slice(&snapshot_text).map_err(|e| e.to_string())?;
        if !store_object(&snapshot) { return Err("invalid native source snapshot".into()); }
        capture(&platform, "nix-store", &["--add-root".into(),
            retained.join("source-retained").to_string_lossy().into_owned(),
            "--indirect".into(), "--realise".into(), snapshot.clone()], custody)?;
        let request = json!({"version":1,"source":snapshot,"crate":name,
                             "abi":format!("beam-lisp-native-{name}-v1"),"target":"x86_64-linux"});
        let root = retained.join("retained");
        let output = capture(&platform, "nix", &[
            "build".into(), "--impure".into(), "--file".into(),
            platform.join("nix/native-artifact.nix").to_string_lossy().into_owned(),
            "--argstr".into(), "requestJson".into(), request.to_string(), "--json".into(),
            "--out-link".into(), root.to_string_lossy().into_owned(),
            "--max-jobs".into(), "1".into(), "--cores".into(), "1".into(),
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
