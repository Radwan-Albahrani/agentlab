"""The companion side of pull request review and QA (generic part in reviewer/): queue, run as tasks, publish."""

import json
import os
import re
import time

from reviewer import prompt as brief
from reviewer import pulls, report
from reviewer.github import App, GitHubError

from . import projects, prompts, slack, t3, tasks
from .config import COMP, FILES, NAME, OWNER, evidence_repo, log, mode, optional_secret, review_slots, slack_for_github
from .state import key, key_of, lock, new_task, review_of, save, state
from .text import clock, first_sentence, hour, no_emoji

APP_ID, APP_KEY = 'github-app-id.txt', 'github-app-key.pem'
IMAGES = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
PR_LINK = re.compile(r'github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)')
ASKED = re.compile(r'^\W*(review|qa|test|check)\b', re.I)
PR_REF = re.compile(r'github\.com/[\w.-]+/[\w.-]+/pull/(\d+)|#(\d+)\b')
LEADING_REF = re.compile(r'^\s*(?:<?https?://\S*github\.com/\S+/pull/\d+\S*|[\w./-]*#\d+\b)\s*[:,.-]?\s*')

status = {'ready': False, 'bot': '', 'accounts': [], 'at': 0.0, 'error': ''}
PEOPLE_EVERY = 3600
_app = {'with': None, 'app': None}


def app():
    """The GitHub App from Secrets (rebuilt when they change), or None."""
    ident, pem = optional_secret(APP_ID), optional_secret(APP_KEY)
    if not ident or not pem:
        status.update(ready=False, error='not set up')
        return None
    if _app['with'] != (ident, pem):
        _app.update({'with': (ident, pem), 'app': App(ident, pem)})
    return _app['app']


def refresh():
    """Re-read the open PRs."""
    a = app()
    if not a:
        state['pulls'] = []
        return
    try:
        found = pulls.open_pulls(a)
        status.update(
            ready=True, error='', bot=a.slug(), accounts=[i['account'] for i in a.installations()], at=time.time()
        )
        state['pulls'] = found
    except Exception as e:  # keep the last list
        log('pull requests unavailable:', e)
        status.update(error=str(e)[:200], at=time.time())
    _refresh_people(a)
    save()


def _refresh_people(a):
    """Hourly: who can work on the repos with open PRs, and the App's private repos (the hub's pickers).

    Failures keep the last list."""
    known = state.get('github_people') or {}
    if time.time() - known.get('at', 0) < PEOPLE_EVERY:
        return
    try:
        found = pulls.people(a, state.get('pulls') or [])
    except Exception as e:
        log('GitHub people unavailable:', e)
        found = known.get('list') or []
    state['github_people'] = {'at': time.time(), 'list': found}
    try:
        repos = sorted((r['name'] for r in a.repositories() if r['private']), key=str.casefold)
    except Exception as e:
        log('GitHub repositories unavailable:', e)
        repos = (state.get('github_repos') or {}).get('list') or []
    state['github_repos'] = {'at': time.time(), 'list': repos}


def latest(pr_id):
    """(key, task) of the newest review of this PR, or (None, None)."""
    found = [(k, t) for k, t in state['tasks'].items() if review_of(t).get('id') == pr_id]
    return max(found, key=lambda kt: kt[1].get('start', ''), default=(None, None))


def rows(card):
    """The hub's PR list, each with its latest review (card: publish.card)."""
    queued = {q['id'] for q in state.get('review_queue', [])}
    entries = _run()
    run = {e['id']: {'n': i + 1, 'of': len(entries), 'done': bool(e.get('verdict'))} for i, e in enumerate(entries)}
    newest = {}  # PR id -> (key, task) of its latest review
    for k, t in state['tasks'].items():
        pr = review_of(t).get('id')
        if pr and (pr not in newest or t.get('start', '') > newest[pr][1].get('start', '')):
            newest[pr] = (k, t)
    out = []
    for p in state.get('pulls') or []:
        k, t = newest.get(p['id'], (None, None))
        review = None
        if p['id'] in queued:
            review = {'status': 'queued', 'outcome': 'Waiting for a free slot', 'task': '', 'head': '', 'at': ''}
        elif t:
            c = card(k, t)
            r = t['review']
            review = {
                'status': c['status'],
                'outcome': r.get('summary') or c['outcome'],
                'task': k,
                'head': r.get('published') or r['head'],
                'at': t.get('start', ''),
                'url': r.get('url', ''),
                'counts': r.get('counts') or report.counts_of(r.get('summary', '')),
            }
            if c['status'] == 'paused':
                review['resumes_at'] = t['paused'].get('resumes_at')
            if r.get('detail') and c['status'] not in ('working', 'waiting', 'paused'):
                review['detail'] = r['detail']
        if review and p['id'] in run:
            review['run'] = run[p['id']]
        out.append(dict(p, review=review))
    return out


