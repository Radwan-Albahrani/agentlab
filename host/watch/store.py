"""The watcher's folder, read by the hub: JSON snapshots and the activity log."""

import json
import os
import time

from .settings import EVENTS_KEPT, WATCH_DIR


def path(*parts):
    return os.path.join(WATCH_DIR, *parts)


def load(name, default):
    try:
        with open(path(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def dump(name, data):
    os.makedirs(path(), exist_ok=True)
    tmp = path(name + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, path(name))


def event(kind, title, detail='', ok=True):
    line = json.dumps({'at': time.time(), 'kind': kind, 'title': title, 'detail': detail, 'ok': ok})
    with open(path('events.jsonl'), 'a') as f:
        f.write(line + '\n')


def trim_events():
    try:
        with open(path('events.jsonl')) as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) > EVENTS_KEPT * 1.2:
        with open(path('events.jsonl'), 'w') as f:
            f.writelines(lines[-EVENTS_KEPT:])
