"""Pull request review and QA (the generic part is in reviewer/), run in the companion's agent and posted as the companion's GitHub App.

Asked for from the hub (the Review button on a pull request) or in Slack ("@companion review <PR link>").
Each review is a task like any other: a thread (the owner's DM for page asks, else where they asked) mirroring one
lead T3 chat, which runs the lanes and QA as T3 child threads and writes review.json into its outbox. The companion then
posts the result: a comment-only review, the QA report with screenshots, a +1 when clean, and closes its own
earlier threads that were fixed. Two reviews run at a time (QA starts dev servers and containers); more queue.
The App's key lives in Secrets; until it is there the page shows how to add it and nothing here runs."""

import json
import os
import re
import time

from reviewer import prompt as brief
from reviewer import pulls, report
from reviewer.github import App, GitHubError

from . import projects, prompts, slack, t3, tasks
from .config import COMP, FILES, OWNER, evidence_repo, log, optional_secret
from .state import key, lock, new_task, save, state
from .text import first_sentence, without_mention

APP_ID, APP_KEY = 'github-app-id.txt', 'github-app-key.pem'
MAX_RUNNING = 2
IMAGES = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
PR_LINK = re.compile(r'github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)')
ASKED = re.compile(r'^\W*(review|qa|test|check)\b', re.I)

status = {'ready': False, 'bot': '', 'accounts': [], 'at': 0.0, 'error': ''}
_app = {'with': None, 'app': None}


def app():
    """The GitHub App from Secrets, rebuilt when its id or key changes; None until both are there."""
    ident, pem = optional_secret(APP_ID), optional_secret(APP_KEY)
    if not ident or not pem:
        status.update(ready=False, error='not set up')
        return None
    if _app['with'] != (ident, pem):
        _app.update({'with': (ident, pem), 'app': App(ident, pem)})
    return _app['app']


# ---------------------------------------------------------------- the open pull requests
def refresh():
    """Re-read the open PRs (asked by the page when it opens or on its refresh button; never on a timer)."""
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
    except Exception as e:  # keep the last list; the page shows why it is old
        log('pull requests unavailable:', e)
        status.update(error=str(e)[:200], at=time.time())
    save()


def latest(pr_id):
    """The newest review task for this PR, as (key, task), or (None, None)."""
    found = [(k, t) for k, t in state['tasks'].items() if (t.get('review') or {}).get('id') == pr_id]
    return max(found, key=lambda kt: kt[1].get('start', ''), default=(None, None))


def rows(card):
    """The PR list for the page, each with its latest review (card: publish.card, for the same status words)."""
    queued = {q['id'] for q in state.get('review_queue', [])}
    out = []
    for p in state.get('pulls') or []:
        k, t = latest(p['id'])
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
                # findings, blocking, open (earlier ones still standing), qa verdict
                'counts': r.get('counts') or report.counts_of(r.get('summary', '')),
            }
        out.append(dict(p, review=review))
    return out


# ---------------------------------------------------------------- asking for one
def request(repo, number, origin=None):
    """Queue a review of repo#number. origin: {channel, thread_ts, trigger_ts} when asked in Slack. Returns a
    problem, or '' when queued."""
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
    state.setdefault('review_queue', []).append({'id': pr_id, 'repo': repo, 'number': int(number), 'origin': origin})
    save()
    return ''


def from_slack(channel, thread_ts, trigger_ts, text):
    """A tag that asks for a review -> a review in that thread. True if taken (else it is an ordinary task).
    Asking: a PR link on its own ("@companion <link>"), or review/QA words with a link, a "#123" from the list, or
    under a message that links one PR ("@companion review this" in its thread)."""
    msg = slack.readable(without_mention(text)).strip()
    rest = re.sub(r'<?https?://\S*github\.com/\S+/pull/\d+\S*', '', msg).strip()
    asked = bool(ASKED.search(rest))
    if not asked and re.search(r'[a-z]{3,}', rest, re.I):
        return False  # other words: an ordinary task, even with a link in it
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
    """(repo, number) of the one pull request a text links, or None (none, or several)."""
    links = {(m.group(1), int(m.group(2))) for m in PR_LINK.finditer(text or '')}
    return next(iter(links)) if len(links) == 1 else None


PRUNE_EVERY = 30 * 86400


def prune_tick():
    """Once a month: drop QA screenshots older than 60 days from the evidence repository (see pulls.prune_evidence)."""
    a, evidence = app(), evidence_repo()
    if not a or not evidence:
        return
    if 'evidence_pruned' not in state:  # nothing can be old yet: the first prune is a month from now
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
    running = sum(1 for t in state['tasks'].values() if t.get('review') and t.get('active'))
    while queue and running < MAX_RUNNING:
        item = queue.pop(0)
        save()
        try:
            start(item)
            running += 1
        except Exception as e:
            log('review start failed:', item['id'], e)
            _tell(item.get('origin'), f":warning: Couldn't start the review of {item['id']}: {str(e)[:200]}")
            COMP.event('failed', f'Could not review {item["id"]}', detail=str(e)[:300], ok=False)


def _tell(origin, md):
    if origin:
        slack.post(origin['channel'], origin['thread_ts'], first_sentence(md, 150), md=md)
    else:
        slack.post(slack.dm_owner(), None, first_sentence(md, 150), md=md)