def request(repo, number, origin=None):
    """Queue a review of repo#number (origin: Slack {channel, thread_ts, trigger_ts}); returns a problem or ''."""
    a = app()
    if not a:
        return 'the GitHub App is not set up yet (Secrets: github-app-id.txt and github-app-key.pem)'
    try:
        if a.installation_for(repo) is None:
            return f"I can't see {repo}: the GitHub App is not installed on {repo.split('/')[0]}"
    except GitHubError as e:
        return f'GitHub did not answer ({e})'
    pr_id = f'{repo}#{number}'
    _, t = latest(pr_id)
    if (t and t.get('active')) or any(q['id'] == pr_id for q in state.get('review_queue', [])):
        return f'{pr_id} is already being reviewed'
    item = {'id': pr_id, 'repo': repo, 'number': int(number), 'origin': origin}
    state.setdefault('review_queue', []).append(item)
    _join(item)
    save()
    return ''


def from_slack(channel, thread_ts, trigger_ts, text):
    """Start a review if this Slack tag asks for one; False means treat it as an ordinary task."""
    msg = slack.ask(text).strip()
    rest = re.sub(r'<?https?://\S*github\.com/\S+/pull/\d+\S*', '', msg).strip()
    asked = bool(ASKED.search(rest))
    if not asked and re.search(r'[a-z]{3,}', rest, re.I):
        return False
    pr = _linked(msg)
    if not pr and asked and thread_ts != trigger_ts:
        root = slack.thread_messages(channel, thread_ts, trigger_ts)[:1]
        pr = _linked(slack.readable(root[0].get('text', ''))) if root else None
    if not pr and asked:
        n = re.search(r'#(\d+)\b', rest)
        hits = [(p['repo'], p['number']) for p in state.get('pulls') or [] if n and p['number'] == int(n.group(1))]
        pr = hits[0] if len(hits) == 1 else None
    if not pr:
        return False
    repo, number = pr
    with lock:
        problem = request(repo, number, {'channel': channel, 'thread_ts': thread_ts, 'trigger_ts': trigger_ts})
    if problem:
        slack.post(channel, thread_ts, problem, md=f':warning: Not reviewing: {problem}.')
    else:
        slack.react(channel, trigger_ts, 'eyes')
    return True


def _linked(text):
    """(repo, number) if the text links exactly one pull request, else None."""
    links = {(m.group(1), int(m.group(2))) for m in PR_LINK.finditer(text or '')}
    return next(iter(links)) if len(links) == 1 else None


def _here(channel, thread_ts):
    """PR id -> newest review task posting into this thread."""
    found = {}
    for t in state['tasks'].values():
        r = review_of(t)
        if (t.get('channel'), t.get('thread_ts')) != (channel, thread_ts) or not r:
            continue
        if r['id'] not in found or t.get('start', '') > found[r['id']].get('start', ''):
            found[r['id']] = t
    return found


def in_thread(channel, thread_ts):
    return bool(_here(channel, thread_ts))


def for_reply(channel, thread_ts, text, others=False):
    """The review task a reply in this thread is for, 'which' when several could be, or None (not a review's).

    Several reviews of a batch share its thread: a reply naming a PR (#5922) goes to that review, else to the one
    waiting for an answer, else to the one running. others: the thread has an ordinary task, which takes the rest."""
    here = _here(channel, thread_ts)
    if not here:
        return None
    numbers = {int(a or b) for a, b in PR_REF.findall(slack.ask(text))}
    if numbers:
        named = [t for t in here.values() if review_of(t)['number'] in numbers]
        return named[0] if len(named) == 1 else None
    waiting = [t for t in here.values() if t.get('question') and (t.get('active') or t.get('outcome') == 'asked you')]
    if len(waiting) == 1:
        return waiting[0]
    if others:
        return None
    running = [t for t in here.values() if t.get('active')]
    if len(running) == 1 and not waiting:
        return running[0]
    if waiting or running:
        return 'which'
    return next(iter(here.values())) if len(here) == 1 else None


