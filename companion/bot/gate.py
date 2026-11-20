"""Which of the agent's files may leave: only files in its outbox folder, of an allowed type, under the size cap."""

import os
from collections.abc import Iterable

TYPES = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.webm',
    '.csv', '.xlsx', '.xls', '.docx', '.doc', '.txt', '.md', '.zip',
}  # fmt: skip
MAX = 50 * 1024 * 1024  # bytes per file


def files(box: str, names: Iterable[str]) -> tuple[list[str], list[str]]:
    """(ok paths, refused reasons) for the file `names` the agent put in `box`."""
    ok: list[str] = []
    refused: list[str] = []
    for f in names:
        p = os.path.realpath(os.path.join(box, os.path.basename(str(f))))
        if not p.startswith(os.path.realpath(box) + os.sep) or not os.path.isfile(p):
            refused.append(f'{f} (missing)')
        elif os.path.splitext(p)[1].lower() not in TYPES:
            refused.append(f'{os.path.basename(p)} (file type not allowed)')
        elif os.path.getsize(p) > MAX:
            refused.append(f'{os.path.basename(p)} (over 50 MB)')
        else:
            ok.append(p)
    return ok, refused
