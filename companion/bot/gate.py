"""Which of the agent's files may leave: only files in its outbox folder, of an allowed type, under the size cap."""

import os
from collections.abc import Iterable

TYPES = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.webm',
    '.csv', '.xlsx', '.xls', '.docx', '.doc', '.txt', '.md', '.zip',
}  # fmt: skip
MAX = 50 * 1024 * 1024  # bytes per file


def one(box: str, name: str) -> tuple[str, str]:
    """(path, '') for a file the agent put in `box` that may leave, else ('', why not)."""
    p = os.path.realpath(os.path.join(box, os.path.basename(str(name))))
    if not p.startswith(os.path.realpath(box) + os.sep) or not os.path.isfile(p):
        return '', 'missing'
    if os.path.splitext(p)[1].lower() not in TYPES:
        return '', 'file type not allowed'
    if os.path.getsize(p) > MAX:
        return '', 'over 50 MB'
    return p, ''


def files(box: str, names: Iterable[str]) -> tuple[list[str], list[str]]:
    """(ok paths, refused reasons) for the file `names` the agent put in `box`."""
    checked = [(os.path.basename(str(n)), *one(box, n)) for n in names]
    return [p for _, p, _ in checked if p], [f'{n} ({why})' for n, p, why in checked if not p]