def answer(task, text, files, ts):
    """Pass a reply on to its review, without the leading PR reference that picked it."""
    msg = LEADING_REF.sub('', slack.ask(text), count=1).strip()
    tasks.follow_up(task, msg or text, files, ts)


def which(channel, thread_ts):
    """Several reviews here could take that reply: say how to pick one."""
    busy = [t for t in _here(channel, thread_ts).values() if t.get('active') or t.get('question')]
    if not busy:
        return
    names = ', '.join(f'#{review_of(t)["number"]}' for t in busy)
    slack.post(
        channel,
        thread_ts,
        'Which review is that for?',
        md=f':point_up: Several reviews are going here ({names}). Start your reply with the PR, like '
        f'`#{review_of(busy[0])["number"]} …`, so it reaches the right one.',
    )


PRUNE_EVERY = 30 * 86400


def prune_tick():
    """Monthly pulls.prune_evidence of old QA screenshots."""
    a, evidence = app(), evidence_repo()
    if not a or not evidence:
        return
    if 'evidence_pruned' not in state:
        state['evidence_pruned'] = time.time()
        save()
    if time.time() - state['evidence_pruned'] < PRUNE_EVERY:
        return
    state['evidence_pruned'] = time.time()
    save()
    try:
        dropped = pulls.prune_evidence(a, evidence, time.time())
    except GitHubError as e:
        log('evidence prune failed:', e)
        COMP.event('failed', f'Could not prune {evidence}', detail=str(e)[:300], ok=False)
        return
    if dropped:
        COMP.event('cleanup', f'Pruned {dropped} old QA screenshots from {evidence}')


def tick():
    queue = state.get('review_queue') or []
    _tidy()
    _recover()
    running = sum(1 for t in state['tasks'].values() if review_of(t) and t.get('active'))
    while queue and running < review_slots():
        item = queue.pop(0)
        e = _entry(item['id']) or _join(item)  # queued by a version without a run
        save()
        try:
            start(item, e)
            running += 1
        except Exception as ex:
            log('review start failed:', item['id'], ex)
            _finish(e, 'failed', f"Couldn't start: {str(ex)[:200]}")
            COMP.event('failed', f'Could not review {item["id"]}', detail=str(ex)[:300], ok=False)
    _settle(queue)


def _recover():
    """Reviews that ended as failed on a usage limit, the newest of their PR and not asked for again: paused instead."""
    queued = {q['id'] for q in state.get('review_queue') or []}
    now = time.time()
    for t in list(state['tasks'].values()):
        r = review_of(t)
        if not r or t.get('active') or t.get('outcome') != 'failed' or t.get('limit_checked'):
            continue
        if r['id'] in queued or latest(r['id'])[1] is not t:
            t['limit_checked'] = True
        elif tasks.recover_limited(t, now):
            log('review paused for the usage limit after it failed', r['id'])
            _rejoin(t)
            save()


def _rejoin(t):
    """Put a recovered review back on a batch card: its own entry if the batch is still going, else a new batch."""
    k = key_of(t)
    if any(e.get('task') == k for e in _run()):
        return  # _settle reopens it
    r = review_of(t)
    b = _batch()
    if not b:
        thread = None if t['channel'].startswith('D') else t['thread_ts']  # a channel's batch stays in its thread
        b = state['review_batch'] = {'channel': t['channel'], 'thread': thread, 'card': None, 'prs': []}
    paused = t['paused'].get('resumes_at') or 0
    b['prs'].append({'id': r['id'], 'url': r['url'], 'title': r.get('title', ''), 'task': k, 'paused': paused})
    _show()


# A batch: every review asked for while others are queued or running; it ends when the queue is empty and all
# finished. It has one card message, edited as its reviews move; each finished review replies in the card's thread.
VERDICTS = {
    'approved': (':white_check_mark:', 'Approved'),
    'changes': (':octagonal_sign:', 'Changes requested'),
    'failed': (':x:', 'Failed'),
    'stopped': (':black_square_for_stop:', 'Stopped'),
    'asked': (':raised_hand:', 'Waiting for your answer'),
}


