"""The companion side of pull request review and QA (generic part in reviewer/): queue, run as tasks, publish."""

import json
import os
import re
import time
from collections.abc import Callable, Collection
from typing import Any, Literal, TypedDict

from reviewer import prompt as brief
from reviewer import pulls, report
from reviewer.github import App, GitHubError, User
from reviewer.pulls import Target, Thread
from reviewer.report import Finding
from tables import CardRow, Counts, Detail, PullReview, PullRow, RunPos

from . import machine, projects, prompts, slack, t3, tasks
from .config import COMP, FILES, NAME, OWNER, evidence_repo, log, mode, optional_secret, review_slots, slack_for_github
from .fsm import REVIEW, REVIEW_ENDS
from .shapes import (
    Asker,
    Json,
    Origin,
    Review,
    ReviewBatch,
    ReviewEntry,
    ReviewQueued,
    ReviewState,
    Task,
)
from .state import key, key_of, lock, new_task, review_of, save, state
from .text import first_sentence, no_emoji
from .when import say

APP_ID, APP_KEY = 'github-app-id.txt', 'github-app-key.pem'
IMAGES = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
PR_LINK = re.compile(r'github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)')
ASKED = re.compile(r'^\W*(review|qa|test|check)\b', re.I)
PR_REF = re.compile(r'github\.com/[\w.-]+/[\w.-]+/pull/(\d+)|#(\d+)\b')
LEADING_REF = re.compile(r'^\s*(?:<?https?://\S*github\.com/\S+/pull/\d+\S*|[\w./-]*#\d+\b)\s*[:,.-]?\s*')
# A PR link as readable() leaves it, with or without its scheme: "github.com/o/r/pull/1 (https://github.com/o/r/pull/1)".
LINK_TEXT = re.compile(r'\(?<?(?:https?://)?(?:www\.)?github\.com/[\w.-]+/[\w.-]+/pull/\d+[^\s)>]*>?\)?')


# The cached App and the secrets it was built with.
_Cached = TypedDict('_Cached', {'with': tuple[str, str] | None, 'app': App | None})


class GithubStatus(TypedDict):
    """The GitHub App as the hub shows it (heartbeat.json github): ready once it listed the PRs."""

    ready: bool
    bot: str
    accounts: list[str]
    at: float
    error: str


class GithubBeat(GithubStatus):
    people: list[User]
    repos: list[str]


status: GithubStatus = {'ready': False, 'bot': '', 'accounts': [], 'at': 0.0, 'error': ''}
PEOPLE_EVERY = 3600
_app: _Cached = {'with': None, 'app': None}


def app() -> App | None:
    """The GitHub App from Secrets (rebuilt when they change), or None."""
    ident, pem = optional_secret(APP_ID), optional_secret(APP_KEY)
    if not ident or not pem:
        status.update({'ready': False, 'error': 'not set up'})
        return None
    if _app['with'] != (ident, pem):
        _app.update({'with': (ident, pem), 'app': App(ident, pem)})
    return _app['app']


def refresh() -> None:
    """Re-read the open PRs."""
    a = app()
    if not a:
        state['pulls'] = []
        return
    try:
        found = pulls.open_pulls(a)
        accounts = [i['account'] for i in a.installations()]
        status.update({'ready': True, 'error': '', 'bot': a.slug(), 'accounts': accounts, 'at': time.time()})
        state['pulls'] = found
    except Exception as e:  # keep the last list
        log('pull requests unavailable:', e)
        status.update({'error': str(e)[:200], 'at': time.time()})
    _refresh_people(a)
    save()


def _refresh_people(a: App) -> None:
    """Hourly: who can work on the repos with open PRs, and the App's private repos (the hub's pickers).

    Failures keep the last list."""
    known = state.get('github_people')
    if known and time.time() - known['at'] < PEOPLE_EVERY:
        return
    try:
        found = pulls.people(a, state.get('pulls') or [])
    except Exception as e:
        log('GitHub people unavailable:', e)
        found = known['list'] if known else []
    state['github_people'] = {'at': time.time(), 'list': found}
    try:
        repos = sorted((r['name'] for r in a.repositories() if r['private']), key=str.casefold)
    except Exception as e:
        log('GitHub repositories unavailable:', e)
        repos = state['github_repos']['list'] if 'github_repos' in state else []
    state['github_repos'] = {'at': time.time(), 'list': repos}


def latest(pr_id: str) -> tuple[str, Task] | tuple[None, None]:
    """(key, task) of the newest review of this PR, or (None, None)."""
    found: list[tuple[str, Task]] = [(k, t) for k, t in state['tasks'].items() if review_of(t).get('id') == pr_id]
    return max(found, key=lambda kt: kt[1].get('start', ''), default=(None, None))


