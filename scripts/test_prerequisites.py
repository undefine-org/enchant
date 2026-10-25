"""Refuse known missing external test tools before starting a candidate VM.

The manifest is deliberately scoped. Tool resolution is an admission check;
the actual watcher/NIF tests still establish that the selected tools work.
"""
import json
from pathlib import Path
import shutil
import sys


def require(root, files, *, platform=None, path=None):
    root = Path(root).resolve()
    manifest = json.loads((root / "scripts/test-prerequisites.json").read_text())
    if manifest.get("version") != 1 or not isinstance(manifest.get("tests"), dict):
        raise ValueError("Invalid test prerequisite manifest")
    inventory = manifest["tests"]
    for name, targets in inventory.items():
        if (not isinstance(name, str) or Path(name).is_absolute()
                or str((root / name).resolve().relative_to(root)) != name
                or not isinstance(targets, dict) or not targets):
            raise ValueError("Invalid test prerequisite entry: " + str(name))
        for target, tools in targets.items():
            if (target not in {"all", "linux", "darwin", "win32"}
                    or not isinstance(tools, list) or not tools
                    or any(not isinstance(tool, str) or not tool or "/" in tool or "\\" in tool
                           for tool in tools) or len(set(tools)) != len(tools)):
                raise ValueError("Invalid test prerequisite tools: " + name)
    platform = platform or sys.platform
    selected, missing = [], []
    for raw in dict.fromkeys(files):
        name = str((root / raw).resolve().relative_to(root))
        targets = inventory.get(name, {})
        for tool in dict.fromkeys(targets.get("all", []) + targets.get(platform, [])):
            executable = shutil.which(tool, path=path)
            selected.append({"test": name, "tool": tool, "executable": executable})
            if executable is None:
                missing.append(name + ": " + tool)
    if missing:
        raise RuntimeError("Missing test prerequisites before VM startup: " + "; ".join(missing))
    return selected