def _batch():
    """The current batch, or None. {channel, thread (None: the card is top level), card, prs: [entry]}."""
    b = state.get('review_batch')
    if b is None and state.get('review_run'):
        b = state['review_batch'] = _migrate(state.pop('review_run'))
    return b


def _migrate(old):
    """A run saved by the per-card version: it continues on a fresh batch card; tick retires the old cards."""
    first = old[0]
    b = {'channel': first['channel'], 'thread': None if first.get('hub') else first.get('thread'), 'card': None}
    b['moved'] = [(e['channel'], e['card'], e['id'], e['url']) for e in old if e.get('card') and not e.get('verdict')]
    b['prs'] = [{k: v for k, v in e.items() if k not in ('channel', 'thread', 'card', 'hub')} for e in old]
    return b


def _run():
    return (_batch() or {}).get('prs') or []


def _thread(b):
    """Where the batch's replies go: the card's own thread, or the thread the card sits in."""
    return b.get('thread') or b.get('card')


def _entry(pr_id):
    """The current batch's unfinished entry for this PR, or None."""
    return next((e for e in reversed(_run()) if e['id'] == pr_id and not e.get('verdict')), None)


def _join(item):
    """Add a requested review to the batch (a new batch goes in the asking thread, or the owner's DM for the hub)."""
    origin = item.get('origin')
    b = _batch()
    if not b:
        ch, thread = (origin['channel'], origin['thread_ts']) if origin else (slack.dm_owner(), None)
        b = state['review_batch'] = {'channel': ch, 'thread': thread, 'card': None, 'prs': []}
    e = {
        'id': item['id'],
        'url': f'https://github.com/{item["repo"]}/pull/{item["number"]}',
        'title': next((p['title'] for p in state.get('pulls') or [] if p['id'] == item['id']), ''),
    }
    if origin:
        e['asked'] = {'channel': origin['channel'], 'ts': origin['trigger_ts']}
    b['prs'].append(e)
    _show()
    if origin and (origin['channel'], origin['thread_ts']) != (b['channel'], b['thread']) and b.get('card'):
        link = slack.link(b['channel'], b['card'])
        where = f'<{link}|the review batch>' if link else 'the review batch'
        slack.note_only(origin['channel'], origin['thread_ts'], f':mag: Added {_short(e["id"])} to {where}')
    return e


def _short(pr_id):
    """'org/app#5922' -> 'app#5922'."""
    return pr_id.rsplit('/', 1)[-1]


def _clip(text, limit):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(' ', 1)[0] + '…'


# A PR's state on the batch card: (emoji, label), in the order the card lists them.
LOOK = {
    'waiting': (':raised_hand:', 'waiting for you'),
    'reviewing': (':arrows_counterclockwise:', 'reviewing'),
    'paused': (':double_vertical_bar:', 'paused'),
    'queued': (':hourglass_flowing_sand:', 'queued'),
    'changes': (':octagonal_sign:', 'changes requested'),
    'failed': (':x:', 'failed'),
    'stopped': (':black_square_for_stop:', 'stopped'),
    'approved': (':white_check_mark:', 'approved'),
}


def _state(e):
    if e.get('waiting') or e.get('verdict') == 'asked':
        return 'waiting'
    if e.get('verdict'):
        return e['verdict']
    if 'paused' in e:
        return 'paused'
    return 'reviewing' if e.get('task') else 'queued'


def _plural(n, word):
    return f'{n} {word}{"s" if n != 1 else ""}'


def _line(e):
    """One PR's short line on the card; the details are in its reply in the thread."""
    st = _state(e)
    icon, label = LOOK[st]
    c = e.get('counts') or {}
    if st == 'changes' and c.get('blocking'):
        label += f' · {c["blocking"]} blocking'
    elif st == 'approved' and c.get('findings'):
        label += f' · {_plural(c["findings"], "finding")}'
    pr = f'<{e.get("link") or e["url"]}|#{e["id"].rsplit("#", 1)[-1]}>'
    return f'{icon} {pr}' + (f' {_clip(e["title"], 40)}' if e.get('title') else '') + f' · {label}'


def _reset(prs):
    """When the paused reviews can go on: the latest reset time any of them gave, or None."""
    return max((e['paused'] for e in prs if e.get('paused')), default=None)