def rows(card: Callable[[str, Task], CardRow]) -> list[PullRow]:
    """The hub's PR list, each with its latest review (card: publish.card)."""
    queued = {q['id'] for q in state.get('review_queue', [])}
    entries = _run()
    run: dict[str, RunPos] = {
        e['id']: {'n': i + 1, 'of': len(entries), 'done': bool(verdict_of(e))} for i, e in enumerate(entries)
    }
    newest: dict[str, tuple[str, Task]] = {}  # PR id -> (key, task) of its latest review
    for tk, task in state['tasks'].items():
        pr = review_of(task).get('id')
        if pr and (pr not in newest or task.get('start', '') > newest[pr][1].get('start', '')):
            newest[pr] = (tk, task)
    out: list[PullRow] = []
    for p in state.get('pulls') or []:
        k, t = newest.get(p['id'], (None, None))
        review: PullReview | None = None
        if p['id'] in queued:
            review = {'status': 'queued', 'outcome': 'Waiting for a free slot', 'task': '', 'head': '', 'at': ''}
        elif t and k is not None:
            c = card(k, t)
            r = review_of(t)
            review = {
                'status': c['status'],
                'outcome': r.get('summary') or c['outcome'],
                'task': k,
                'head': r.get('published') or r['head'],
                'at': t.get('start', ''),
                'url': r.get('url', ''),
            }
            if 'counts' in r:
                review['counts'] = r['counts']
            if c['status'] == 'paused':
                pause = machine.paused(t)
                review['resumes_at'] = pause['resumes_at'] if pause else None
            if 'detail' in r and c['status'] not in ('working', 'waiting', 'paused'):
                review['detail'] = r['detail']
        if review is not None and p['id'] in run:
            review['run'] = run[p['id']]
        out.append({**p, 'review': review})
    return out


def request(repo: str, number: int, origin: Origin | None = None) -> str:
    """Queue a review of repo#number (origin: Slack {channel, thread_ts, trigger_ts}); returns a problem or ''."""
    a = app()
    if not a:
        return 'the GitHub App is not set up yet (Secrets: github-app-id.txt and github-app-key.pem)'
    try:
        if a.installation_for(repo) is None:
            return f"I can't see {repo}: the GitHub App is not installed on {repo.split('/', maxsplit=1)[0]}"
    except GitHubError as e:
        return f'GitHub did not answer ({e})'
    pr_id = f'{repo}#{number}'
    _, t = latest(pr_id)
    if (t and machine.running(t)) or any(q['id'] == pr_id for q in state.get('review_queue', [])):
        return f'{pr_id} is already being reviewed'
    item: ReviewQueued = {'id': pr_id, 'repo': repo, 'number': int(number), 'origin': origin}
    state.setdefault('review_queue', []).append(item)
    _join(item)
    save()
    return ''


def from_slack(
    channel: str,
    thread_ts: str,
    trigger_ts: str,
    text: str,
    by: str | None = None,
    any_words: bool = False,
    approved_by: str | None = None,
    via: str | None = None,
) -> bool:
    """Start a review of each PR this Slack message asks for; False means it asks for none (an ordinary task).

    by: a colleague asking (questions go to the owner, the result back to them); any_words: PR links are enough."""
    msg = slack.ask(text).strip()
    rest = LINK_TEXT.sub(' ', msg).strip()
    asked = bool(ASKED.search(rest)) or (any_words and bool(re.search(r'\breview', rest, re.I)))
    if not asked and not any_words and re.search(r'[a-z]{3,}', rest, re.I):
        return False
    prs = _links(msg)
    if not prs and asked and thread_ts != trigger_ts:
        root = slack.thread_messages(channel, thread_ts, trigger_ts)[:1]
        prs = _links(slack.readable(root[0].get('text', ''))) if root else []
    if not prs and asked:
        n = re.search(r'#(\d+)\b', rest)
        hits = [(p['repo'], p['number']) for p in state.get('pulls') or [] if n and p['number'] == int(n.group(1))]
        prs = hits if len(hits) == 1 else []
    if not prs:
        return False
    via = via or ('in a DM' if channel.startswith('D') else f'in #{slack.channel_name(channel)}')
    origin: Origin = {'channel': channel, 'thread_ts': thread_ts, 'trigger_ts': trigger_ts, 'via': via}
    if by:
        origin['by'] = by
    if approved_by:
        origin['approved_by'] = approved_by
    with lock:
        problems = [(f'{repo}#{n}', _ask_one(repo, n, origin, by)) for repo, n in prs]
    refused = [(pr, p) for pr, p in problems if p]
    if len(refused) == 1 and len(prs) == 1:
        slack.post(channel, thread_ts, refused[0][1], md=f':warning: Not reviewing: {refused[0][1]}.')
    elif refused:
        why: dict[str, list[str]] = {}
        for pr, p in refused:
            why.setdefault(p, []).append(_short(pr))
        lines = '\n'.join(f'- {", ".join(names)}: {p}' for p, names in why.items())
        slack.post(channel, thread_ts, f'Not reviewing {len(refused)} PRs', md=f':warning: Not reviewing:\n{lines}')
    if len(refused) < len(prs):
        slack.react(channel, trigger_ts, 'eyes')
    return True