def start(item):
    a = app()
    if not a:
        raise GitHubError(0, 'the GitHub App is not set up')
    f = pulls.facts(a, item['repo'], item['number'])
    if f['state'] != 'open':
        raise GitHubError(0, f'the PR is {f["state"]}')
    if f['fork']:
        raise GitHubError(0, 'it comes from a fork; only branches of the repository itself are run here')
    _, before = latest(f'{f["repo"]}#{f["number"]}')
    rereview = ((before or {}).get('review') or {}).get('published', '')
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
    pr_id, short = f'{f["repo"]}#{f["number"]}', f'{f["repo"].rsplit("/", 1)[-1]}#{f["number"]}'
    title = f'Review {short}: {f["title"]}'[:90]
    origin = item.get('origin')
    if origin:
        ch, tts, trigger = origin['channel'], origin['thread_ts'], origin['trigger_ts']
    else:
        ch = slack.dm_owner()
        tts = trigger = slack.post(
            ch,
            None,
            f'Reviewing {short}: {f["title"]}',
            md=f':mag: **Review and QA** · <{f["url"]}|{pr_id}>: {f["title"]}'
            + (f'\nAgain, after {rereview[:7]}' if rereview else ''),
            note='Asked from the hub. Reply here to steer it.',
        )
    tid, err = t3.start_thread(project or '/workspace', title, message)
    if not tid:
        raise GitHubError(0, f"T3 didn't start the chat: {err}")
    new_task(
        ch,
        tts,
        tid,
        title,
        folder,
        trigger,
        slack.note_only(ch, tts, tasks.THINKING),
        project or '/workspace',
        review={
            'id': pr_id,
            'repo': f['repo'],
            'number': f['number'],
            'url': f['url'],
            'head': f['head'],
            'installation': f['installation'],
            'rereview': rereview,
        },
    )
    log('review started', pr_id, tid)
    COMP.event('started', title, task=key(ch, tts), detail=f'{pr_id} at {f["head"][:7]}')


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


# ---------------------------------------------------------------- the result
def publish(task, box, data):
    """review.json from the lead chat -> GitHub, as the App. Every step that fails says so in the thread."""
    r, ch, tts = task['review'], task['channel'], task['thread_ts']
    a = app()
    if not a:
        slack.post(ch, tts, 'Not posted', md=':warning: The review is ready, but the GitHub App is not set up.')
        return
    head = r['head']  # the commit the chat was given; comments anchor to it even if the PR moved on since
    f = {'repo': r['repo'], 'number': r['number'], 'installation': r['installation'], 'url': r['url']}
    findings = report.clean(data.get('findings'))
    qa = data.get('qa') if isinstance(data.get('qa'), dict) else {}
    files = _read_json(box, '.files.json')
    mine = {th['id']: th for th in _read_json(box, 'threads.json') if th.get('mine') and not th.get('resolved')}
    problems, qa_url = [], ''
    still_open = set(mine) - _settle_threads(a, f, head, data.get('threads'), mine, problems)
    if qa.get('verdict') in ('pass', 'fail', 'partial') and qa.get('report'):
        qa_url = _post_qa(a, f, box, qa, problems)
    limitation = str(data.get('limitation') or '').strip()[:500]
    extra = '\n\n'.join(
        x
        for x in (f'_Not fully covered: {limitation}_' if limitation else '', f'QA report: {qa_url}' if qa_url else '')
        if x
    )
    url = ''
    try:
        if findings or limitation:  # only what is new: earlier findings live on in their own threads
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
    slack.note_only(ch, tts, note)
    counts = {
        'findings': len(findings),
        'blocking': sum(x['severity'] == 'blocking' for x in findings),
        'open': len(still_open),
        'qa': qa.get('verdict', ''),
    }
    r.update(published=head, summary=summary, url=link, counts=counts)
    task.update(closed=note, posted=True)
    with_token = os.path.join(box, '.token')
    if os.path.exists(with_token):
        os.remove(with_token)
    COMP.event('sent', f'Review of {r["id"]}: {summary}', task=key(ch, tts), to=r['id'], ok=not problems)
    save()


def _settle_threads(a, f, head, verdicts, mine, problems):
    """A re-review edits instead of piling up: The companion's own earlier threads are resolved with a one-line reply when
    fixed or wrong, and rewritten in place when the problem is still there but changed. Returns the ids closed."""
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


def _post_qa(a, f, box, qa, problems):
    """The QA report as its own comment, its screenshots shown inline: the ones in the review's folder that the report
    names go to the QA screenshots repository (see pulls.upload_images). If that fails, the report still goes
    up, each screenshot marked "not attached", and the thread says why."""
    report_path = os.path.realpath(os.path.join(box, os.path.basename(str(qa['report']))))
    if not os.path.isfile(report_path):
        problems.append('the QA report file is missing')
        return ''
    with open(report_path, encoding='utf-8') as fh:
        text = fh.read()
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
    try:
        return pulls.qa_comment(a, f, report.qa_body(text, urls, [n for n in local if n not in urls]))
    except GitHubError as e:
        problems.append(f'the QA report: {e}')
        return ''


def heartbeat():
    """What the page needs to know about the App (for the heartbeat)."""
    app()
    return dict(status)
