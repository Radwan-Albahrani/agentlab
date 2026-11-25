"""Each screen's JSON; hidden or out-of-scope things are left out here, never sent to the browser."""

import os
import time
from typing import Any

import cluster
import display
import domains
import needs
import notify
import scope
import store
from shapes import epoch
from store.companions import Companion

Json = dict[str, Any]

BARK_PUBLIC = os.environ.get('BARK_PUBLIC', '')  # Bark server address for the phone app
DAY = 86400


def see(key: str) -> bool:
    return display.visible(key) and scope.current().sees(key)


def shown_profiles() -> list[str]:
    return [p for p in cluster.ids() if see(f'profile.{p}')]


def shown_companions(profile: str | None = None) -> list[Companion]:
    return [
        c
        for c in store.companions.all_companions()
        if see(f'companion.{c["name"]}') and (profile is None or c['profile'] == profile)
    ]


def nav() -> Json:
    items = store.watch.containers().get('items') or []
    agents = []
    for p in shown_profiles():
        up = any(domains.healthy(r) for r in items if r.get('stack') == f'{domains.AGENT_STACK}{p}')
        comps = [
            {
                'name': c['name'],
                'display': c['display'],
                'live': c['state'] == 'live',
                'waiting': sum(1 for t in c['tasks'] if t['status'] == 'waiting'),
            }
            for c in shown_companions(p)
        ]
        agents.append({'name': p, 'up': up, 'companions': comps})
    disk, _ = my_disk()
    system = []
    for key, path, label in (
        ('manage', '/manage', 'Manage agents'),
        ('services', '/services', 'Services'),
        ('config', '/config', 'Configs'),
        ('storage', '/storage', 'Storage'),
        ('secrets', '/secrets', 'Secrets'),
        ('notifications', '/notifications', 'Notifications'),
    ):
        if not see(f'page.{key}'):
            continue
        entry: Json = {'key': key, 'path': path, 'label': label}
        if key == 'services':
            entry['count'] = sum(1 for r in items if not domains.healthy(r))
        if key == 'manage':
            entry['count'] = sum(1 for j in store.jobs.recent(5) if j.get('state') in ('queued', 'running'))
        if key == 'storage' and disk:
            entry['note'] = f'{100 * disk["used"] / disk["size"]:.0f}%'
        system.append(entry)
    return {
        'attention': needs.count(shown_companions()),
        'agents': agents,
        'colors': {p: a['color'] for p, a in cluster.agents().items() if p in shown_profiles() and a.get('color')},
        'allAgents': see('page.agents'),
        'system': system,
        'display': not display.load()['presenting'],
    }


def overview() -> Json:
    sums = cluster.summaries(shown_profiles())
    comps = shown_companions()
    out: Json = {}
    if see('overview.tiles'):
        tiles: Json = {
            'agents': {'online': sum(1 for s in sums.values() if s), 'total': len(sums), 'link': see('page.agents')}
        }
        if comps:
            tiles['companions'] = {
                'live': sum(1 for c in comps if c['state'] == 'live'),
                'total': len(comps),
                'waiting': sum(1 for c in comps for t in c['tasks'] if t['status'] == 'waiting'),
                'link': store.companions.url(comps[0]['name']),
            }
        disk, label = my_disk()
        if label:
            tiles['disk'], tiles['diskLabel'] = disk, label
        if see('agent.resources'):
            tiles['memory'] = {
                'usedMB': sum((s.get('resources') or {}).get('usedMB') or 0 for s in sums.values() if s),
                'poolMB': cluster.pool_mb(),
            }
        out['tiles'] = tiles
    if see('overview.needs'):
        out['needs'] = needs.needs(sums, comps)
    if see('overview.activity'):
        activity: list[Json] = [
            {**e, 'source': c['name']} for c in comps for e in c['events'][:40] if e.get('kind') != 'live'
        ]
        if see('page.services'):
            activity += [dict(e, source='server') for e in store.watch.events(None, 40) if e.get('kind') != 'scan']
        out['activity'] = sorted(activity, key=lambda e: e.get('at', 0), reverse=True)[:14]
    if see('companion.pulls'):
        out['reviews'] = [r for r in (review_summary(c) for c in comps) if r]
    if see('overview.stacks') and see('page.services'):
        groups = domains.by_stack()
        out['stacks'] = {
            'at': store.watch.containers().get('at'),
            'rows': [domains.stack(sid, groups[sid]) for _, sids in domains.by_domain(list(groups)) for sid in sids],
        }
    return out