def _ask_one(repo: str, number: int, origin: Origin, by: str | None) -> str:
    """Queue (or follow) one asked-for review; returns a problem or ''. Holds the lock."""
    going = _going(f'{repo}#{number}') if by else None
    if going and by:  # already queued or running: follow that review
        _follow(going, origin, by, new=False)
        _show()
        save()
        return ''
    return request(repo, number, origin)


def _going(pr_id: str) -> ReviewEntry | None:
    """The batch's entry for this PR while it is queued or running, or None."""
    return next((e for e in reversed(_run()) if e['id'] == pr_id and verdict_of(e) in (None, 'asked')), None)


def _askers(e: ReviewEntry) -> list[Asker]:
    """The colleagues following this review."""
    return e.get('for') or []


def _follow(e: ReviewEntry, origin: Origin, by: str, new: bool = True) -> None:
    """Keep a colleague posted on a review: an "On it" message whose status line follows it, then the result."""
    ch, thr = origin['channel'], origin['thread_ts']
    short, line = _short(e['id']), _progress(e)
    pr = f'<{e["url"]}|{short}>'
    if any(a['user'] == by for a in _askers(e)):
        slack.post(ch, thr, f'Reviewing {short}', md=f':mag: Still on it: {pr}. Updates are in your first thread.')
        return
    head = f':mag: On it: reviewing {pr}.' if new else f':mag: Already on it: {pr} was asked for before you.'
    md = head + " I'll keep this updated and reply here when it's done."
    ts = slack.post(ch, thr, f'Reviewing {short}', md=md, note=line)
    asker: Asker = {
        'channel': ch,
        'thread': thr,
        'user': by,
        'name': slack.name(by),
        'ts': origin['trigger_ts'],
        'msg': ts,
        'md': md,
        'shown': line,
    }
    e['for'] = [*_askers(e), asker]
    t = state['tasks'].get(e.get('task') or '')
    if t and by not in review_of(t).setdefault('asked_by', []):
        review_of(t)['asked_by'].append(by)


def _progress(e: ReviewEntry) -> str:
    """A colleague's live status line for a review."""
    st = _look(e)
    if st == 'queued':
        queue = [q['id'] for q in state.get('review_queue') or []]
        ahead = queue.index(e['id']) if e['id'] in queue else 0
        return ':hourglass_flowing_sand: Queued · ' + (f'{ahead} ahead' if ahead else 'next up')
    if st == 'reviewing':
        bits = ['Reviewing'] + ([f'started {say(e["began"], "near")}'] if e.get('began') else [])
        n = (state['tasks'].get(e.get('task') or '') or {}).get('workers_said') or 0
        if n:
            bits.append(f'{_plural(n, "reviewer")} on it')
        return ':arrows_counterclockwise: ' + ' · '.join(bits)
    if st == 'waiting':
        return f':raised_hand: Waiting for {slack.name(OWNER)} to answer a question from the review'
    if st == 'paused':
        when = f'resumes at {say(e["paused"], "near")}' if e.get('paused') else 'resumes when it resets'
        return f':double_vertical_bar: Paused for the usage limit · {when}'
    icon, label = VERDICTS[st]
    return f'{icon} {label}' + (f' · {say(e["ended"], "near")}' if e.get('ended') else '')


def _status(e: ReviewEntry, a: Asker) -> bool:
    """Edit a colleague's status line when it changed; True if it did."""
    line, msg = _progress(e), a['msg']
    if not msg or line == a['shown']:
        return False
    a['shown'] = line
    slack.update(a['channel'], msg, f'Reviewing {_short(e["id"])}', md=a['md'], note=line)
    return True


def _keep_posted() -> None:
    for e in _run():  # who asked, on the task too (reviews started before it was recorded there)
        t = state['tasks'].get(e.get('task') or '')
        if t:
            mine = review_of(t).setdefault('asked_by', [])
            mine += [a['user'] for a in _askers(e) if a['user'] not in mine]
    changed = [_status(e, a) for e in _run() for a in _askers(e)]  # every line, not just up to the first change
    if True in changed:
        save()


def _links(text: str | None) -> list[tuple[str, int]]:
    """Every pull request the text links, once each, in the order written."""
    return list(dict.fromkeys((m.group(1), int(m.group(2))) for m in PR_LINK.finditer(text or '')))


def _linked(text: str | None) -> tuple[str, int] | None:
    """(repo, number) if the text links exactly one pull request, else None."""
    links = {(m.group(1), int(m.group(2))) for m in PR_LINK.finditer(text or '')}
    return next(iter(links)) if len(links) == 1 else None


def _here(channel: str, thread_ts: str) -> dict[str, Task]:
    """PR id -> newest review task posting into this thread."""
    found: dict[str, Task] = {}
    for t in state['tasks'].values():
        r = review_of(t)
        if (t.get('channel'), t.get('thread_ts')) != (channel, thread_ts) or not r:
            continue
        if r['id'] not in found or t.get('start', '') > found[r['id']].get('start', ''):
            found[r['id']] = t
    return found


