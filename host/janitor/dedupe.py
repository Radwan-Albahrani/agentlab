"""Hardlink identical package files (node_modules, the package caches) in an agent's workspace, the way bun and pnpm do
when their cache shares a mount with the project: every worktree's node_modules then costs about one copy."""

import hashlib
import os
import stat
import time
from collections import defaultdict

PACKAGE_DIRS = ('node_modules',)
CACHES = ('.cache/bun-install', '.cache/pnpm-store')  # where the agent image points bun's and pnpm's caches
MIN_BYTES = 4096  # smaller files cost a block either way
SETTLED_S = 3600  # files this new may still be mid-install


def _files(workspace):
    """Regular files under any node_modules or package cache in `workspace`, never following symlinks."""
    roots = [os.path.join(workspace, c) for c in CACHES]
    for top, dirs, _ in os.walk(workspace):
        dirs[:] = [d for d in dirs if d != '.git' and not os.path.islink(os.path.join(top, d))]
        for d in [d for d in dirs if d in PACKAGE_DIRS]:
            roots.append(os.path.join(top, d))
            dirs.remove(d)
    for root in roots:
        for top, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(top, d))]
            for f in files:
                yield os.path.join(top, f)


def _digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.digest()


def dedupe(workspace, dry=False, now=None):
    """-> (files linked, bytes freed). Only files with the same size, owner, mode and content become one inode."""
    now = time.time() if now is None else now
    by_shape = defaultdict(dict)  # (size, uid, gid, mode, device) -> {inode: [link count, paths]}
    for p in _files(workspace):
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_size < MIN_BYTES or now - st.st_mtime < SETTLED_S:
            continue
        by_shape[(st.st_size, st.st_uid, st.st_gid, st.st_mode, st.st_dev)].setdefault(st.st_ino, [st.st_nlink, []])[
            1
        ].append(p)
    linked = freed = 0
    for (size, *_), inodes in by_shape.items():
        if len(inodes) < 2:
            continue
        keep = {}  # content -> path of the inode everyone else will share
        for nlink, paths in inodes.values():
            try:
                key = _digest(paths[0])
            except OSError:
                continue
            if key not in keep:
                keep[key] = paths[0]
                continue
            done = 0
            for p in paths:
                if not dry:
                    tmp = f'{p}.agentlab-link'
                    try:
                        os.link(keep[key], tmp)
                        os.replace(tmp, p)
                    except OSError:
                        if os.path.lexists(tmp):
                            os.remove(tmp)
                        continue
                done += 1
            linked += done
            freed += size if done == nlink else 0  # the old inode goes only once nothing points to it
    return linked, freed
