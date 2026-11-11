"""Edits to cluster.toml as text, so the admin's comments and layout survive."""

import json
import re

HEADER = re.compile(r'^\s*\[(\[)?\s*([A-Za-z0-9_.-]+)\s*\]\]?\s*(#.*)?$')
KEY = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=')


def _headers(lines):
    """[(line index, name, is array)] of every table header."""
    out = []
    for i, line in enumerate(lines):
        m = HEADER.match(line)
        if m:
            out.append((i, m.group(2), bool(m.group(1))))
    return out


def _block_end(lines, start, heads, name=''):
    """End (exclusive) of the block at `start`, excluding the comments and blank lines just above the next header."""
    end = next((i for i, n, array in heads if i > start and (array or not n.startswith(name + '.'))), len(lines))
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith('#')):
        end -= 1
    return end


def _blocks(lines, name):
    heads = _headers(lines)
    return [(i, _block_end(lines, i, heads, name)) for i, n, array in heads if n == name and array]


def _value(lines, start, end, key):
    for line in lines[start + 1 : end]:
        m = KEY.match(line)
        if m and m.group(1) == key:
            return line.split('=', 1)[1].split('#', 1)[0].strip().strip('"\'')
    return None


def add_agent(text, agent_id, owner, extra=None):
    lines = text.splitlines()
    block = ['[[agents]]', f'id = {json.dumps(agent_id)}', f'owner = {json.dumps(owner)}']
    block += [f'{k} = {json.dumps(v)}' for k, v in (extra or {}).items()]
    existing = _blocks(lines, 'agents')
    if existing:
        at = existing[-1][1]
        lines[at:at] = ['', *block]
    else:
        lines += ['', *block]
    return '\n'.join(lines) + '\n'


def remove_agent(text, agent_id):
    """The text without that agent's [[agents]] block; ValueError when there is none."""
    lines = text.splitlines()
    for start, end in _blocks(lines, 'agents'):
        if _value(lines, start, end, 'id') == agent_id:
            first = start - 1 if start > 0 and not lines[start - 1].strip() else start
            del lines[first:end]
            return '\n'.join(lines) + '\n'
    raise ValueError(f'no [[agents]] block with id = "{agent_id}"')


def set_agent_key(text, agent_id, key, value):
    """Set `key = value` in that agent's [[agents]] block, or drop the key when value is None."""
    lines = text.splitlines()
    for start, end in _blocks(lines, 'agents'):
        if _value(lines, start, end, 'id') != agent_id:
            continue
        at = next((i for i in range(start + 1, end) if (m := KEY.match(lines[i])) and m.group(1) == key), None)
        if value is None:
            if at is not None:
                del lines[at]
        elif at is not None:
            lines[at] = f'{key} = {json.dumps(value)}{_comment(lines[at].split("=", 1)[1])}'
        else:
            lines.insert(end, f'{key} = {json.dumps(value)}')
        return '\n'.join(lines) + '\n'
    raise ValueError(f'no [[agents]] block with id = "{agent_id}"')


def _comment(rest):
    """The trailing `   # ...` of a value, with its spacing; a '#' inside a quoted string is not a comment."""
    value = rest.lstrip()
    tail = value
    if value[:1] in '"\'':
        m = re.match(r'"(?:[^"\\]|\\.)*"' if value[0] == '"' else r"'[^']*'", value)
        tail = value[m.end() :] if m else ''
    hash_at = tail.find('#')
    if hash_at < 0:
        return ''
    before = tail[:hash_at]
    return ' ' * max(len(before) - len(before.rstrip()), 1) + tail[hash_at:]


def set_key(text, section, key, value):
    """Set `key = value` in [section], adding the key or section when missing; keeps a trailing comment."""
    lines = text.splitlines()
    encoded = json.dumps(value)
    heads = _headers(lines)
    head = next((i for i, n, array in heads if n == section and not array), None)
    if head is None:
        lines += ['', f'[{section}]', f'{key} = {encoded}']
        return '\n'.join(lines) + '\n'
    end = next((i for i, _, _ in heads if i > head), len(lines))
    for i in range(head + 1, end):
        m = KEY.match(lines[i])
        if m and m.group(1) == key:
            lines[i] = f'{key} = {encoded}{_comment(lines[i].split("=", 1)[1])}'
            return '\n'.join(lines) + '\n'
    lines.insert(head + 1, f'{key} = {encoded}')
    return '\n'.join(lines) + '\n'