def in_thread(channel: str, thread_ts: str) -> bool:
    return bool(_here(channel, thread_ts))


def for_reply(channel: str, thread_ts: str, text: str, others: bool = False) -> Task | Literal['which'] | None:
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
    waiting = [t for t in here.values() if machine.asking(t) and (machine.running(t) or machine.outcome(t) == 'asked')]
    if len(waiting) == 1:
        return waiting[0]
    if others:
        return None
    running = [t for t in here.values() if machine.running(t)]
    if len(running) == 1 and not waiting:
        return running[0]
    if waiting or running:
        return 'which'
    return next(iter(here.values())) if len(here) == 1 else None


def answer(task: Task, text: str, files: list[Json] | None, ts: str) -> None:
    """Pass a reply on to its review, without the leading PR reference that picked it."""
    msg = LEADING_REF.sub('', slack.ask(text), count=1).strip()
    tasks.follow_up(task, msg or text, files, ts, 'thread')


def which(channel: str, thread_ts: str) -> None:
    """Several reviews here could take that reply: say how to pick one."""
    busy = [t for t in _here(channel, thread_ts).values() if machine.running(t) or machine.asking(t)]
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


def prune_tick() -> None:
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


def tick() -> None:
    queue = state.get('review_queue') or []
    _tidy()
    running = sum(1 for t in state['tasks'].values() if review_of(t) and machine.running(t))
    while queue and running < review_slots():
        if not t3.agent_up():  # restarting: the queue waits for it rather than failing
            break
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
    _keep_posted()


# A batch: every review asked for while others are queued or running; it ends when the queue is empty and all
# finished. It has one card message, edited as its reviews move; each finished review replies in the card's thread.
VERDICTS = {
    'approved': (':white_check_mark:', 'Approved'),
    'changes': (':octagonal_sign:', 'Changes requested'),
    'failed': (':x:', 'Failed'),
    'stopped': (':black_square_for_stop:', 'Stopped'),
    'asked': (':raised_hand:', 'Waiting for your answer'),
}


def _batch() -> ReviewBatch | None:
    """The current batch, or None. {channel, thread (None: the card is top level), card, prs: [entry]}."""
    return state.get('review_batch')


def _run() -> list[ReviewEntry]:
    return (_batch() or {}).get('prs') or []


def _thread(b: ReviewBatch) -> str | None:
    """Where the batch's replies go: the card's own thread, or the thread the card sits in."""
    return b.get('thread') or b.get('card')


def _entry(pr_id: str) -> ReviewEntry | None:
    """The current batch's unfinished entry for this PR, or None."""
    return next((e for e in reversed(_run()) if e['id'] == pr_id and not verdict_of(e)), None)


def _join(item: ReviewQueued) -> ReviewEntry:
    """Add a requested review to the batch (a new batch goes in the owner's asking thread, else the owner's DM)."""
    origin = item.get('origin')
    by = origin.get('by') if origin else None
    b = _batch()
    if not b:
        ch, thread = (origin['channel'], origin['thread_ts']) if origin and not by else (slack.dm_owner(), None)
        b = state['review_batch'] = {'channel': ch, 'thread': thread, 'card': None, 'prs': []}
    e: ReviewEntry = {
        'id': item['id'],
        'url': f'https://github.com/{item["repo"]}/pull/{item["number"]}',
        'title': next((p['title'] for p in state.get('pulls') or [] if p['id'] == item['id']), ''),
    }
    e['state'] = REVIEW.first('queued')
    if origin and not by:  # a colleague's 👀 goes with their follow
        e['asked'] = {'channel': origin['channel'], 'ts': origin['trigger_ts']}
    b['prs'].append(e)
    if origin and by:
        _follow(e, origin, by)
    _show()
    if origin and not by and (origin['channel'], origin['thread_ts']) != (b['channel'], b['thread']) and b.get('card'):
        link = slack.link(b['channel'], b['card'] or '')
        where = f'<{link}|the review batch>' if link else 'the review batch'
        slack.note_only(origin['channel'], origin['thread_ts'], f':mag: Added {_short(e["id"])} to {where}')
    return e


def _short(pr_id: str) -> str:
    """'org/app#5922' -> 'app#5922'."""
    return pr_id.rsplit('/', 1)[-1]


def _clip(text: str | None, limit: int) -> str:
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


def verdict_of(e: ReviewEntry) -> str | None:
    """How the review ended (fsm.REVIEW_ENDS), or None while it is queued or running."""
    s = REVIEW.of(e.get('state'))
    return s if s in REVIEW_ENDS else None


def _look(e: ReviewEntry) -> str:
    """The entry's state as the card shows it: a run that ended on a question waits for the owner too."""
    s = REVIEW.of(e.get('state'))
    return 'waiting' if s == 'asked' else s


def _plural(n: int, word: str) -> str:
    return f'{n} {word}{"s" if n != 1 else ""}'


