import re

FULL = 1500  # characters of detail kept


def plain(text, limit=FULL):
    """Markdown -> readable notification text."""
    t = re.sub(r'```.*?```', '[code]', text or '', flags=re.S)
    t = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', t)  # links -> their text
    t = re.sub(r'^\s*[-*+]\s+', '• ', t, flags=re.M)
    t = re.sub(r'^\s*#+\s*', '', t, flags=re.M)
    t = re.sub(r'(\*\*|__|`)', '', t)  # bold / code marks (a single _ in names stays)
    t = re.sub(r'(?<!\w)[*_](\S[^*_\n]*?)[*_](?!\w)', r'\1', t)  # *italic* / _italic_
    t = re.sub(r'^\s*>\s?', '', t, flags=re.M)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n\s*\n+', '\n\n', t).strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(' ', 1)[0] + '…'


def short(text, limit=120):
    t = re.sub(r'\s+', ' ', text or '').strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(' ', 1)[0] + '…'


def first_sentence(text):
    t = re.sub(r'\s+', ' ', text or '').strip()
    m = re.match(r'(.+?[.!?])(\s|$)', t)
    return short(m.group(1) if m else t)


def last_question(text):
    qs = re.findall(r'[^.!?\n]*\?', text or '')
    return short(qs[-1].strip()) if qs else first_sentence(text)


def ends_with_question(text):
    return re.sub(r'[\s*_`)]+$', '', text or '').endswith('?')