def _card(b):
    """(text, md, note) of the batch card."""
    prs = b['prs']
    finished = all(e.get('verdict') for e in prs)
    head = f'{"Reviewed" if finished else "Reviewing"} {_plural(len(prs), "pull request")}'
    n = {}
    for e in prs:
        n[_state(e)] = n.get(_state(e), 0) + 1
    reset = _reset(prs)
    parts = [
        ('done', n.get('approved', 0) + n.get('changes', 0)),
        ('waiting for you', n.get('waiting', 0)),
        (f'paused until {hour(reset)}' if reset else 'paused for the usage limit', n.get('paused', 0)),
        ('reviewing', n.get('reviewing', 0)),
        ('queued', n.get('queued', 0)),
        ('failed', n.get('failed', 0)),
        ('stopped', n.get('stopped', 0)),
    ]
    bits = [f'{count} {label}' for label, count in parts if count]
    md = f'{":checkered_flag:" if finished else ":mag:"} **{head}**' + ''.join(f' · {x}' for x in bits)
    md += '\n' + '\n'.join(_line(e) for e in sorted(prs, key=lambda e: list(LOOK).index(_state(e))))
    if finished:
        note = f'Finished {clock(time.time())}'
    elif n.get('paused'):
        note = 'Paused for the usage limit · T3 picks the reviews up again when it resets'
    else:
        note = f'Up to {review_slots()} run at a time · questions and results follow in the thread'
    return ' · '.join([head, *bits]), md, note


def _show():
    """Post the batch card, or edit it in place (edits don't notify)."""
    b = _batch()
    if not b or not b['prs']:
        return
    text, md, note = _card(b)
    if b.get('card'):
        slack.update(b['channel'], b['card'], text, md=md, note=note)
    else:
        b['card'] = slack.post(b['channel'], b.get('thread'), text, md=md, note=note)


def _tidy():
    """A migrated batch: post its card and point the old per-PR cards at it."""
    b = _batch()
    if not b:
        return
    if not b.get('card'):
        _show()
    link = slack.link(b['channel'], b['card']) if b.get('card') else ''
    for ch, ts, pr_id, url in b.pop('moved', []):
        where = f'<{link}|the review batch>' if link else 'the review batch'
        slack.update(
            ch, ts, f'{pr_id}: followed on the review batch', md=f'<{url}|{pr_id}>', note=f'Followed on {where}'
        )


def _done_md(e):
    icon, label = VERDICTS[e['verdict']]
    title = f': {e["title"]}' if e.get('title') else ''
    return f'{icon} **{label}** · <{e["link"]}|{e["id"]}>{title}' + (f'\n{e["detail"]}' if e.get('detail') else '')


def _finish(e, verdict, detail='', link='', thread=None):
    """Close a review's entry: edit the card, and reply in the batch thread unless the batch's done message will say
    it (a batch of one); thread: (channel, ts) of a review whose batch already ended."""
    e.update(verdict=verdict, detail=detail, link=link or e['url'], waiting=False)
    e.pop('paused', None)
    asked = e.pop('asked', None)
    if asked:
        slack.react(asked['channel'], asked['ts'], 'eyes', remove=True)
    b = _batch()
    if thread is None and b:
        _show()
        thread = (b['channel'], _thread(b)) if len(b['prs']) > 1 else None
    if thread and verdict != 'asked':  # a question is its own message
        n, of = sum(1 for x in _run() if x.get('verdict')), len(_run())
        slack.post(
            *thread,
            f'{e["id"]}: {VERDICTS[verdict][1].lower()}',
            md=_done_md(e),
            note=f'{n} of {of} reviews done' if e in _run() else None,
        )
    save()


def _ended(t):
    """(verdict, detail) of a review task that stopped without publishing."""
    outcome = (t or {}).get('outcome')
    if outcome == 'stopped':
        return 'stopped', ''
    if outcome == 'asked you':
        return 'asked', 'It asked you a question in the thread.'
    if outcome == 'failed':
        return 'failed', first_sentence(no_emoji(t.get('latest', '')), 200) or 'The agent run failed.'
    said = first_sentence(no_emoji((t or {}).get('latest', '')), 200)
    return 'failed', 'It ended without posting a review' + (f': {said}' if said else '.')


