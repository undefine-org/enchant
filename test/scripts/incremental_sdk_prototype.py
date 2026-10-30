#!/usr/bin/env python3
"""Serial real Nix workers, immutable previous units and fresh SDK consumers.

Use an existing SDK; never invokes checkout bin/bl or regenerates a compiler.
All evidence and GC roots remain beneath --out. No installed SDK is changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
RECIPE = ROOT / "nix/incremental-sdk-prototype.nix"
PROVIDER = "priv/std/sdk/artifact/provider.bl"
CONSUMER = "priv/std/sdk/artifact/consumer.bl"
UNRELATED = "priv/std/sdk/artifact/unrelated.bl"
REAL = "priv/std/errors.bl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    metadata = json.loads((sdk / "artifact.json").read_text())
    out = args.out.absolute()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "source"
    shutil.copytree(metadata["source"], source)
    for path in [source, *source.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o200)
    fixture = ROOT / "test/fixtures/sdk-artifacts"
    for name in ("provider.bl", "consumer.bl"):
        path = source / "priv/std/sdk/artifact" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture / name, path)
    (source / UNRELATED).write_text("(ns sdk.artifact.unrelated) (defn answer [] 7)\n")
    selection = [PROVIDER, CONSUMER, UNRELATED, REAL]
    report = {"status": "running", "sdk": str(sdk), "stages": [],
              "scope": "selected-sealed-sdk-fragment; production entry unchanged"}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def command(name, argv, *, expected=0):
        start = time.monotonic()
        log = out / (name + ".log")
        with log.open("w") as stream:
            done = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        stage = {"name": name, "seconds": round(time.monotonic() - start, 3),
                 "exit": done.returncode, "log": str(log)}
        report["stages"].append(stage)
        save()
        print(name, json.dumps(stage), flush=True)
        if (done.returncode == 0) != (expected == 0):
            raise RuntimeError(log.read_text()[-6000:])
        return log.read_text()

    def arguments():
        return [str(RECIPE), "--argstr", "sdk", str(sdk),
                "--argstr", "source", str(source), "--argstr", "selectionJson", json.dumps(selection)]

    def identities():
        return "let p = import " + str(RECIPE) + " { sdk = " + json.dumps(str(sdk)) + "; source = " + json.dumps(str(source)) + "; selectionJson = " + json.dumps(json.dumps(selection)) + "; }; in { compiler = toString p.compiler; dependencies = toString p.dependencies; }"

    def check_identities(name):
        text = command(name, ["nix-instantiate", "--eval", "--strict", "--json", "--expr", identities(),
                              "--option", "experimental-features", "nix-command flakes"])
        assert json.loads(text) == {key: metadata[key] for key in ("compiler", "dependencies")}

    def tree_hashes(directory):
        return {str(p.relative_to(directory)): ("link", str(p.readlink())) if p.is_symlink()
                else ("file", hashlib.sha256(p.read_bytes()).hexdigest())
                for p in directory.rglob("*") if p.is_symlink() or p.is_file()}

    def build(name, previous, compiled, restored, answer, *, real_value=None):
        extra = ["--argstr", "previous", str(previous)] if previous else []
        pointer = out / name
        build_log = command(name, ["nix-build", *arguments(), *extra, "-A", "product", "--out-link", str(pointer),
                       "--max-jobs", "0", "--option", "timeout", "550",
                       "--option", "experimental-features", "nix-command flakes"])
        product = pointer.resolve(strict=True)
        result = json.loads((product / "result.json").read_text())
        report["stages"][-1]["result"] = result
        drv = subprocess.check_output(["nix-store", "--query", "--deriver", str(product)], text=True).strip()
        worker_log = subprocess.check_output(["nix", "--extra-experimental-features", "nix-command", "log", drv],
                                             text=True, stderr=subprocess.STDOUT, timeout=20)
        (out / (name + "-worker.log")).write_text(worker_log)
        metrics = [json.loads(line[len("INCREMENTAL-SDK "):]) for line in worker_log.splitlines()
                   if line.startswith("INCREMENTAL-SDK ")][-1]
        report["stages"][-1].update(product=str(product), derivation=drv,
                                   worker_milliseconds=metrics["milliseconds"],
                                   fresh_worker=("building '" + drv + "'") in build_log)
        assert set(result["compiled"]) == set(compiled), result
        assert set(result["restored"]) == set(restored), result
        assert result["compile_calls"] == len(compiled), result
        assert result["compiler"] == metadata["compiler"]
        assert result["dependencies"] == metadata["dependencies"]
        if previous:
            for namespace in restored:
                before = previous / "units" / namespace
                after = product / "units" / namespace
                hashes = lambda d: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}
                assert hashes(before) == hashes(after), namespace
        # A cold source-free receiver gets a private image and an empty cache.
        image = out / (name + "-receiver") / "lib/beam_lisp-0.1.0"
        shutil.copytree(product / "image", image, symlinks=True)
        for path in [image, *image.rglob("*")]:
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o200)
                if path.is_file() and path.name.endswith((".bl", ".bl.md", ".bl.org")):
                    path.unlink()
        env = dict(PATH=metadata["platform"] + "/bin:" + os.environ.get("PATH", ""),
                   BL_ROOT=str(image), BL_INCREMENTAL_BASE=str(sdk),
                   BL_INCREMENTAL_IMAGE=str(image), BL_INCREMENTAL_ANSWER=str(answer),
                   BL_DAEMON="off", XDG_CACHE_HOME=str(out / (name + "-empty-cache")),
                   ELIXIR_ERL_OPTIONS="+S 4:4 +SDcpu 2:2 +SDio 1:1")
        if real_value is not None:
            env["BL_INCREMENTAL_REAL_VALUE"] = str(real_value)
        # Pass the exact receiver environment through the process-tree cap.
        argv = ["systemd-run", "--user", "--quiet", "--collect", "--wait", "--pipe",
                "--property=MemoryMax=2G", "--property=MemorySwapMax=0", "--property=RuntimeMaxSec=120"]
        for key, value in env.items():
            if key.startswith(("BL_", "XDG_", "ELIXIR_")) or key == "PATH":
                argv.append(f"--setenv={key}={value}")
        argv += [metadata["platform"] + "/bin/elixir", str(ROOT / "test/scripts/incremental_sdk_receiver.exs")]
        text = command(name + "-consumer", argv)
        assert "INCREMENTAL-CONSUMER passed" in text, text
        save()
        return product

    try:
        # Evaluation alone proves ordinary Source edits do not change the
        # compiler/dependency identities. These outputs reference the baseline.
        check_identities("input-boundaries-before")
        all_ns = ["sdk.artifact.provider", "sdk.artifact.consumer", "sdk.artifact.unrelated", "errors"]
        first = build("initial", None, all_ns, [], 42)
        # Distributed Nix check-mode does not dispatch on every daemon version.
        # An unused derivation parameter forces an independent ordinary worker
        # with identical compilation inputs. Compare every byte and link.
        reproduction = out / "reproduction"
        command("reproduction", ["nix-build", *arguments(), "-A", "product", "--arg", "reproduction", "true",
                                 "--out-link", str(reproduction), "--max-jobs", "0", "--option", "timeout", "550",
                                 "--option", "experimental-features", "nix-command flakes"])
        assert reproduction.resolve() != first
        assert tree_hashes(first) == tree_hashes(reproduction.resolve())
        report["stages"][-1]["byte_identical"] = True
        unchanged = build("unchanged", first, [], all_ns, 42)
        (source / PROVIDER).write_text("(ns sdk.artifact.provider) (def base 50) (defmacro forty [] base)\n")
        macro = build("macro-edit", unchanged, all_ns[:2], all_ns[2:], 52)
        with (source / REAL).open("a") as stream:
            stream.write("\n(defn incremental-prototype-value [] 73)\n")
        real = build("real-library-edit", macro, ["errors"], all_ns[:3], 52, real_value=73)
        selection.remove(UNRELATED)
        (source / UNRELATED).unlink()
        deleted = build("deleted", real, [], [ns for ns in all_ns if ns != "sdk.artifact.unrelated"], 52, real_value=73)
        assert json.loads((deleted / "result.json").read_text())["removed"] == ["sdk.artifact.unrelated"]
        assert not (deleted / "image/ebin/Elixir.BeamLisp.Ns.Sdk.Artifact.Unrelated.beam").exists()
        # Same whole-tree edit as the original regression: compiler/deps must
        # remain identical, and a changed compiler must refuse this reuse path.
        check_identities("stable-compiler-after-edits")
        with (source / "priv/host/aot.bl").open("a") as stream:
            stream.write("\n; changed compiler control\n")
        text = command("changed-compiler-refused", ["nix-instantiate", "--eval", "--strict", "--expr", identities(),
                                                   "--option", "experimental-features", "nix-command flakes"], expected=1)
        assert "qualify a new compiler first" in text
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
