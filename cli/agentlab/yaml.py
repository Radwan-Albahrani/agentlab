"""A tiny block-style YAML writer for the files agentctl renders (compose files, Traefik's dynamic config).
Strings that could be misread are written JSON-quoted, which YAML reads as the same double-quoted string."""

import json
import re

PLAIN = re.compile(r'^[A-Za-z_./][A-Za-z0-9_./@=-]*$')
AMBIGUOUS = {'y', 'n', 'yes', 'no', 'on', 'off', 'true', 'false', 'null', '~'}


def _scalar(v):
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int | float):
        return str(v)
    s = str(v)
    return s if PLAIN.match(s) and s.lower() not in AMBIGUOUS else json.dumps(s)


def _lines(v, indent):
    pad = '  ' * indent
    out = []
    if isinstance(v, dict):
        for k, item in v.items():
            key = _scalar(k)
            if isinstance(item, dict | list) and item:
                out.append(f'{pad}{key}:')
                out += _lines(item, indent + 1)
            else:
                out.append(f'{pad}{key}: {_empty(item) if isinstance(item, dict | list) else _scalar(item)}')
    else:
        for item in v:
            if isinstance(item, dict | list) and item:
                inner = _lines(item, indent + 1)
                out.append(f'{pad}- {inner[0].lstrip()}')
                out += inner[1:]
            else:
                out.append(f'{pad}- {_empty(item) if isinstance(item, dict | list) else _scalar(item)}')
    return out


def _empty(v):
    return '{}' if isinstance(v, dict) else '[]'


def dump(data, header=''):
    head = ''.join(f'# {line}\n' if line else '#\n' for line in header.splitlines())
    return head + '\n'.join(_lines(data, 0)) + '\n'