def _line(e: ReviewEntry) -> str:
    """One PR's short line on the card; the details are in its reply in the thread."""
    st = _look(e)
    icon, label = LOOK[st]
    c: Counts = e.get('counts') or {'findings': 0, 'blocking': 0, 'open': 0, 'qa': ''}
    if st == 'changes' and c['blocking']:
        label += f' · {c["blocking"]} blocking'
    elif st == 'approved' and c['findings']:
        label += f' · {_plural(c["findings"], "finding")}'
    pr = f'<{e.get("link") or e["url"]}|#{e["id"].rsplit("#", 1)[-1]}>'
    names = ', '.join(a['name'] for a in _askers(e))
    asker = f' · for {names}' if names else ''
    return f'{icon} {pr}' + (f' {_clip(e["title"], 40)}' if e.get('title') else '') + f' · {label}{asker}'


def _reset(prs: list[ReviewEntry]) -> float | None:
    """When the paused reviews can go on: the latest reset time any of them gave, or None."""
    return max((e['paused'] for e in prs if e.get('paused')), default=None)


def _card(b: ReviewBatch) -> tuple[str, str, str]:
    """(text, md, note) of the batch card."""
    prs = b['prs']
    finished = all(verdict_of(e) for e in prs)
    head = f'{"Reviewed" if finished else "Reviewing"} {_plural(len(prs), "pull request")}'
    n: dict[str, int] = {}
    for e in prs:
        n[_look(e)] = n.get(_look(e), 0) + 1
    reset = _reset(prs)
    parts = [
        ('done', n.get('approved', 0) + n.get('changes', 0)),
        ('waiting for you', n.get('waiting', 0)),
        (f'paused until {say(reset, "near")}' if reset else 'paused for the usage limit', n.get('paused', 0)),
        ('reviewing', n.get('reviewing', 0)),
        ('queued', n.get('queued', 0)),
        ('failed', n.get('failed', 0)),
        ('stopped', n.get('stopped', 0)),
    ]
    bits = [f'{count} {label}' for label, count in parts if count]
    md = f'{":checkered_flag:" if finished else ":mag:"} **{head}**' + ''.join(f' · {x}' for x in bits)
    md += '\n' + '\n'.join(_line(e) for e in sorted(prs, key=lambda e: list(LOOK).index(_look(e))))
    if finished:
        note = f'Finished {say(form="day")}'
    elif n.get('paused'):
        note = 'Paused for the usage limit · T3 picks the reviews up again when it resets'
    else:
        note = f'Up to {review_slots()} run at a time · questions and results follow in the thread'
    return ' · '.join([head, *bits]), md, note


def _show() -> None:
    """Post the batch card, or edit it in place (edits don't notify)."""
    b = _batch()
    if not b or not b['prs']:
        return
    text, md, note = _card(b)
    card = b.get('card')
    if card:
        slack.update(b['channel'], card, text, md=md, note=note)
    else:
        b['card'] = slack.post(b['channel'], b.get('thread'), text, md=md, note=note)


def _tidy() -> None:
    """A batch whose card Slack refused: post it again."""
    b = _batch()
    if b and not b.get('card'):
        _show()


def _done_md(e: ReviewEntry) -> str:
    icon, label = VERDICTS[e['state']]
    title = f': {e["title"]}' if e.get('title') else ''
    return f'{icon} **{label}** · <{e["link"]}|{e["id"]}>{title}' + (f'\n{e["detail"]}' if e.get('detail') else '')


def _finish(
    e: ReviewEntry, verdict: ReviewState, detail: str = '', link: str = '', thread: tuple[str, str | None] | None = None
) -> None:
    """Close a review's entry: edit the card, and reply in the batch thread unless the batch's done message will say
    it (a batch of one); thread: (channel, ts) of a review whose batch already ended."""
    if 'state' not in e:  # a re-run from the thread after its batch ended: an entry of its own
        e['state'] = REVIEW.first('reviewing')
    e['state'] = REVIEW.to(e.get('state'), verdict)
    e.update({'detail': detail, 'link': link or e['url'], 'ended': time.time()})
    e.pop('paused', None)
    asked = e.pop('asked', None)
    if asked:
        slack.react(asked['channel'], asked['ts'], 'eyes', remove=True)
    for a in _askers(e):
        _status(e, a)
        if verdict != 'asked' and a.get('told') != verdict:  # a question to the owner isn't an end
            a['told'] = verdict
            slack.react(a['channel'], a.get('ts', ''), 'eyes', remove=True)
            _tell_asker(e, a)
    b = _batch()
    if thread is None and b:
        _show()
        thread = (b['channel'], _thread(b)) if len(b['prs']) > 1 else None
    if thread and verdict != 'asked':  # a question is its own message
        n, of = sum(1 for x in _run() if verdict_of(x)), len(_run())
        slack.post(
            *thread,
            f'{e["id"]}: {VERDICTS[verdict][1].lower()}',
            md=_done_md(e),
            note=f'{n} of {of} reviews done' if e in _run() else None,
        )
    save()


