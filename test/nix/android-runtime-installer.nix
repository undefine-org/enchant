# Finite JVM filesystem proof; deliberately outside the SDK engine recipe roots.
{ source }:
let
  lock = builtins.fromJSON (builtins.readFile ../../flake.lock);
  pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
  input = import ../../nix/project-source.nix {
    inherit source;
    rootsJson = builtins.toJSON [ "priv/android/kotlin/BlRuntime.kt" "test/android/BlRuntimeTest.kt" ];
  };
  # Released test-only jars avoid compiling an unrelated Gradle/Maven graph.
  junit = pkgs.fetchurl {
    url = "https://repo.maven.apache.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar";
    hash = "sha256-jklbY0Rp1k+4rPo0laBly6zIoP/1XOHjEAe+TBbcV9M=";
  };
  hamcrest = pkgs.fetchurl {
    url = "https://repo.maven.apache.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar";
    hash = "sha256-Zv3vkelzk0jfeglqo4SlaF9Oh1WEzOiThqekclHE2Ok=";
  };
  bounded = import ../../nix/bounded-build.nix { inherit pkgs; memoryMiB = 3072; cpuCount = 2; };
in bounded (pkgs.runCommand "beam-lisp-android-installer-tests" {
  __structuredAttrs = true;
  nativeBuildInputs = [ pkgs.kotlin pkgs.jdk pkgs.python3 pkgs.util-linux ];
  outputChecks.out.allowedReferences = [];
} ''
  cp ${input}/priv/android/kotlin/BlRuntime.kt BlRuntime.kt
  cp ${input}/test/android/BlRuntimeTest.kt BlRuntimeTest.kt
  export JAVA_OPTS='-Xms64m -Xmx768m'
  kotlinc BlRuntime.kt BlRuntimeTest.kt -jvm-target 1.8 -cp ${junit}:${hamcrest} -include-runtime -d tests.jar
  # Permission-denial controls must observe actual mode bits, including in the VM.
  jvm_exit=0
  setpriv --bounding-set=-dac_override,-dac_read_search --no-new-privs \
    java -Xmx256m -cp tests.jar:${junit}:${hamcrest} org.junit.runner.JUnitCore \
    io.beamlisp.android.BlRuntimeTest > junit.log 2>&1 || jvm_exit=$?
  mkdir -p "$out"
  python3 - "$out" "$jvm_exit" <<'PY'
  import hashlib,json,os,re,sys
  from pathlib import Path
  log=Path('junit.log').read_text()
  good=re.search(r'OK \((\d+) tests\)',log)
  bad=re.search(r'Tests run: (\d+),\s+Failures: (\d+)',log)
  status='passed' if int(sys.argv[2])==0 and good and int(good[1])>0 else 'failed'
  result={'kind':'android-runtime-installer-jvm','status':status,'exit':int(sys.argv[2]),
          'tests':int(good[1]) if good else int(bad[1]) if bad else 0,
          'failures':int(bad[2]) if bad else 0 if good else None,
          'worker_memory_kib':int(os.environ['BL_WORKER_MEMORY_KIB']),
          'worker_swap_kib':int(os.environ['BL_WORKER_SWAP_KIB']),
          'inputs_sha256':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest()
                           for name in ['BlRuntime.kt','BlRuntimeTest.kt']}}
  out=Path(sys.argv[1]);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
  (out/'run.log').write_text(re.sub(r'/nix/store/[0-9a-z]{32}-[^\s:]+','<store>',log))
  print(json.dumps(result))
  PY
'')
