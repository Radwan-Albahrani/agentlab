"""Where a new T3 chat starts: one route() for every chat the companion starts, each answer explicit.

Every T3 project has a KIND:
  work   a codebase (the platform, its apps, other repos): the only places a chat is ever routed to
  home   a companion's own folder (/workspace/companions/<name>): its template merges, never Slack work, so the
         companion's own name in an ask ("@Leafy ...") is never a reason to go there
  none   T3's folderless chats ('No project', /workspace itself)

Every route says BY what it was chosen (strongest first):
  repo      a review: the project of the PR's repository
  named     the ask names the project ("node-api", "tree-map")
  channel   the channel is named after it (#node-api)
  thread    the thread mentions it
  topic     the ask and thread share words with the project's past chats
  default   nothing pointed anywhere: the default project (setting, a work project)
  checkout  a review of a repository with no project: the chat sits in the default project and works in a fresh
            checkout in its outbox
  earlier   a task started before routes were recorded

PURPOSES: what each kind of chat may be routed by. A Slack task or hub ask is read for its project; an errand or
a draft is the owner's paperwork and goes to the default project."""

import json
import os
import re

from . import t3
from .config import NAME, default_project

KINDS = ('work', 'home', 'none')
BY = ('repo', 'named', 'channel', 'thread', 'topic', 'default', 'checkout', 'earlier')
PURPOSES = {
    'task': ('named', 'channel', 'thread', 'topic', 'default'),
    'ask': ('named', 'channel', 'thread', 'topic', 'default'),
    'review': ('repo', 'checkout'),
    'errand': ('default',),
    'draft': ('default',),
}
HOMES = '/workspace/companions/'

STOP_WORDS = """this that with from your have will what when where which their there about into fix fixed
fixing check update updates add adding remove make need please could would should still also just more
some than then them they were been being does done work working issue issues page bug bugs error
errors test tests daily audit review simplify simplification service services draft three thread"""
STOP = set(STOP_WORDS.split())


def kind_of(title, root):
    root = (root or '').rstrip('/')
    if not root or root == '/workspace' or title in ('No project', 'workspace'):
        return 'none'
    return 'home' if (root + '/').startswith(HOMES) else 'work'


def made(project, by, why):
    """A route: where the chat starts and why; `by` is one of BY."""
    if by not in BY:
        raise ValueError(f'unknown route {by!r}')
    return {'project': project, 'by': by, 'why': why}


def route(purpose, ask='', context='', channel='', repo=''):
    """The route for a new chat (made()); never raises for a known purpose and never lands outside a work project."""
    if purpose not in PURPOSES:
        raise ValueError(f'unknown purpose {purpose!r}')
    try:
        profiles = _profiles()
    except Exception as e:
        profiles, failed = {}, type(e).__name__
    else:
        failed = ''
    home = _default(profiles)
    if purpose == 'review':
        root = _for_repo(profiles, repo)
        return made(root, 'repo', repo) if root else made(home, 'checkout', f'no project for {repo}')
    if 'named' in PURPOSES[purpose] and profiles:
        found = _scored(profiles, ask, context, channel)
        if found:
            return found
    return made(home, 'default', f'T3 unreadable ({failed})' if failed else 'nothing named a project')


def _default(profiles):
    """The default project setting, unless it is not a work project; then the shallowest work project."""
    want = default_project().rstrip('/')
    if kind_of('', want) == 'work':
        return want
    roots = sorted((p['root'] for p in profiles.values()), key=len)
    return roots[0] if roots else want


def _words(text):
    """Topic words: 4+ letters, plurals folded, stop words dropped."""
    out = set()
    for word in re.findall(r'(?<![\w-])[a-z]{4,}(?![\w-])', text.lower()):
        stem = word[:-1] if len(word) > 4 and word.endswith('s') and not word.endswith('ss') else word
        if stem not in STOP:
            out.add(stem)
    return out


def _profiles():
    """Per work project: identifying names/paths/repos and distinctive words from its chat titles."""
    with t3.db() as con:
        projs = {
            pid: (title, root)
            for pid, title, root in con.execute(
                'select project_id, title, workspace_root from projection_projects where deleted_at is null'
            )
            if kind_of(title, root) == 'work'
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
    repo_owner = {}  # repo -> its shallowest project
    for pid, rs in repos.items():
        for r in rs:
            if r not in repo_owner or len(projs[pid][1]) < len(projs[repo_owner[r]][1]):
                repo_owner[r] = pid
    me = NAME.lower()
    out = {}
    for pid, (title, root) in projs.items():
        base = os.path.basename(root).lower()
        rel = os.path.relpath(root, '/workspace').lower()
        names = {title.lower(), base, base.replace('-', ' '), rel}
        if '/' in rel:
            names.add(rel.split('/', 1)[1])
        names |= {r for r, owner in repo_owner.items() if owner == pid}
        out[pid] = {'title': title, 'root': root, 'names': {n for n in names if len(n) >= 3 and n != me}}
    name_words = {w for p in out.values() for n in p['names'] for w in re.findall(r'[a-z]{4,}', n)}
    common = {
        w for w in {w for c in counts.values() for w in c} if sum(c.get(w, 0) for c in counts.values()) > 0.15 * total
    }
    for pid, p in out.items():
        p['vocab'] = (
            {
                w
                for w, n in counts[pid].items()
                if n >= 2 and n > sum(c.get(w, 0) for q, c in counts.items() if q != pid)
            }
            - name_words
            - common
            - {me}
        )
    return out


def _for_repo(profiles, repo):
    """The work project for GitHub repo owner/name, or None."""
    if not repo:
        return None
    repo, name = repo.lower(), repo.lower().rsplit('/', 1)[-1]
    by_repo = [p for p in profiles.values() if repo in p['names']]
    by_name = [p for p in profiles.values() if os.path.basename(p['root']).lower() == name]
    found = sorted(by_repo or by_name, key=lambda p: len(p['root']))
    return found[0]['root'] if found else None


def hit(name, text):
    return re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', text) is not None


def _scored(profiles, ask, context, channel):
    """The best-evidenced work project as a route, or None when nothing points anywhere."""
    ask_l, ctx_l = ask.lower(), context.lower()
    chan = ' ' + re.sub(r'[_\-.]+', ' ', channel.lower()) + ' '
    scores = []
    for p in profiles.values():
        named = [n for n in p['names'] if hit(n, ask_l)]
        in_channel = [n for n in p['names'] if '/' not in n and hit(n.replace('-', ' '), chan)]
        in_thread = [n for n in p['names'] if hit(n, ctx_l)]
        topical = sorted(p['vocab'] & _words(ask + ' ' + context + chan))
        score = (
            100 * bool(named)
            + 30 * bool(in_channel)
            + 5 * len(in_thread)
            + (min(len(topical), 6) if len(topical) >= 2 else 0)
        )
        if score:
            if named:
                by, why = 'named', f'the ask names "{named[0]}"'
            elif in_channel:
                by, why = 'channel', f'#{channel}'
            elif in_thread:
                by, why = 'thread', f'the thread mentions "{in_thread[0]}"'
            else:
                by, why = 'topic', ', '.join(topical[:4])
            scores.append((score, len(p['root']), p['root'], by, why))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 2:
        return None
    return made(scores[0][2], scores[0][3], scores[0][4])
