"""Capture the same self-contained Git-visible inputs for both CI workers."""
import hashlib
from pathlib import Path
import shutil
import subprocess

ROOTS = {'.gitignore', '.github', 'AGENTS.md', 'README.md', 'README.bl.org', 'bin', 'nix',
         'scripts', 'test', 'priv', 'native', 'tooling', 'vendor', 'docs', 'research',
         'examples', 'env.bl', 'bl.lock', 'flake.nix', 'flake.lock', 'rust-toolchain', 'rust-toolchain.toml'}


def capture(project, snapshot):
    project, snapshot = Path(project).resolve(strict=True), Path(snapshot)
    snapshot.mkdir()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=project)
    copied = {}
    for raw in sorted(set(names.split(b'\0')) - {b''}):
        name = raw.decode()
        if Path(name).parts[0] not in ROOTS:
            continue
        source = project / name
        if not source.is_file():
            continue
        if not source.resolve().is_relative_to(project):
            raise ValueError('Source link escapes the checkout: ' + name)
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o777)
        copied[name] = hashlib.sha256(target.read_bytes()).digest()
    if any(not (project / name).is_file() or hashlib.sha256((project / name).read_bytes()).digest() != sha
           for name, sha in copied.items()):
        raise ValueError('Source changed during capture; retry the finite check')