def _tell_asker(e: ReviewEntry, asker: Asker) -> None:
    """The colleague who asked hears how it ended, in their thread; what went wrong stays with the owner."""
    short, verdict = _short(e['id']), e['state']
    if verdict in ('approved', 'changes'):
        md, plain = _done_md(e), f'{VERDICTS[verdict][1]} · {e.get("detail") or ""}'.rstrip(' ·')
    else:
        md = (
            f'{VERDICTS[verdict][0]} The review of <{e["url"]}|{short}> {verdict}; {slack.name(OWNER)} has the details.'
        )
        plain = VERDICTS[verdict][1]
    ok = bool(
        slack.post(asker['channel'], asker['thread'], f'Review of {short}: {VERDICTS[verdict][1].lower()}', md=md)
    )
    COMP.event(
        'sent', f'Review result for {short}', to=asker['name'], detail=plain if ok else 'Slack refused it', ok=ok
    )


def _ended(t: Task | None) -> tuple[ReviewState, str]:
    """(verdict, detail) of a review task that stopped without publishing."""
    outcome = machine.outcome(t or {})
    if outcome == 'stopped':
        return 'stopped', ''
    if outcome == 'asked':
        return 'asked', 'It asked you a question in the thread.'
    if outcome == 'failed':
        return 'failed', first_sentence(no_emoji((t or {}).get('latest', '')), 200) or 'The agent run failed.'
    said = first_sentence(no_emoji((t or {}).get('latest', '')), 200)
    return 'failed', 'It ended without posting a review' + (f': {said}' if said else '.')


def _settle(queue: list[ReviewQueued]) -> None:
    """Follow the batch's reviews to their end; once all are done, one message saying so."""
    b = _batch()
    if not b:
        return
    changed = False
    for e in b['prs']:
        t = state['tasks'].get(e.get('task') or '')
        if REVIEW.is_(e.get('state'), 'asked', 'failed') and t and machine.running(t):  # answered, or resumed after all
            e['state'] = REVIEW.to(e.get('state'), 'reviewing')
            e.pop('detail', None)
            e.pop('link', None)
            changed = True
        if verdict_of(e) or not e.get('task'):
            continue
        if t and machine.running(t):
            paused = machine.paused(t)
            now: ReviewState = 'waiting' if machine.asking(t) else 'paused' if paused else 'reviewing'
            if not REVIEW.is_(e.get('state'), now):
                e['state'] = REVIEW.to(e.get('state'), now)
                changed = True
            if paused and e.get('paused') != (paused.get('resumes_at') or 0):
                e['paused'] = paused.get('resumes_at') or 0  # when it resumes, for the card
                changed = True
            elif not paused and 'paused' in e:
                e.pop('paused')
                changed = True
            continue
        _finish(e, *_ended(t))
    if changed:
        _show()
    if any(REVIEW.is_(e.get('state'), 'paused') for e in b['prs']) and not b.get('limit_told'):
        b['limit_told'] = True
        reset = _reset(b['prs'])
        when = f'at {say(reset, "near")}' if reset else 'when the limit resets'
        slack.post(
            b['channel'],
            _thread(b),
            'Paused for the usage limit',
            md=f':double_vertical_bar: Paused for the usage limit; reviews resume {when}.',
        )
        save()
    if b['prs'] and not queue and all(verdict_of(e) for e in b['prs']):
        _wrap_up(b)
        state.pop('review_batch')
        save()


def _wrap_up(b: ReviewBatch) -> None:
    """The batch's one notifying end: top level in the DM for the hub, in the asking thread for Slack."""
    prs = b['prs']
    if len(prs) == 1:
        e = prs[0]
        slack.post(
            b['channel'], b.get('thread'), f'Review of {e["id"]}: {VERDICTS[e["state"]][1].lower()}', md=_done_md(e)
        )
        return
    lines = []
    for e in prs:
        icon, label = VERDICTS[e['state']]
        lines.append(f'{icon} <{e["link"]}|{e["id"]}> · {label.lower()}' + (f' · {e["detail"]}' if e['detail'] else ''))
    md = f':checkered_flag: **All {len(prs)} reviews done**\n' + '\n'.join(lines)
    slack.post(b['channel'], b.get('thread'), f'All {len(prs)} reviews done', md=md)


