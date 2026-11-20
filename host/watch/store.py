"""The watcher's folder, read by the hub: JSON snapshots and the activity log."""

import json
import os
import time
from typing import Any, TypedDict

from .settings import EVENTS_KEPT, WATCH_DIR

Json = Any  # a file's JSON before the caller states its shape


class Container(TypedDict):
    """A containers.json row."""

    name: str
    service: str
    stack: str  # '' = not one of ours; 'coolify' = Coolify's own
    state: str | None  # Docker's: running, exited, ...
    status: str | None
    image: str | None
    created: str | None


class StackRef(TypedDict):
    id: str
    uuid: str


class Containers(TypedDict):
    """containers.json."""

    at: float
    items: list[Container]
    stacks: list[StackRef]


class State(TypedDict, total=False):
    """state.json: what the checks remember between rounds."""

    alerted: dict[str, int]  # storage key -> level last alerted
    unmounted: list[str]
    secrets: dict[str, str]  # file -> sha256
    extra_secrets: dict[str, str]


def path(*parts: str) -> str:
    return os.path.join(WATCH_DIR, *parts)


def load(name: str, default: object) -> Json:
    try:
        with open(path(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def dump(name: str, data: object) -> None:
    os.makedirs(path(), exist_ok=True)
    tmp = path(name + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, path(name))


def event(kind: str, title: str, detail: str = '', ok: bool = True) -> None:
    line = json.dumps({'at': time.time(), 'kind': kind, 'title': title, 'detail': detail, 'ok': ok})
    with open(path('events.jsonl'), 'a') as f:
        f.write(line + '\n')


def trim_events() -> None:
    try:
        with open(path('events.jsonl')) as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) > EVENTS_KEPT * 1.2:
        with open(path('events.jsonl'), 'w') as f:
            f.writelines(lines[-EVENTS_KEPT:])
