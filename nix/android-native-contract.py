#!/usr/bin/env python3
"""Describe the SDK's exact lazy-memo source and NIF interface for Android."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def contract(root):
    crate = root / "native/lazy_memo"
    files = sorted([crate / name for name in ("Cargo.toml", "Cargo.lock", "build.rs")]
                   + list((crate / "src").rglob("*.rs")))
    sources = {p.relative_to(crate).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in files}
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    facade = (root / "priv/host/lazy_memo.bl").read_text()
    nifs = sorted([[name, len(args.split())] for name, args in
                   re.findall(r"\(defn (nif_[^\s\[]+)\s*\[([^\]]*)\]", facade)])
    if not nifs or len({name for name, _ in nifs}) != len(nifs):
        raise ValueError("missing or duplicate native declarations")
    return dict(version=1, kind="android-native-contract", crate="lazy_memo",
                source_sha256=digest, source_files=sources, nifs=nifs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(contract(args.root), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