def start(item: ReviewQueued, e: ReviewEntry) -> None:
    a = app()
    if not a:
        raise GitHubError(0, 'the GitHub App is not set up')
    f = pulls.facts(a, item['repo'], item['number'])
    if f['state'] != 'open':
        raise GitHubError(0, f'the PR is {f["state"]}')
    if f['fork']:
        raise GitHubError(0, 'it comes from a fork; only branches of the repository itself are run here')
    b = _batch()
    card = b.get('card') if b else None
    if not b or not card:
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
    where_to = projects.route('review', repo=f['repo'])
    in_project = where_to['by'] == 'repo'
    agent_box = prompts.outbox(folder)
    message = brief.lead(
        f,
        owner=slack.name(OWNER),
        box=agent_box,
        workdir='' if in_project else f'{agent_box}/code',
        project=where_to['project'] if in_project else '',
        rereview=rereview,
    )
    pr_id, short = f'{f["repo"]}#{f["number"]}', _short(f'{f["repo"]}#{f["number"]}')
    title = f'Review {short}: {f["title"]}'[:90]
    ch, tts = b['channel'], _thread(b) or card
    k = f'{key(ch, tts)}:{folder}'  # several reviews share the batch thread
    tid, err = t3.start_thread(where_to['project'], title, message)
    if not tid:
        raise GitHubError(0, f"T3 didn't start the chat: {err}")
    origin = item['origin']
    how = (
        tasks.audit(origin.get('by', OWNER), origin['via'], origin.get('approved_by'))
        if origin
        else tasks.audit(OWNER, 'from the hub')
    )
    t = new_task(
        ch,
        tts,
        tid,
        title,
        folder,
        card,
        None,
        where_to,
        key=k,
        audit=how,
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
            'asked_by': [a['user'] for a in _askers(e)],  # colleagues who asked for it (the hub's "started by")
        },
        party=machine.party_of(),
    )
    machine.begin_turn(t, 'system', 'thread')
    e.update({'task': k, 'title': f['title'], 'url': f['url'], 'rereview': rereview, 'began': time.time()})
    e['state'] = REVIEW.to(e.get('state'), 'reviewing')
    _show()
    log('review started', pr_id, tid)
    COMP.event('started', title, task=k, detail=f'{pr_id} at {f["head"][:7]}')