def _settle(queue):
    """Follow the batch's reviews to their end; once all are done, one message saying so."""
    b = _batch()
    if not b:
        return
    changed = False
    for e in b['prs']:
        t = state['tasks'].get(e.get('task') or '')
        if e.get('verdict') in ('asked', 'failed') and t and t.get('active'):  # answered, or paused after all
            for k in ('verdict', 'detail', 'link'):
                e.pop(k, None)
            changed = True
        if e.get('verdict') or not e.get('task'):
            continue
        if t and t.get('active'):
            if bool(t.get('question')) != bool(e.get('waiting')):
                e['waiting'] = bool(t.get('question'))
                changed = True
            paused = t.get('paused')
            if paused and e.get('paused') != (paused.get('resumes_at') or 0):
                e['paused'] = paused.get('resumes_at') or 0
                changed = True
            elif not paused and 'paused' in e:
                e.pop('paused')
                changed = True
            continue
        _finish(e, *_ended(t))
    if changed:
        _show()
    if any('paused' in e for e in b['prs']) and not b.get('limit_told'):
        b['limit_told'] = True
        reset = _reset(b['prs'])
        when = f'at {hour(reset)}' if reset else 'when the limit resets'
        slack.post(
            b['channel'],
            _thread(b),
            'Paused for the usage limit',
            md=f':double_vertical_bar: Paused for the usage limit; reviews resume {when}.',
        )
        save()
    if b['prs'] and not queue and all(e.get('verdict') for e in b['prs']):
        _wrap_up(b)
        state.pop('review_batch')
        save()


def _wrap_up(b):
    """The batch's one notifying end: top level in the DM for the hub, in the asking thread for Slack."""
    prs = b['prs']
    if len(prs) == 1:
        e = prs[0]
        slack.post(
            b['channel'], b.get('thread'), f'Review of {e["id"]}: {VERDICTS[e["verdict"]][1].lower()}', md=_done_md(e)
        )
        return
    lines = []
    for e in prs:
        icon, label = VERDICTS[e['verdict']]
        lines.append(f'{icon} <{e["link"]}|{e["id"]}> · {label.lower()}' + (f' · {e["detail"]}' if e['detail'] else ''))
    md = f':checkered_flag: **All {len(prs)} reviews done**\n' + '\n'.join(lines)
    slack.post(b['channel'], b.get('thread'), f'All {len(prs)} reviews done', md=md)


def start(item, e):
    a = app()
    if not a:
        raise GitHubError(0, 'the GitHub App is not set up')
    f = pulls.facts(a, item['repo'], item['number'])
    if f['state'] != 'open':
        raise GitHubError(0, f'the PR is {f["state"]}')
    if f['fork']:
        raise GitHubError(0, 'it comes from a fork; only branches of the repository itself are run here')
    b = _batch()
    if not b or not b.get('card'):
        raise RuntimeError("Slack refused the batch's message")
    _, before = latest(f'{f["repo"]}#{f["number"]}')
    rereview = review_of(before or {}).get('published', '')
    folder = f'review-{f["repo"].replace("/", "-")}-{f["number"]}-{int(time.time())}'
    box = os.path.join(FILES, 'outbox', folder)
    os.makedirs(box, exist_ok=True)
    _write(box, 'pr.md', brief.pr_md(f))
    _write(box, 'threads.json', json.dumps(f['threads'], indent=1, ensure_ascii=False))
    _write(box, '.files.json', json.dumps([{'path': x['path'], 'patch': x['patch']} for x in f['files']]))
    _write(box, '.token', a.token(f['installation']), private=True)
    project = projects.for_repo(f['repo'])
    agent_box = prompts.outbox(folder)
    message = brief.lead(
        f,
        owner=slack.name(OWNER),
        box=agent_box,
        workdir='' if project else f'{agent_box}/code',
        project=project or '',
        rereview=rereview,
    )
    pr_id, short = f'{f["repo"]}#{f["number"]}', _short(f'{f["repo"]}#{f["number"]}')
    title = f'Review {short}: {f["title"]}'[:90]
    ch, tts = b['channel'], _thread(b)
    k = f'{key(ch, tts)}:{folder}'  # several reviews share the batch thread
    tid, err = t3.start_thread(project or '/workspace', title, message)
    if not tid:
        raise GitHubError(0, f"T3 didn't start the chat: {err}")
    new_task(
        ch,
        tts,
        tid,
        title,
        folder,
        b['card'],
        None,
        project or '/workspace',
        key=k,
        review={
            'id': pr_id,
            'repo': f['repo'],
            'number': f['number'],
            'url': f['url'],
            'head': f['head'],
            'installation': f['installation'],
            'rereview': rereview,
            'author': f['author'],
            'title': f['title'],
        },
    )
    e.update(task=k, title=f['title'], url=f['url'], rereview=rereview)
    _show()
    log('review started', pr_id, tid)
    COMP.event('started', title, task=k, detail=f'{pr_id} at {f["head"][:7]}')


