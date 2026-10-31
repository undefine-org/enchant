#!/usr/bin/env python3
"""Evaluate real production derivations after independent edits; build no VMs."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
policy = json.loads((ROOT / "nix/engine-inputs.json").read_text())
with tempfile.TemporaryDirectory(prefix="sdk-input-boundaries-") as tmp:
    root = Path(tmp)
    ignore = shutil.ignore_patterns("target", ".git", ".bl", "__pycache__")
    for relative in policy["roots"]:
        source, dest = ROOT / relative, root / relative
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, dest, ignore=ignore)
        else:
            shutil.copy2(source, dest)
    def evaluate():
        expression = '''let
          root = /. + ROOT;
          lock = builtins.fromJSON (builtins.readFile (root + "/flake.lock"));
          pkgs = import (builtins.fetchTree lock.nodes.nixpkgs.locked).outPath { system = "x86_64-linux"; };
          beam = import (root + "/nix/beam.nix") {
            inherit pkgs;
            otp-src = (builtins.fetchTree lock.nodes.otp-src.locked).outPath;
            elixir-src = (builtins.fetchTree lock.nodes.elixir-src.locked).outPath;
          };
          products = import (root + "/nix/bl-drop.nix") {
            inherit pkgs; rustPkgs = pkgs; inherit (beam) erlang elixir;
          };
        in { compiler = products.compiler.drvPath; dependencies = products.dependencies.drvPath;
             sdk = products.sdk.drvPath; }
        '''.replace("ROOT", json.dumps(str(root)))
        return json.loads(subprocess.check_output(["nix-instantiate", "--read-write-mode", "--eval", "--strict", "--json",
            "--expr", expression, "--option", "experimental-features", "nix-command flakes"], text=True))
    baseline = evaluate()
    for relative, compiler_changes in [("priv/std/errors.bl", False),
                                        ("native/bl_json/src/lib.rs", False),
                                        ("priv/host/record.bl", True)]:
        path = root / relative
        original = path.read_bytes()
        path.write_bytes(original + (b"\n// input boundary\n" if path.suffix == ".rs" else b"\n; input boundary\n"))
        changed = evaluate()
        assert changed["dependencies"] == baseline["dependencies"], relative
        assert (changed["compiler"] != baseline["compiler"]) == compiler_changes, relative
        assert changed["sdk"] != baseline["sdk"], relative
        path.write_bytes(original)
        print("SDK INPUT BOUNDARY passed", relative, flush=True)