def chat_link(p: str) -> str:
    """Chat opens the T3 app (your newest chat) for your own agent; the web page otherwise or before any chat."""
    return (scope.current().owns(p) and notify.newest_chat_link(p)) or cluster.links(p)['chat']


def now() -> Json:
    """How busy each of the viewer's own agents is, as counts read from its T3 database (cheap: the page polls it every
    few seconds). Never what the chats are about, and never someone else's agent, admins included."""
    if not see('overview.now'):
        return {'agents': []}
    mine = [p for p in shown_profiles() if scope.current().owns(p)]
    return {
        'agents': [{'name': p, 'chat': chat_link(p), **notify.live(p)} for p in mine],
        'at': time.time(),
    }


BUSY = ('queued', 'working', 'waiting', 'paused')  # paused: a usage limit T3 resumes from on its own


def outcome(p: Json) -> str:
    """Where a PR stands (the web app's lib/pulls.ts outcomeOf, kept the same)."""
    r = p.get('review')
    if not r:
        return 'draft' if p.get('draft') else 'unreviewed'
    if r.get('status') in BUSY:
        return 'reviewing'
    if r.get('status') != 'done':
        return 'failed'
    c = r.get('counts') or {}
    if c.get('blocking'):
        return 'blocking'
    return 'findings' if c.get('findings') or c.get('open') else 'clean'


def review_summary(c: Companion) -> Json | None:
    """A companion's PR reviews at a glance: outcome counts and the batch under way; None when it reviews none."""
    pulls = c.get('pulls') or []
    if not pulls:
        return None
    counts: dict[str, int] = {}
    for p in pulls:
        counts[outcome(p)] = counts.get(outcome(p), 0) + 1
    run = sorted(
        ((p['review']['run'], p) for p in pulls if (p.get('review') or {}).get('run')), key=lambda x: x[0]['n']
    )
    now = next((p for r, p in run if not r['done'] and p['review'].get('status') in ('working', 'waiting')), None)
    return {
        'name': c['name'],
        'display': c['display'],
        'profile': c['profile'],
        'open': len(pulls),
        'counts': counts,
        'batch': {
            'of': len(run),
            'done': sum(1 for r, _ in run if r['done']),
            'now': {'number': now['number'], 'title': now['title']} if now else None,
        }
        if len(run) > 1
        else None,
    }


def agent_card(n: str, s: Json | None) -> Json:
    if s is None:
        return {'name': n, 'online': False}
    links = cluster.links(n)
    r = s.get('resources') or {}
    card = {
        'name': n,
        'online': True,
        'onboarded': s.get('onboarded', True),
        'accounts': [{'key': k, 'label': label, **s['accounts'][k]} for k, label in cluster.ACCOUNTS.items()],
        'connectors': [{'key': k, **c} for k, c in s['connectors'].items()],
        'links': {
            'chat': chat_link(n),
            'terminal': links['terminal'],
            'files': links['files'],
            'browser': links['browser'] if s.get('browserUp') else None,
        },
        'companions': [
            {'name': c['name'], 'display': c['display'], 'live': c['state'] == 'live'} for c in shown_companions(n)
        ],
    }
    if see('agent.resources') and r.get('usedMB') is not None:
        card['resources'] = {
            'usedMB': r['usedMB'],
            'limitMB': r.get('limitMB'),
            'running': r.get('running') or [],
            'waiting': r.get('waiting') or [],
            'paused': r.get('paused') or 0,
        }
    return card


def agents(host: str) -> Json:
    sums = cluster.summaries(shown_profiles())
    out: Json = {'agents': [agent_card(n, s) for n, s in sums.items()]}
    if see('agent.resources'):
        out['memory'] = {
            'usedMB': sum((s.get('resources') or {}).get('usedMB') or 0 for s in sums.values() if s),
            'poolMB': cluster.pool_mb(),
        }
    return out