def _read_json(box, name):
    try:
        with open(os.path.join(box, name), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _write(box, name, text, private=False):
    path = os.path.join(box, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.chmod(path, 0o600 if private else 0o644)


def publish(task, box, data):
    """review.json -> GitHub as the App; failures are reported in the thread."""
    r, ch, tts = task['review'], task['channel'], task['thread_ts']
    a = app()
    if not a:
        slack.post(ch, tts, 'Not posted', md=':warning: The review is ready, but the GitHub App is not set up.')
        return
    head = r['head']  # the reviewed commit, not the PR's current head
    f = {'repo': r['repo'], 'number': r['number'], 'installation': r['installation'], 'url': r['url']}
    findings = report.clean(data.get('findings'))
    qa = data.get('qa') if isinstance(data.get('qa'), dict) else {}
    files = _read_json(box, '.files.json')
    mine = {th['id']: th for th in _read_json(box, 'threads.json') if th.get('mine') and not th.get('resolved')}
    problems, qa_text, qa_url = [], '', ''
    still_open = set(mine) - _settle_threads(a, f, head, data.get('threads'), mine, problems)
    if qa.get('verdict') in ('pass', 'fail', 'partial') and qa.get('report'):
        qa_text = _qa_report(box, qa['report'])
        if qa_text is None:
            problems.append('the QA report file is missing')
            qa_text = ''
        else:
            qa_url, qa_text = _post_qa(a, f, box, qa_text, problems)
    limitation = str(data.get('limitation') or '').strip()[:500]
    extra = report.closing(findings, limitation, qa.get('verdict'), qa_url)
    url = ''
    try:
        if findings or limitation:
            body, inline = report.build(findings, files, r['repo'], head, extra)
            url = pulls.post_review(a, f, head, body, inline)
        elif not still_open:
            pulls.thumbs_up(a, f)
    except GitHubError as e:
        problems.append(f'the review itself: {e}')
    summary = report.summary(findings, qa)
    link = url or qa_url or r['url']
    note = f':white_check_mark: Review posted on <{link}|{r["id"]}> · {summary}'
    if problems:
        note = f':warning: Review of <{r["url"]}|{r["id"]}> · {summary} · trouble with ' + '; '.join(problems)
    counts = {
        'findings': len(findings),
        'blocking': sum(x['severity'] == 'blocking' for x in findings),
        'open': len(still_open),
        'qa': qa.get('verdict', ''),
    }
    detail = _detail(r['repo'], head, findings, qa, qa_text, qa_url, url)
    r.update(published=head, summary=summary, url=link, counts=counts, detail=detail)
    task.update(closed=note, posted=True)
    verdict = 'changes' if counts['blocking'] or counts['open'] or counts['qa'] == 'fail' else 'approved'
    said = summary + (' · :warning: trouble with ' + '; '.join(problems) if problems else '')
    k = key_of(task)
    e = next((x for x in reversed(_run()) if x.get('task') == k), None)
    if e:
        e['counts'] = counts
        _finish(e, verdict, said, link)
    else:  # a re-run from the thread after its batch ended
        _finish({'id': r['id'], 'url': r['url'], 'title': r.get('title', '')}, verdict, said, link, (ch, tts))
    with_token = os.path.join(box, '.token')
    if os.path.exists(with_token):
        os.remove(with_token)
    COMP.event('sent', f'Review of {r["id"]}: {summary}', task=k, to=r['id'], ok=not problems)
    _tell_author(r, verdict, link)
    save()


def _tell_author(r, verdict, link):
    """DM the PR's author, if the hub links their GitHub login to a Slack person, once per reviewed commit."""
    author = r.get('author') or ''
    who = slack_for_github(author)
    told = state.setdefault('authors_told', {})
    mine = author.casefold() == (COMP.setting('github_user') or '').strip().casefold()
    if not who or who == OWNER or mine or mode() == 'owner' or told.get(r['id']) == r['head']:
        return
    told[r['id']] = r['head']
    save()
    url = f'https://github.com/{r["repo"]}/pull/{r["number"]}'  # r['url'] is the review's by now
    md = f':mag: {NAME} reviewed your pull request <{url}|{_short(r["id"])}>: {VERDICTS[verdict][1].lower()}'
    md += f' · {r["summary"]}' + (f' — <{link}|see the review>' if link != url else '')
    try:
        dm = slack.app.client.conversations_open(users=who)['channel']['id']
    except Exception as e:
        log('author DM failed:', who, e)
        return
    slack.post(dm, None, f'{NAME} reviewed your pull request {_short(r["id"])}', md=md)


MAX_SHOWN = 20  # findings in the hub's short review; GitHub has them all


def _detail(repo, head, findings, qa, qa_text, qa_url, review_url):
    """The short review the hub shows when a PR is opened."""
    return {
        'findings': [
            {
                **{n: x[n] for n in ('title', 'severity', 'lane', 'path', 'line', 'start_line')},
                'body': _trim(x['body'], 500),
                'link': report.permalink(repo, head, x) if x['path'] else '',
            }
            for x in findings[:MAX_SHOWN]
        ],
        'qa': {'verdict': qa.get('verdict', ''), 'text': _trim(qa_text, 800), 'url': qa_url},
        'review_url': review_url,
    }


def _trim(text, limit):
    """At most `limit` characters, cut after a sentence if one ends late enough, else between words."""
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 2]
    end = max(cut.rfind(c) for c in ('. ', '.\n', '! ', '? '))
    return cut[: end + 1] + ' …' if end > limit // 2 else cut.rsplit(None, 1)[0] + ' …'


def _settle_threads(a, f, head, verdicts, mine, problems):
    """Resolve or rewrite the companion's own earlier threads per the verdicts; returns the ids closed."""
    closed = set()
    for th in verdicts or []:
        if not isinstance(th, dict) or th.get('id') not in mine:
            continue
        note = str(th.get('note') or '').strip()[:1000]
        try:
            if th.get('action') in ('fixed', 'retract'):
                lead = f'Fixed in `{head[:7]}`: ' if th['action'] == 'fixed' else 'Retracting this: '
                pulls.close_thread(a, f, th['id'], lead + note)
                closed.add(th['id'])
            elif th.get('action') == 'update' and mine[th['id']].get('first_comment'):
                found = report.clean([th.get('finding') or {}])
                if found:
                    text = report.header(found[0]) + '\n\n' + found[0]['body']
                    pulls.update_comment(a, f, mine[th['id']]['first_comment'], text)
        except GitHubError as e:
            problems.append(f'an earlier thread: {e}')
    return closed


def _qa_report(box, name):
    """The QA report's text, or None when the file is missing."""
    path = os.path.realpath(os.path.join(box, os.path.basename(str(name))))
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _post_qa(a, f, box, text, problems):
    """Post the QA report comment with its screenshots uploaded to the evidence repository; returns (url, body)."""
    local = [
        n for n in sorted(os.listdir(box)) if os.path.splitext(n)[1].lower() in IMAGES and report.mentions(text, n)
    ]
    urls, evidence = {}, evidence_repo()
    if local and not evidence:
        problems.append(f'{len(local)} screenshots (no QA screenshots repository is set on the hub)')
    elif local:
        try:
            folder = f'{f["repo"]}/pr-{f["number"]}/run-{os.path.basename(box).rsplit("-", 1)[-1]}'
            urls = pulls.upload_images(a, evidence, f, [os.path.join(box, n) for n in local], folder)
        except GitHubError as e:
            problems.append(f'{len(local)} screenshots (could not store them in {evidence}: {e})')
    body = report.qa_body(text, urls, [n for n in local if n not in urls])
    try:
        return pulls.qa_comment(a, f, body), body
    except GitHubError as e:
        problems.append(f'the QA report: {e}')
        return '', body


def heartbeat():
    app()
    return dict(
        status,
        people=(state.get('github_people') or {}).get('list') or [],
        repos=(state.get('github_repos') or {}).get('list') or [],
    )
