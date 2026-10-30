"""Inventory the complete application product before it crosses publication.

Nix authenticates the store object. This check independently binds its expected
SDK/source and every emitted byte; the language still verifies artifact units.
"""
import hashlib
import json
from pathlib import Path
import re
import stat
import sys


def inventory(root):
    rows = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root).as_posix()
            if relative == "inventory.json":
                continue
            info = path.lstat()
            row = {"path": relative}
            if stat.S_ISDIR(info.st_mode):
                row["type"] = "directory"
                pending.append(path)
            else:
                if stat.S_ISLNK(info.st_mode):
                    target = str(path.readlink())
                    if not relative.startswith("native/") or not re.fullmatch(
                        r"/nix/store/[0-9a-z]{32}-[^/]+/lib/[A-Za-z_][A-Za-z0-9_]*\.so", target
                    ) or not stat.S_ISREG(Path(target).lstat().st_mode):
                        raise ValueError(f"unsupported product link: {relative}")
                    row.update(type="symlink", target=target)
                    contents = Path(target)
                elif stat.S_ISREG(info.st_mode):
                    row.update(type="file", executable=bool(info.st_mode & 0o111))
                    contents = path
                else:
                    raise ValueError(f"unsupported product entry: {relative}")
                with contents.open("rb") as stream:
                    row["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            rows.append(row)
            if len(rows) > 65536:
                raise ValueError("application inventory exceeds capacity")
    return sorted(rows, key=lambda row: row["path"])


def verify(root, sdk, source):
    manifest = root / "inventory.json"
    if not stat.S_ISREG(manifest.lstat().st_mode) or manifest.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("invalid application inventory")
    recorded = json.loads(manifest.read_text())
    if recorded != {"version": 1, "entries": inventory(root)}:
        raise ValueError("application inventory disagrees")
    descriptor = json.loads((root / "artifact.json").read_text())
    if descriptor != {"version": 1, "kind": "application", "source": source,
                      "sdk": sdk, "target": "x86_64-linux"}:
        raise ValueError("application identity disagrees")
    result = json.loads((root / "result.json").read_text())
    if result["errors"]:
        raise ValueError("application producer reported errors")
    return result


if __name__ == "__main__":
    mode, directory, *expected = sys.argv[1:]
    root = Path(directory)
    if mode == "write" and not expected:
        (root / "inventory.json").write_text(json.dumps(
            {"version": 1, "entries": inventory(root)}, sort_keys=True) + "\n")
    elif mode == "verify" and len(expected) == 2:
        print(json.dumps(verify(root, *expected), sort_keys=True))
    else:
        raise SystemExit("usage: application-inventory.py write ROOT | verify ROOT SDK SOURCE")