def agent(host: str, prof: str) -> Json:
    s = cluster.summary(prof)
    groups = domains.by_stack()
    sids = sorted(
        (sid for sid in groups if domains.domain_of(sid)[0] == prof), key=lambda x: domains.domain_of(x)[1] != 'agent'
    )
    out: Json = {
        'agent': agent_card(prof, s),
        'up': bool(sids) and all(domains.healthy(r) for sid in sids for r in groups[sid]),
        'companions': [
            {
                'name': c['name'],
                'display': c['display'],
                'state': c['state'],
                'tasks': len(c['tasks']),
                'working': sum(1 for t in c['tasks'] if t['status'] == 'working'),
                'waiting': sum(1 for t in c['tasks'] if t['status'] == 'waiting'),
            }
            for c in shown_companions(prof)
        ],
    }
    if see('agent.containers'):
        out['containers'] = [domains.stack(sid, groups[sid]) for sid in sids]
    out['disk'] = store.watch.people().get(cluster.owner(prof)) if cluster.storage_mode() == 'per-person' else None
    out['owner'] = (cluster.agents().get(prof) or {}).get('owner', '')
    out['mine'] = prof in scope.current().agents
    return out


def accounts(host: str, prof: str, page: Json) -> Json:
    """The agent's own Accounts page minus hidden items, plus its browser link."""
    if not see('agent.env'):
        page.pop('env', None)
    page['browserUrl'] = cluster.links(prof)['browser'] if page.get('browserUp') else None
    return page


CASE_ITEM = ('seq', 'kind', 'state', 'at', 'to', 'label', 'text', 'files', 'private', 'note', 'action', 'details',
             'side', 'question', 'where', 'attachments', 'history')  # fmt: skip


def _case_item(it: Json) -> Json:
    """A ledger item as the Cases tab shows it (contract: companion/bot/ledger.py); Slack ids stay behind."""
    out = {k: it[k] for k in CASE_ITEM if it.get(k) not in (None, '', [])}
    out['history'] = [[h[0], h[1]] for h in it.get('history') or []]
    return out


def companion(name: str) -> Json:
    c = store.companions.companion(name)
    settings = store.companions.settings(name)
    tasks: list[Json] = [
        {
            **t,
            'startedAt': epoch(t.get('started')),
            'endedAt': epoch(t.get('ended')) or None,
            'resumesAt': float(t['resumes_at']) if t.get('resumes_at') else None,
            't3': notify.thread_link(c['profile'], t['thread']) if t.get('thread') else '',
        }
        for t in c['tasks']
    ]
    poll_of = {p['task']: p['id'] for p in c['polls']}
    for t in tasks:
        # who it is with and where it stands (companion/bot/machine.py), and its ledger: every message in and out
        t['party'], t['phase'], t['caseLink'] = (
            t.pop('party', None) or 'owner',
            t.pop('phase', None) or '',
            t.pop('case_link', None) or '',
        )
        t['items'] = [_case_item(it) for it in t.get('items') or []]
        # where its T3 chat started and why (companion/bot/projects.py)
        project, by, why = (t.pop(k, None) or '' for k in ('project', 'route_by', 'route_why'))
        t['route'] = {'project': project, 'by': by, 'why': why} if project else None
        t.pop('started', None), t.pop('ended', None), t.pop('resumes_at', None)
        # the audit (from a companion new enough to record it): who started it, how, who approved it
        t['startedBy'], t['via'], t['approvedBy'] = (t.pop(k, None) or '' for k in ('started_by', 'via', 'approved_by'))
        t['poll'] = poll_of.get(t['id'])
    hb = c['heartbeat']
    mode = next(
        ({o['value']: o['label'] for o in f.get('options', [])}.get(v, v) for f, v in settings if f['key'] == 'mode'),
        hb.get('mode', ''),
    )
    out: Json = {
        'name': name,
        'display': c['display'],
        'problem': c['problem'],
        'profile': c['profile'],
        'state': c['state'],
        'since': hb.get('since'),
        'seen': hb.get('at'),
        'mode': mode,
        'templateUpdate': c['template_update'],
        'tasks': tasks,
        'events': c['events'][:200],
        'sentThisWeek': [
            e for e in c['events'] if e.get('kind') in ('sent', 'files') and time.time() - e['at'] < 7 * DAY
        ],
    }
    if see('companion.delivered'):
        out['delivered'] = [e for e in c['events'] if e.get('kind') in ('sent', 'files')][:100]
    if see('companion.polls'):
        out['polls'] = c['polls']
    if see('companion.pulls') and hb.get('github'):
        by_id = {t['id']: t for t in tasks}
        for p in c['pulls']:
            reviewed = by_id.get((p.get('review') or {}).get('task'))
            if reviewed:
                p['review'].update(t3=reviewed['t3'], slack=reviewed['slack'])
        me = next((v for f, v in settings if f['key'] == 'github_user'), '') or ''
        out['pulls'] = {'github': hb['github'], 'me': me, 'items': c['pulls']}
    channels = store.companions.channels(name)
    if see('companion.ask') and channels is not None:
        out['channels'] = channels
    if see('companion.settings'):
        people = [{'value': p['id'], 'label': p['name'], 'avatar': p.get('avatar', '')} for p in hb.get('people') or []]
        out['settings'] = [
            dict(f, value=v, **({'options': people} if f['type'] in ('people', 'links') else {})) for f, v in settings
        ]
    return out


