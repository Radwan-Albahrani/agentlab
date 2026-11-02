"""Small file helpers shared by the stores: tolerant JSON reads, atomic JSON writes, kept versions."""

import contextlib
import json
import os
import shutil
import time
from pathlib import Path


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_jsonl(path, limit):
    """The last `limit` lines that parse, newest first."""
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        with contextlib.suppress(ValueError):
            out.append(json.loads(line))
    return out[::-1]


def write_json(path, data):
    """Write through a temp file so a reader never sees half a file."""
    with open(f'{path}.tmp', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)
    os.replace(f'{path}.tmp', path)
    os.chmod(path, 0o644)


def write_in_place(path, text):
    """Overwrite the same file (not a replacement inode), so containers that bind-mount it see the change."""
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def versions(folder):
    """Kept versions in `folder`, newest first (names are timestamps)."""
    try:
        return sorted(os.listdir(folder), reverse=True)
    except OSError:
        return []


def keep_version(path, folder, keep):
    """Copy `path` into `folder` as a new version, keeping only the newest `keep`."""
    if not os.path.isfile(path):
        return
    os.makedirs(folder, exist_ok=True)
    shutil.copy2(path, os.path.join(folder, time.strftime('%Y%m%d-%H%M%S')))
    for old in versions(folder)[keep:]:
        os.remove(os.path.join(folder, old))


def read_version(folder, version):
    if version not in versions(folder):
        raise ValueError('That version is gone.')
    return Path(folder, version).read_text(encoding='utf-8', errors='replace')
