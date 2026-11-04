"""agentlab's marked block in /etc/hosts; apply only removes it now, nothing outside it is touched."""

from .util import write_if_changed

PATH = '/etc/hosts'
BEGIN = '# BEGIN agentlab (private names: cloudflared resolves them to the edge)'
END = '# END agentlab'


def block(names):
    return '' if not names else '\n'.join([BEGIN, *(f'127.0.0.1 {n}' for n in names), END]) + '\n'


def merged(text, names):
    """`text` with agentlab's block replaced by one for `names` (or removed when there are none)."""
    lines = text.splitlines(keepends=True)
    if BEGIN in text and END in text:
        start = next(i for i, line in enumerate(lines) if line.startswith(BEGIN))
        end = next(i for i, line in enumerate(lines) if i > start and line.startswith(END))
        lines = lines[:start] + lines[end + 1 :]
    kept = ''.join(lines)
    if kept and not kept.endswith('\n'):
        kept += '\n'
    return kept + block(names)


def ensure(names, plan, path=PATH):
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ''
    new = merged(text, names)
    if new == text:
        return
    if plan.dry:
        plan.do(f'point {", ".join(names) or "no names"} at the edge in {path}')
        return
    write_if_changed(path, new, mode=0o644)
    plan.do(f'{path}: {", ".join(names) or "no names"} -> 127.0.0.1 (the edge)')