def companion_secrets(name: str) -> Json:
    """The companion's own secrets: what each is, never the values."""
    prefix = f'companions/{name}/'
    items = [s for s in store.secrets.all_secrets() if s['name'].startswith(prefix)]
    present = {s['name'] for s in items}
    missing = [
        {'name': n, 'label': info.get('label', ''), 'about': info.get('about', ''), 'how': info.get('how', '')}
        for n, info in store.secrets.secrets_map().items()
        if n.startswith(prefix) and n not in present
    ]
    shown = ('name', 'label', 'about', 'how', 'modified')
    return {
        'items': [{k: s[k] for k in shown} | {'file': s['name'][len(prefix) :], 'set': True} for s in items]
        + [m | {'file': m['name'][len(prefix) :], 'set': False, 'modified': None} for m in missing],
    }


def companion_logs(name: str) -> Json:
    text, at = store.companions.log_tail(name)
    return {'text': text, 'at': at}


def services() -> Json:
    groups = domains.by_stack()
    out: Json = {'domains': [], 'other': []}
    for prof, sids in domains.by_domain(list(groups)):
        stacks = [domains.stack(sid, groups[sid]) for sid in sids]
        if prof:
            out['domains'].append({'profile': prof, 'stacks': stacks})
        else:
            out['other'] = stacks
    return out


def configs() -> Json:
    stacks = {s['id']: s for s in store.stacks.stacks()}
    out: Json = {'domains': [], 'other': []}
    for prof, sids in domains.by_domain(list(stacks)):
        rows = []
        for sid in sids:
            role = domains.domain_of(sid)[1]
            rows.append(
                {
                    'id': sid,
                    'label': domains.stack_label(sid),
                    'profile': prof,
                    'role': role,
                    'modified': stacks[sid]['modified'],
                    'companion': role if role not in (None, 'agent') and role in cluster.companions() else None,
                }
            )
        if prof:
            out['domains'].append({'profile': prof, 'stacks': rows})
        else:
            out['other'] = rows
    return out


def config(sid: str) -> Json:
    if sid not in {s['id'] for s in store.stacks.stacks()}:
        raise LookupError(sid)
    prof, role = domains.domain_of(sid)
    if prof and not see(f'profile.{prof}'):
        raise LookupError(sid)
    return {
        'id': sid,
        'label': domains.stack_label(sid),
        'role': role,
        'text': store.stacks.read(sid),
        'path': f'{cluster.data_dir()}/rendered/compose/{sid}/docker-compose.yml',
        'deploys': [e for e in store.watch.events({'deploy'}, 50) if e.get('title', '').startswith(sid + ' ')][:6],
    }


def people_disks() -> list[Json]:
    """[{email, agents, size?, ...}]: each person in scope with their disk and the agents on it."""
    disks, shown = store.watch.people(), set(shown_profiles())
    return [
        {'email': email, 'agents': [a for a in ids if a in shown], **(disks.get(email) or {})}
        for email, ids in cluster.owners().items()
        if see(f'person.{email}') and any(a in shown for a in ids)
    ]


def my_disk() -> tuple[Json | None, str]:
    """(disk, label) for the overview: the shared pool, or the person's own disk."""
    if cluster.storage_mode() == 'per-person':
        if scope.current().admin:
            return None, ''
        return store.watch.people().get(scope.current().email), 'Your disk'
    return (store.watch.usage().get('pool'), 'Server disk') if see('storage.manage') else (None, '')


