"""Which T3 project a Slack task belongs in, guessed from the request, the channel and the thread."""

import json
import os
import re

from . import t3
from .config import DEFAULT_PROJECT

STOP_WORDS = """this that with from your have will what when where which their there about into fix fixed
fixing check update updates add adding remove make need please could would should still also just more
some than then them they were been being does done work working issue issues page bug bugs error
errors test tests daily audit review simplify simplification service services draft three thread"""
STOP = set(STOP_WORDS.split())


def _words(text):
    """Topic words: 4+ letters, no ids or numbers, plurals folded ('accounts' = 'account')."""
    out = set()
    for word in re.findall(r'(?<![\w-])[a-z]{4,}(?![\w-])', text.lower()):
        stem = word[:-1] if len(word) > 4 and word.endswith('s') and not word.endswith('ss') else word
        if stem not in STOP:
            out.add(stem)
    return out


def _profiles():
    """Per project: names/paths/repos that identify it, and words distinctive of its past chat titles."""
    with t3.db() as con:
        projs = {
            pid: (title, root)
            for pid, title, root in con.execute(
                'select project_id, title, workspace_root from projection_projects where deleted_at is null'
            )
            if title not in ('No project', 'workspace')
        }
        titles, repos = {}, {}
        for pid, title, pl in con.execute(
            """select project_id, title, payload_json from orchestration_v2_projection_threads
                   where deleted_at is null order by created_at desc limit 1500"""
        ):
            if pid not in projs:
                continue
            titles.setdefault(pid, []).append(title)
            for pr in json.loads(pl).get('pullRequests') or []:
                if pr.get('repository'):
                    repos.setdefault(pid, set()).add(pr['repository'].lower())
    counts = {pid: {} for pid in projs}
    total = sum(len(ts) for ts in titles.values()) or 1
    for pid, ts in titles.items():
        for t in ts:
            for w in _words(t):
                counts[pid][w] = counts[pid].get(w, 0) + 1
    # a repo belongs to the top-level folder that IS it, not to the subprojects inside it
    repo_owner = {}
    for pid, rs in repos.items():
        for r in rs:
            if r not in repo_owner or len(projs[pid][1]) < len(projs[repo_owner[r]][1]):
                repo_owner[r] = pid
    out = {}
    for pid, (title, root) in projs.items():
        base = os.path.basename(root).lower()
        rel = os.path.relpath(root, '/workspace').lower()
        names = {title.lower(), base, base.replace('-', ' '), rel}  # rel: platform/apps/api
        if '/' in rel:
            names.add(rel.split('/', 1)[1])  # apps/node-api
        names |= {r for r, owner in repo_owner.items() if owner == pid}  # example-org/app
        out[pid] = {'title': title, 'root': root, 'names': {n for n in names if len(n) >= 3}}
    # project names are identity, not topic; very common words say nothing either
    name_words = {w for p in out.values() for n in p['names'] for w in re.findall(r'[a-z]{4,}', n)}
    common = {
        w for w in {w for c in counts.values() for w in c} if sum(c.get(w, 0) for c in counts.values()) > 0.15 * total
    }
    for pid, p in out.items():
        # distinctive: used at least twice in this project's chats, more often than in all others together
        p['vocab'] = (
            {
                w
                for w, n in counts[pid].items()
                if n >= 2 and n > sum(c.get(w, 0) for q, c in counts.items() if q != pid)
            }
            - name_words
            - common
        )
    return out


def for_repo(repo):
    """The project that IS this GitHub repo (owner/name), known from the PRs its chats opened or from a folder of
    the same name; None when this environment has none."""
    try:
        profiles = _profiles().values()
    except Exception:
        return None
    repo, name = repo.lower(), repo.lower().rsplit('/', 1)[-1]
    by_repo = [p for p in profiles if repo in p['names']]
    by_name = [p for p in profiles if os.path.basename(p['root']).lower() == name]
    found = sorted(by_repo or by_name, key=lambda p: len(p['root']))
    return found[0]['root'] if found else None


def pick(ask, context='', channel=''):
    """A name in the owner's own message wins; then a project in the channel's name (#raqeeb_management ->
    raqeeb); then names, paths and repos in the thread; then words typical of a project's past chats.
    No clear signal: the platform repo. Returns (root, reason); never raises."""
    try:
        return _pick(ask, context, channel)
    except Exception as e:  # never block a task on the guess
        return DEFAULT_PROJECT, f'default ({type(e).__name__})'


def hit(name, text):
    """`name` appears in `text` as a whole word or path."""
    return re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', text) is not None


def _pick(ask, context, channel):
    ask_l, ctx_l = ask.lower(), context.lower()
    chan = ' ' + re.sub(r'[_\-.]+', ' ', channel.lower()) + ' '  # raqeeb_management -> raqeeb management
    scores = []
    for p in _profiles().values():
        named = [n for n in p['names'] if hit(n, ask_l)]
        in_channel = [n for n in p['names'] if '/' not in n and hit(n.replace('-', ' '), chan)]
        in_thread = [n for n in p['names'] if hit(n, ctx_l)]
        topical = sorted(p['vocab'] & _words(ask + ' ' + context + chan))
        # one topic word can be chance; two or more start to say something
        score = (
            100 * bool(named)
            + 30 * bool(in_channel)
            + 5 * len(in_thread)
            + (min(len(topical), 6) if len(topical) >= 2 else 0)
        )
        if score:
            why = (
                f'named "{named[0]}"'
                if named
                else f'channel #{channel}'
                if in_channel
                else f'thread mentions "{in_thread[0]}"'
                if in_thread
                else 'topic: ' + ', '.join(topical[:4])
            )
            scores.append((score, len(p['root']), p['root'], why))  # ties: the more specific folder
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 2:
        return DEFAULT_PROJECT, 'default'
    return scores[0][2], scores[0][3]
