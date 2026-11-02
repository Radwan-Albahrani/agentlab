"""<data>/secrets (mounted at /secrets) and what each file is for (secrets-map.json). Cluster secrets sit at the top;
each companion's in companions/<name>/ (its folder is mounted into it alone). Edits are written in place (services
that mount a single file see the change); the watcher then applies them where they are used.
Optionally, one more folder from the host ([hub] extra_secrets: secrets of other things on the machine) shows as its
own group under extra/<file>, described by its own map; the screen is admins only either way."""

import json
import os
import re
from pathlib import Path

import cluster

from . import watch
from .files import keep_version, read_json, read_version, versions, write_in_place

SECRETS = os.environ.get('SECRETS_DIR', '/secrets')
MAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'secrets-map.json')
EXTRA = os.environ.get('HUB_EXTRA_SECRETS', '')  # the mounted host folder, '' when there is none
EXTRA_MAP = os.environ.get('HUB_EXTRA_SECRETS_MAP', '')
EXTRA_LABEL = os.environ.get('HUB_EXTRA_SECRETS_LABEL', '') or 'Other secrets'
EXTRA_PREFIX = 'extra/'
VERSIONS_KEPT = 5
FILE_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$')


def _folders():
    """Where secrets live, relative to SECRETS: the top and each configured companion's folder (plus extra/)."""
    return ['', *(f'companions/{n}/' for n in cluster.companions()), *([EXTRA_PREFIX] if EXTRA else [])]


def _root(folder):
    """(directory on disk, prefix inside it) for one of _folders()."""
    return (EXTRA, '') if folder == EXTRA_PREFIX else (SECRETS, folder)


def _path(name):
    folder, _, file = (name or '').rpartition('/')
    folder += '/' if folder else ''
    if folder not in _folders() or not FILE_OK.match(file):
        raise ValueError('Use letters, digits, dots, dashes or underscores (in companions/<name>/ for a companion).')
    root, inner = _root(folder)
    return os.path.join(root, inner + file)


def _versions_folder(name):
    if EXTRA and name.startswith(EXTRA_PREFIX):
        return os.path.join(EXTRA, '.versions', name[len(EXTRA_PREFIX) :])
    return os.path.join(SECRETS, '.versions', name)


def _expand(value, name):
    if isinstance(value, str):
        return value.replace('{companion}', name).replace('Companion', cluster.display_name(name))
    if isinstance(value, list):
        return [_expand(v, name) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v, name) for k, v in value.items()}
    return value


def secrets_map():
    """{file name: what it is}, with every {companion} entry spelled out for each companion in cluster.json."""
    out = {}
    for key, info in read_json(MAP, {}).items():
        if key == '_about':
            continue
        if '{companion}' in key:
            out |= {key.replace('{companion}', n): _expand(info, n) for n in cluster.companions()}
        else:
            out[key] = info
    if EXTRA and EXTRA_MAP:
        out |= {EXTRA_PREFIX + k: v for k, v in read_json(EXTRA_MAP, {}).items() if k != '_about' and '/' not in k}
    return out


def all_secrets():
    described = secrets_map()
    out = []
    names = []
    for folder in _folders():
        root, inner = _root(folder)
        try:
            names += [folder + f for f in sorted(os.listdir(os.path.join(root, inner)))]
        except OSError:
            continue
    for name in names:
        if not FILE_OK.match(name.rpartition('/')[2]):
            continue  # hidden entries (.versions) and odd names aren't secrets
        path = _path(name)
        if not os.path.isfile(path):
            continue
        info = described.get(name, {})
        out.append(
            {
                'name': name,
                **{k: info.get(k, '') for k in ('label', 'note', 'about', 'how')},
                'used_by': info.get('used_by', []),
                'apply': info.get('apply', []),
                'modified': os.path.getmtime(path),
                'versions': len(secret_versions(name)),
                'known': name in described,
                'group': EXTRA_LABEL if EXTRA and name.startswith(EXTRA_PREFIX) else '',
            }
        )
    return out


def value(name):
    return Path(_path(name)).read_text(encoding='utf-8', errors='replace')


def secret_versions(name):
    return versions(_versions_folder(name))


def save(name, text, create=False):
    """Write a secret, keeping the old value as a version. False when nothing changed."""
    path = _path(name)
    exists = os.path.isfile(path)
    if create and os.path.exists(path):
        raise ValueError(f'{name} already exists.')
    if not create and not exists:
        raise ValueError(f'{name} does not exist.')
    if name.endswith('.json'):
        json.loads(text)  # refuse broken JSON before it reaches a service
    if exists and value(name) == text:
        return False
    keep_version(path, _versions_folder(name), VERSIONS_KEPT)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    write_in_place(path, text)
    return True


def delete(name):
    keep_version(_path(name), _versions_folder(name), VERSIONS_KEPT)
    os.remove(_path(name))


def restore(name, version):
    text = read_version(_versions_folder(name), version)
    return save(name, text, create=not os.path.isfile(_path(name)))


def events(limit=60):
    return watch.events({'secret'}, limit)