def storage() -> Json:
    u = store.watch.usage()
    mode = cluster.storage_mode()
    out: Json = {
        'reported': bool(u),
        'mode': mode,
        'manage': see('storage.manage'),
        'pool': u.get('pool') if mode == 'shared' and see('storage.manage') else None,
        'people': people_disks() if mode == 'per-person' else [],
        'events': store.watch.events({'cleanup', 'alert', 'scan', 'restart'}, 30) if see('storage.manage') else [],
    }
    scan = u.get('scan') or {}
    if scan:
        items, profs = scan.get('items') or [], []
        for prof in shown_profiles():
            mine = [i for i in items if i.get('agent', i.get('profile')) == prof]
            total = next((i['bytes'] for i in mine if i['path'] == ''), 0)
            if total:
                profs.append(
                    {
                        'name': prof,
                        'total': total,
                        'top': sorted(
                            (
                                {'path': i['path'], 'bytes': i['bytes']}
                                for i in mine
                                if i['path'] and '/' not in i['path']
                            ),
                            key=lambda i: -i['bytes'],
                        ),
                        'biggest': biggest(mine),
                    }
                )
        out['scan'] = {'at': scan.get('at'), 'took': scan.get('took', 0), 'profiles': profs}
        if out['pool'] and see('storage.manage'):
            out['scan']['reconcile'] = reconcile(out['pool'], scan)
    return out


FOLDER_HINTS = {
    'home/.local/share/docker': "Docker inside the agent: images, containers and volumes (cleanup prunes what's unused)",
    'home/.local/share': 'Tool data, including Docker inside the agent',
    'home/.cache': 'Tool and package caches; they rebuild themselves',
    'home/.bun': "Bun's package store, shared by every node_modules",
    'home/.t3': 'T3: chats, attachments and its runtime',
    'home/.codex': 'Codex sessions and history',
    'home/.npm': 'npm cache',
    'home/.claude': 'Claude Code sessions and settings',
    'workspace/worktrees': 'Worktrees for agent chats; idle ones are removed',
    'linuxbrew': 'Homebrew tools',
}


def folder_hint(path: str) -> str:
    """One line on what a folder is, for the Storage screen."""
    for prefix, hint in FOLDER_HINTS.items():
        if path == prefix or path.startswith(prefix + '/'):
            return hint
    parts = path.split('/')
    if parts[0] == 'home' and len(parts) > 1 and not parts[1].startswith('.'):
        return "A scratch folder in the agent's home; node_modules and venvs go after 2 days untouched"
    if parts[0] == 'workspace' and len(parts) == 2:
        return 'A repository the agent works in'
    return ''


def biggest(rows: list[Json], n: int = 6, dominant: float = 0.6) -> list[Json]:
    """The largest second-level folders, each named by the subfolder holding most of it (home/.local becomes
    home/.local/share/docker when that is 13 of its 14 GB)."""
    sizes = {i['path']: i['bytes'] for i in rows if i['path']}
    out = []
    for path, size in sizes.items():
        if path.count('/') != 1:
            continue
        name = path
        while True:
            kids = [
                (p, b) for p, b in sizes.items() if p.startswith(name + '/') and p.count('/') == name.count('/') + 1
            ]
            big = max(kids, key=lambda k: k[1], default=None)
            if not big or big[1] < dominant * size:
                break
            name = big[0]
        out.append({'path': name, 'bytes': sizes[name], 'hint': folder_hint(name)})
    return sorted(out, key=lambda i: -i['bytes'])[:n]


def reconcile(pool: Json, scan: Json) -> Json | None:
    """Why the pool's used figure is bigger than the folders: growth since the scan, and the disk's own overhead."""
    at_scan = sum((scan.get('units') or {}).values())
    folders = sum(i['bytes'] for i in scan.get('items') or [] if i.get('path') == '')
    if not at_scan or not folders:
        return None
    return {
        'now': pool['used'],
        'atScan': at_scan,
        'folders': folders,
        'overhead': max(0, at_scan - folders),
        'since': pool['used'] - at_scan,
    }


