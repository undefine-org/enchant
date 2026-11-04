#!/usr/bin/env python3
"""Make transient store locks readable to the unprivileged Actions cache saver.

Nix's advisory locks survive permission changes. Never unlink a lock, follow a
symlink, change payload bytes, or change ownership of the daemon's store.
"""
import errno
import os
from pathlib import Path
import re
import stat


def prepare(store):
    changed = 0
    with os.scandir(store) as entries:
        for entry in entries:
            if not re.fullmatch(r'[0-9a-z]{32}-.+\.lock', entry.name) or entry.is_symlink():
                continue
            try:
                fd = os.open(entry.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError as error:
                if error.errno in (errno.ENOENT, errno.ELOOP):
                    continue
                raise
            try:
                mode = os.fstat(fd).st_mode
                if stat.S_ISREG(mode) and not mode & stat.S_IROTH:
                    os.fchmod(fd, stat.S_IMODE(mode) | stat.S_IRGRP | stat.S_IROTH)
                    changed += 1
            finally:
                os.close(fd)
    return changed


if __name__ == '__main__':
    print(f'Prepared {prepare(Path("/nix/store"))} transient Nix store lock(s) for cache retention')
