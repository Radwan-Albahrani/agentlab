"""review.json (what the lead chat hands over) -> the review GitHub gets. Findings are headed the same way every
time (title · blocking or not · the lane that found it), blocking ones first. A finding sits on its lines as an
inline comment (a range when it spans several, with a one-click suggestion when the fix is small) whenever those
lines are on the PR side of one diff hunk. GitHub refuses comments elsewhere, so the rest go in the review body
with a permalink to the exact lines at the reviewed commit, which GitHub renders as a highlighted snippet."""

import re

HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', re.M)
MAX_FINDINGS = 50


def hunks(patch):
    """[(first, last)] PR-side line ranges of a file's diff hunks."""
    return [(int(s), int(s) + int(n if n is not None else 1) - 1) for s, n in HUNK.findall(patch or '')]


def placeable(files, path, line, start=None):
    ranges = hunks(next((f['patch'] for f in files if f['path'] == path), ''))
    lo = start or line
    return any(a <= lo <= line <= b for a, b in ranges)


def header(f):
    mark = '`🔴 blocking`' if f['severity'] == 'blocking' else '`🟠 non-blocking`'
    return f'**{f["title"]}** | {mark} | `§ {f["lane"]}`'


def clean(raw):
    """The findings worth keeping from review.json, normalised; malformed ones are dropped."""
    out = []
    for f in (raw or [])[:MAX_FINDINGS]:
        if not isinstance(f, dict) or not str(f.get('title') or '').strip() or not str(f.get('body') or '').strip():
            continue
        line, start = _int(f.get('line')), _int(f.get('start_line'))
        out.append(
            {
                'title': str(f['title']).strip()[:150],
                'severity': 'blocking' if f.get('severity') == 'blocking' else 'non-blocking',
                'lane': re.sub(r'[^\w -]', '', str(f.get('lane') or 'correctness'))[:30] or 'correctness',
                'path': str(f.get('path') or '').strip().lstrip('/'),
                'line': line,
                'start_line': start if start and line and start < line else None,
                'body': str(f['body']).strip()[:4000],
                'suggestion': f.get('suggestion') if isinstance(f.get('suggestion'), str) else None,
            }
        )
    out.sort(key=lambda f: f['severity'] != 'blocking')
    return out


def _int(v):
    try:
        return int(v) if v not in (None, '') and int(v) > 0 else None
    except (TypeError, ValueError):
        return None


def permalink(repo, head, f):
    lines = f'#L{f["start_line"]}-L{f["line"]}' if f['start_line'] else f'#L{f["line"]}' if f['line'] else ''
    return f'https://github.com/{repo}/blob/{head}/{f["path"]}{lines}'


def build(findings, files, repo, head, extra=''):
    """(review body, inline comments) for a review of `head`."""
    inline, rest = [], []
    for f in findings:
        text = header(f) + '\n\n' + f['body']
        if f['path'] and f['line'] and placeable(files, f['path'], f['line'], f['start_line']):
            if f['suggestion'] is not None:
                text += '\n\n```suggestion\n' + f['suggestion'].rstrip('\n') + '\n```'
            c = {'path': f['path'], 'line': f['line'], 'side': 'RIGHT', 'body': text}
            if f['start_line']:
                c.update(start_line=f['start_line'], start_side='RIGHT')
            inline.append(c)
        else:
            rest.append(text + (f'\n\n{permalink(repo, head, f)}' if f['path'] else ''))
    body = '\n\n---\n\n'.join(rest)
    return '\n\n'.join(x for x in (body, extra) if x), inline


def _mention(name):
    """A screenshot named as a local file, not yet a GitHub link: ![alt](/tmp/name.png), `/tmp/name.png`, or an
    <img src="name.png" ...> tag (sized images)."""
    n = re.escape(name)
    return re.compile(
        r'!\[(?P<alt>[^\]]*)\]\((?:[^)\s:]*/)?' + n + r'\)'
        r'|`(?:[^`\s]*/)?' + n + '`'
        r'|(?P<tag><img\b[^>]*?\bsrc=")(?:[^"\s:]*/)?' + n + r'(?P<rest>"[^>]*>)'
    )


def mentions(text, name):
    return bool(_mention(name).search(text))


def qa_body(text, urls, missing=()):
    """The QA report for GitHub: each screenshot it names as a local file becomes its uploaded copy ({file name: url}),
    keeping an <img> tag's size; one that could not be uploaded says so instead of showing a broken image."""
    for name, url in urls.items():
        text = _mention(name).sub(lambda m, n=name, u=url: _linked(m, n, u), text)
    for name in missing:
        text = _mention(name).sub(f'_(screenshot not attached: {name})_', text)
    return text


def _linked(m, name, url):
    if m.group('tag'):
        return f'{m.group("tag")}{url}{m.group("rest")}'
    return f'![{m.group("alt") or _alt(name)}]({url})'


def _alt(name):
    return re.sub(r'[-_]+', ' ', name.rsplit('.', 1)[0])


def summary(findings, qa):
    """'2 findings (1 blocking) · QA: verified' style line for the dashboard and Slack."""
    n = len(findings)
    blocking = sum(f['severity'] == 'blocking' for f in findings)
    out = (
        'no findings'
        if not n
        else f'{n} finding{"s" if n != 1 else ""}' + (f' ({blocking} blocking)' if blocking else '')
    )
    verdict = (qa or {}).get('verdict')
    if verdict in QA_WORDS:
        out += ' · QA ' + QA_WORDS[verdict]
    return out


def counts_of(summary):
    """The counts behind a summary line written before reviews kept them ("3 findings (3 blocking) · QA found
    problems"), or None when it is not one."""
    m = re.match(r'(no findings|(\d+) findings?(?: \((\d+) blocking\))?)', summary or '')
    if not m:
        return None
    qa = next((v for v, words in QA_WORDS.items() if summary.endswith('QA ' + words)), '')
    return {'findings': int(m.group(2) or 0), 'blocking': int(m.group(3) or 0), 'open': 0, 'qa': qa}


QA_WORDS = {'pass': 'verified', 'fail': 'found problems', 'partial': 'partly verified', 'skipped': 'not needed'}