def manage() -> Json:
    """The admin's agent management: every agent with its limits and disk, disk sizing, and the jobs."""
    cfg, u = cluster.load(), store.watch.usage()
    st = cfg.get('storage') or {}
    per_person = st.get('mode') == 'per-person'
    defaults = cfg.get('defaults') or {}
    items = store.watch.containers().get('items') or []
    scan = {i.get('agent'): i['bytes'] for i in (u.get('scan') or {}).get('items') or [] if i.get('path') == ''}
    people = store.watch.people()
    agents = []
    for a in cfg.get('agents') or []:
        rows = [r for r in items if r.get('stack') == f'{domains.AGENT_STACK}{a["id"]}']
        state = 'up' if rows and all(domains.healthy(r) for r in rows) else 'starting' if rows else 'down'
        agents.append(
            {
                'id': a['id'],
                'owner': a.get('owner', ''),
                'memory': a.get('memory', ''),
                'cpus': a.get('cpus', 0),
                'customMemory': bool(defaults) and a.get('memory') != defaults.get('memory'),
                'customCpus': bool(defaults) and a.get('cpus') != defaults.get('cpus'),
                'state': state,
                'used': scan.get(a['id']),
                'disk': people.get((a.get('owner') or '').lower()) if per_person else None,
            }
        )
    return {
        'agents': agents,
        'owners': sorted({a['owner'] for a in agents if a['owner']}),
        'defaults': defaults,
        'storage': {
            'mode': st.get('mode', 'shared'),
            'personSize': st.get('person_size', ''),
            'hostReserve': st.get('host_reserve', '15%'),
            'host': u.get('pool') if per_person else None,
            'pool': None if per_person else u.get('pool'),
            'people': [{'email': e, 'agents': ids, **(people.get(e) or {})} for e, ids in cluster.owners().items()]
            if per_person
            else [],
        },
        'jobs': store.jobs.recent(),
        'watcher': store.watch.alive(),
        'access': access_setup(cfg),
    }


def access_setup(cfg: Json) -> Json:
    """What adding an agent involves here: who it can be for, and how people reach it."""
    auth = cfg.get('auth') or {}
    published = any(a.get('publish') for a in cfg.get('agents') or []) or bool((cfg.get('hub') or {}).get('publish'))
    owners = sorted({a.get('owner', '') for a in cfg.get('agents') or [] if a.get('owner')})
    return {
        'mode': auth.get('mode', ''),
        'cloudflare': auth.get('mode') == 'cloudflare-access' or auth.get('ingress') == 'cloudflared',
        'published': published,
        # published ports skip the gate, so such a setup is one person's (agentctl enforces it)
        'fixedOwner': owners[0] if published and len(owners) == 1 else '',
    }


def effect(s: Json) -> str:
    if not s['known']:
        return 'Not mapped yet: nothing happens on change.'
    parts = []
    for r in s['apply']:
        if 'copy' in r:
            parts.append('copied into the agent')
        elif 'restart' in r:
            parts.append(f'restarts {r["restart"].rstrip("-")}')
    return ('On change: ' + ', '.join(parts) + '.') if parts else (s['note'] or 'Read when used: nothing to apply.')


def kinds(s: Json) -> list[str]:
    """What a change does, as filter categories: restart, copy, read or unmapped."""
    if not s['known']:
        return ['unmapped']
    found = set()
    for r in s['apply']:
        if 'copy' in r:
            found.add('copy')
        elif 'restart' in r:
            found.add('restart')
    return sorted(found) or ['read']


def secrets() -> Json:
    items = [
        {k: s[k] for k in ('name', 'label', 'used_by', 'about', 'how', 'modified', 'versions', 'group')}
        | {'effect': effect(s), 'kinds': kinds(s)}
        for s in store.secrets.all_secrets()
    ]
    return {'items': items, 'events': store.secrets.events(20)}


def notifications() -> Json:
    s = notify.load()
    shown = shown_profiles()
    watch = notify.watcher.status if notify.watcher else {}
    recent = [
        {
            'at': r['at'],
            'kind': 'sent' if r['ok'] else 'failed',
            'ok': r['ok'],
            'title': r['title'] + (f' · {r["subtitle"]}' if r.get('subtitle') else ''),
            'detail': r['body'] if r['ok'] else f'not sent: {r["detail"]}',
        }
        for r in notify.recent
        if r.get('profile') not in cluster.agents() or r['profile'] in shown
    ][:15]
    return {
        'configured': bool(notify.BARK),
        'barkUp': notify.server_up(),
        'barkPublic': BARK_PUBLIC,
        'agents': len(shown),
        'watching': sum(1 for n in shown if watch.get(n) == 'watching'),
        'settings': {
            'deviceKey': s['device_key'],
            'minMinutes': s['min_minutes'],
            'muted': s['muted'],
            'encrypt': s['encrypt'],
            'encKey': s['enc_key'],
        },
        'recent': recent,
    }


def display_settings() -> Json:
    s = display.load()
    groups: dict[str, list[Json]] = {}
    for g, key, label, _ in display.items():
        groups.setdefault(g, []).append({'key': key, 'label': label, 'mode': display.mode(key, s)})
    return {'presenting': s['presenting'], 'groups': [{'name': g, 'items': i} for g, i in groups.items()]}
