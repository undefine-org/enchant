# Foundry's job mechanism needs an independent runtime while the target SDK is
# being produced. Use the verified compiler cohort and immutable framework
# Source; this package neither depends on nor pretends to be the target SDK.
{ pkgs, compiler, dependencies, source, platform, foundry ? import ./foundry-ledger.nix }:
let
  ledgerFiles = [
    "src/foundry/operations/deployment-runner.bl"
    "src/foundry/support/deployment-exec.bl"
    "src/foundry/support/deployment-runtime.bl"
    "src/foundry/support/deployment-tar.bl"
    "src/foundry/support/cli-kit.bl"
    "src/foundry/credentials/deployment-keyring.bl"
  ];
  ledger = pkgs.lib.fileset.toSource {
    root = foundry;
    fileset = pkgs.lib.fileset.unions (map (file: foundry + "/${file}") ledgerFiles);
  };
in pkgs.runCommand "beam-lisp-foundry-coordinator-runtime" {} ''
  mkdir -p "$out/bin" "$out/lib/beam_lisp-0.1.0/ebin" "$out/foundry"
  image="$out/lib/beam_lisp-0.1.0"
  prepared=$(readlink -f ${platform}/native-products)
  cp -a ${source}/priv "$image/priv"
  chmod -R u+w "$image/priv"
  rm -rf "$image/priv/bootstrap/seed"
  mkdir -p "$image/priv/bootstrap/seed" "$image/priv/native"
  cp -a ${compiler}/seed/. "$image/ebin/"
  cp -a ${compiler}/seed/. "$image/priv/bootstrap/seed/"
  cp ${source}/env.bl "$image/env.bl"
  for library in ${platform}/native-products/*.so; do
    ln -s "$library" "$image/priv/native/$(basename "$library")"
  done
  for dependency in ${dependencies}/ebin/*; do
    ln -s "$dependency" "$out/lib/$(basename "$dependency")"
  done
  ln -s lib/beam_lisp-0.1.0 "$out/image"
  cp -a ${ledger}/. "$out/foundry/"
  chmod -R u+w "$out/foundry"
  mkdir -p "$out/foundry/bin"
  cp ${./preparation-jobs.bl} "$out/foundry/bin/jobs.bl"
  cp ${./preparation-operation.bl} "$out/foundry/bin/preparation-operation.bl"
  cat > "$out/foundry/env.bl" <<'PROJECT'
  {:name "foundry-artifact-coordinator"
   :paths ["src/foundry/operations" "src/foundry/support" "src/foundry/credentials"]}
  PROJECT
  cat > "$out/boot.exs" <<EOF_BOOT
  for path <- Path.wildcard("$out/lib/*/ebin"), do: Code.prepend_path(path)
  Code.prepend_path("$out/image/ebin")
  :code.del_path(~c".")
  BeamLisp.Launcher.start_app!(System.argv(), %{})
  EOF_BOOT
  cat > "$out/bin/bl" <<EOF_BL
  #!${pkgs.runtimeShell}
  set -eu
  unset BL_INTERNAL_PRODUCER BL_SDK_PRODUCT BL_CHECKOUT_ROOT BL_CHECKOUT_COLD
  export BL_ROOT="$out/image" BEAM_LISP_DEV=0 BL_DAEMON=off
  export BL_BIN=${platform}/bin/drop-launcher
  export BL_ARTIFACT_PLATFORM=${platform}/artifact-platform
  export BL_PREPARED_NATIVES="$prepared"
  export PATH=${platform}/bin:\$PATH
  export FOUNDRY_ROOT="$out/foundry" FOUNDRY_BL="$out/bin/worker"
  export FOUNDRY_TOOL_PATH=${platform}/bin
  export BL_PREPARATION_COORDINATOR="$out"
  export BL_PREPARATION_PLATFORM="$(readlink -f ${platform}/artifact-platform)"
  export LANG=C.UTF-8 LC_ALL=C.UTF-8
  export ELIXIR_ERL_OPTIONS='+fnu +S 4:4 +SDcpu 2:2 +SDio 1:1'
  cd "$out/foundry"
  exec ${platform}/bin/elixir "$out/boot.exs" "\$@"
  EOF_BL
  cat > "$out/bin/worker" <<EOF_WORKER
  #!${pkgs.runtimeShell}
  set -eu
  job=
  previous=
  for argument do
    if [ "\$previous" = --id ]; then job=\$argument; fi
    previous=\$argument
  done
  case "\$job" in job_*) ;; *) echo 'worker job id required' >&2; exit 64 ;; esac
  case "\$job" in *[!A-Za-z0-9_]*) exit 64 ;; esac
  # Operator Nix policy crosses the manager boundary as runtime environment,
  # never as request data or a captured credential in this immutable product.
  manager_environment=()
  worker_environment=()
  for name in NIX_CONFIG NIX_SSHOPTS NIX_USER_CONF_FILES NIX_CONF_DIR SSH_AUTH_SOCK XDG_CONFIG_HOME; do
    if [[ -v \$name ]]; then
      manager_environment+=("--setenv=\$name")
      worker_environment+=("\$name=\''${!name}")
    fi
  done
  exec ${platform}/bin/systemd-run --user --quiet --collect --wait --pipe --expand-environment=no \\
    --working-directory="$out/foundry" --unit="foundry-artifact-\$job.service" \\
    --property=MemoryMax=4G --property=MemorySwapMax=0 \\
    --property=RuntimeMaxSec=3600 --property=KillMode=control-group \\
    "\''${manager_environment[@]}" \\
    -- ${pkgs.coreutils}/bin/env -i "HOME=\$HOME" "PATH=${platform}/bin:/usr/bin:/bin" \\
      "XDG_RUNTIME_DIR=\''${XDG_RUNTIME_DIR:-}" \\
      "DBUS_SESSION_BUS_ADDRESS=\''${DBUS_SESSION_BUS_ADDRESS:-}" \\
      "\''${worker_environment[@]}" \\
      "$out/bin/bl" --cold "\$@"
  EOF_WORKER
  chmod 555 "$out/bin/bl" "$out/bin/worker"
  printf '%s\n' '${builtins.toJSON {
    version = 1;
    kind = "artifact-coordinator-runtime";
    target = "x86_64-linux";
    compiler = toString compiler;
    dependencies = toString dependencies;
    source = toString source;
    platform = toString platform;
    foundry = toString ledger;
  }}' > "$out/artifact.json"
''