def _read_json(box: str, name: str) -> Any:
    try:
        with open(os.path.join(box, name), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _write(box: str, name: str, text: str, private: bool = False) -> None:
    path = os.path.join(box, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.chmod(path, 0o600 if private else 0o644)


def publish(task: Task, box: str, data: Json) -> None:
    """review.json -> GitHub as the App; failures are reported in the thread."""
    r, ch, tts = review_of(task), task['channel'], task['thread_ts']
    a = app()
    if not a:
        slack.post(ch, tts, 'Not posted', md=':warning: The review is ready, but the GitHub App is not set up.')
        return
    head = r['head']  # the reviewed commit, not the PR's current head
    f: Target = {'repo': r['repo'], 'number': r['number'], 'installation': r['installation'], 'url': r['url']}
    findings = report.clean(data.get('findings'))
    raw_qa = data.get('qa')
    qa: Json = raw_qa if isinstance(raw_qa, dict) else {}
    files = _read_json(box, '.files.json')
    mine: dict[str, Thread] = {
        th['id']: th for th in _read_json(box, 'threads.json') if th.get('mine') and not th.get('resolved')
    }
    problems: list[str] = []
    qa_text, qa_url = '', ''
    verdicts = data.get('threads')
    still_open = set(mine) - _settle_threads(a, f, head, verdicts if isinstance(verdicts, list) else [], mine, problems)
    if qa.get('verdict') in ('pass', 'fail', 'partial') and qa.get('report'):
        found = _qa_report(box, qa['report'])
        if found is None:
            problems.append('the QA report file is missing')
        else:
            qa_url, qa_text = _post_qa(a, f, box, found, problems)
    limitation = str(data.get('limitation') or '').strip()[:500]
    extra = report.closing(findings, limitation, qa.get('verdict'), qa_url)
    url = ''
    try:
        if findings or limitation:
            body, inline = report.build(findings, files, r['repo'], head, extra)
            url = pulls.post_review(a, f, head, body, inline)
        elif not still_open:
            pulls.thumbs_up(a, f)
    except GitHubError as err:
        problems.append(f'the review itself: {err}')
    summary = report.summary(findings, qa)
    link = url or qa_url or r['url']
    note = f':white_check_mark: Review posted on <{link}|{r["id"]}> · {summary}'
    if problems:
        note = f':warning: Review of <{r["url"]}|{r["id"]}> · {summary} · trouble with ' + '; '.join(problems)
    counts: Counts = {
        'findings': len(findings),
        'blocking': sum(x['severity'] == 'blocking' for x in findings),
        'open': len(still_open),
        'qa': qa.get('verdict', ''),
    }
    detail = _detail(r['repo'], head, findings, qa, qa_text, qa_url, url)
    r.update({'published': head, 'summary': summary, 'url': link, 'counts': counts, 'detail': detail})
    task['closed'] = note
    verdict: ReviewState = 'changes' if counts['blocking'] or counts['open'] or counts['qa'] == 'fail' else 'approved'
    said = summary + (' · :warning: trouble with ' + '; '.join(problems) if problems else '')
    k = key_of(task)
    e: ReviewEntry | None = next((x for x in reversed(_run()) if x.get('task') == k), None)
    askers = {a['user'] for a in _askers(e or {})}
    if e:
        e['counts'] = counts
        _finish(e, verdict, said, link)
    else:  # a re-run from the thread after its batch ended
        _finish({'id': r['id'], 'url': r['url'], 'title': r.get('title', '')}, verdict, said, link, (ch, tts))
    with_token = os.path.join(box, '.token')
    if os.path.exists(with_token):
        os.remove(with_token)
    COMP.event('sent', f'Review of {r["id"]}: {summary}', task=k, to=r['id'], ok=not problems)
    _tell_author(r, verdict, link, askers)
    save()


def _tell_author(r: Review, verdict: str, link: str, askers: Collection[str] = ()) -> None:
    """DM the PR's author, if the hub links their GitHub login to a Slack person, once per reviewed commit (not when
    they asked for the review: they hear in their thread)."""
    author = r.get('author') or ''
    who = slack_for_github(author)
    told = state.setdefault('authors_told', {})
    mine = author.casefold() == (COMP.setting('github_user') or '').strip().casefold()
    if not who or who == OWNER or who in askers or mine or mode() == 'owner' or told.get(r['id']) == r['head']:
        return
    told[r['id']] = r['head']
    save()
    url = f'https://github.com/{r["repo"]}/pull/{r["number"]}'  # r['url'] is the review's by now
    md = f':mag: {NAME} reviewed your pull request <{url}|{_short(r["id"])}>: {VERDICTS[verdict][1].lower()}'
    md += f' · {r["summary"]}' + (f' — <{link}|see the review>' if link != url else '')
    name, title = slack.name(who), f'Review result for {_short(r["id"])}'
    try:
        dm = slack.app.client.conversations_open(users=who)['channel']['id']
    except Exception as e:
        log('author DM failed:', who, e)
        COMP.event('sent', title, to=name, detail=f'Slack refused the DM: {e}', ok=False)
        return
    ok = bool(slack.post(dm, None, f'{NAME} reviewed your pull request {_short(r["id"])}', md=md))
    plain = f'{VERDICTS[verdict][1]} · {r["summary"]}'
    COMP.event('sent', title, to=name, detail=plain if ok else 'Slack did not take the message', ok=ok)


MAX_SHOWN = 20  # findings in the hub's short review; GitHub has them all


def _detail(
    repo: str,
    head: str,
    findings: list[Finding],
    qa: Json,
    qa_text: str,
    qa_url: str,
    review_url: str,
) -> Detail:
    """The short review the hub shows when a PR is opened."""
    return {
        'findings': [
            {
                'title': x['title'],
                'severity': x['severity'],
                'lane': x['lane'],
                'path': x['path'],
                'line': x['line'],
                'start_line': x['start_line'],
                'body': _trim(x['body'], 500),
                'link': report.permalink(repo, head, x) if x['path'] else '',
            }
            for x in findings[:MAX_SHOWN]
        ],
        'qa': {'verdict': qa.get('verdict', ''), 'text': _trim(qa_text, 800), 'url': qa_url},
        'review_url': review_url,
    }


def _trim(text: str | None, limit: int) -> str:
    """At most `limit` characters, cut after a sentence if one ends late enough, else between words."""
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 2]
    end = max(cut.rfind(c) for c in ('. ', '.\n', '! ', '? '))
    return cut[: end + 1] + ' …' if end > limit // 2 else cut.rsplit(None, 1)[0] + ' …'


def _settle_threads(
    a: App, f: Target, head: str, verdicts: list[Json], mine: dict[str, Thread], problems: list[str]
) -> set[str]:
    """Resolve or rewrite the companion's own earlier threads per the verdicts; returns the ids closed."""
    closed: set[str] = set()
    for th in verdicts:
        if not isinstance(th, dict) or th.get('id') not in mine:
            continue
        note = str(th.get('note') or '').strip()[:1000]
        try:
            if th.get('action') in ('fixed', 'retract'):
                lead = f'Fixed in `{head[:7]}`: ' if th['action'] == 'fixed' else 'Retracting this: '
                pulls.close_thread(a, f, th['id'], lead + note)
                closed.add(th['id'])
            elif th.get('action') == 'update' and (first := mine[th['id']].get('first_comment')):
                found = report.clean([th.get('finding') or {}])
                if found:
                    text = report.header(found[0]) + '\n\n' + found[0]['body']
                    pulls.update_comment(a, f, first, text)
        except GitHubError as e:
            problems.append(f'an earlier thread: {e}')
    return closed


def _qa_report(box: str, name: object) -> str | None:
    """The QA report's text, or None when the file is missing."""
    path = os.path.realpath(os.path.join(box, os.path.basename(str(name))))
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _post_qa(a: App, f: Target, box: str, text: str, problems: list[str]) -> tuple[str, str]:
    """Post the QA report comment with its screenshots uploaded to the evidence repository; returns (url, body)."""
    local = [
        n for n in sorted(os.listdir(box)) if os.path.splitext(n)[1].lower() in IMAGES and report.mentions(text, n)
    ]
    urls: dict[str, str] = {}
    evidence = evidence_repo()
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


def heartbeat() -> GithubBeat:
    app()
    return {
        **status,
        'people': state['github_people']['list'] if 'github_people' in state else [],
        'repos': state['github_repos']['list'] if 'github_repos' in state else [],
    }
