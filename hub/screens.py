"""Each screen's JSON; hidden or out-of-scope things are left out here, never sent to the browser."""

import os
import time

import cluster
import display
import domains
import needs
import notify
import scope
import store
from shapes import epoch

BARK_PUBLIC = os.environ.get('BARK_PUBLIC', '')  # Bark server address for the phone app
DAY = 86400


def see(key):
    return display.visible(key) and scope.current().sees(key)


def shown_profiles():
    return [p for p in cluster.ids() if see(f'profile.{p}')]


def shown_companions(profile=None):
    return [
        c
        for c in store.companions.all_companions()
        if see(f'companion.{c["name"]}') and (profile is None or c['profile'] == profile)
    ]


def nav():
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
        ('services', '/services', 'Services'),
        ('config', '/config', 'Configs'),
        ('storage', '/storage', 'Storage'),
        ('secrets', '/secrets', 'Secrets'),
        ('notifications', '/notifications', 'Notifications'),
    ):
        if not see(f'page.{key}'):
            continue
        entry = {'key': key, 'path': path, 'label': label}
        if key == 'services':
            entry['count'] = sum(1 for r in items if not domains.healthy(r))
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


def overview():
    sums = cluster.summaries(shown_profiles())
    comps = shown_companions()
    out = {}
    if see('overview.tiles'):
        tiles = {
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
        activity = [dict(e, source=c['name']) for c in comps for e in c['events'][:40] if e.get('kind') != 'live']
        if see('page.services'):
            activity += [dict(e, source='server') for e in store.watch.events(None, 40) if e.get('kind') != 'scan']
        out['activity'] = sorted(activity, key=lambda e: e.get('at', 0), reverse=True)[:14]
    if see('overview.stacks') and see('page.services'):
        groups = domains.by_stack()
        out['stacks'] = {
            'at': store.watch.containers().get('at'),
            'rows': [domains.stack(sid, groups[sid]) for _, sids in domains.by_domain(list(groups)) for sid in sids],
        }
    return out


def agent_card(n, s):
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
            'chat': links['chat'],
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


def agents(host):
    sums = cluster.summaries(shown_profiles())
    out = {'agents': [agent_card(n, s) for n, s in sums.items()]}
    if see('agent.resources'):
        out['memory'] = {
            'usedMB': sum((s.get('resources') or {}).get('usedMB') or 0 for s in sums.values() if s),
            'poolMB': cluster.pool_mb(),
        }
    return out


def agent(host, prof):
    s = cluster.summary(prof)
    groups = domains.by_stack()
    sids = sorted(
        (sid for sid in groups if domains.domain_of(sid)[0] == prof), key=lambda x: domains.domain_of(x)[1] != 'agent'
    )
    out = {
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


def accounts(host, prof, page):
    """The agent's own Accounts page minus hidden items, plus its browser link."""
    if not see('agent.env'):
        page.pop('env', None)
    page['browserUrl'] = cluster.links(prof)['browser'] if page.get('browserUp') else None
    return page


def companion(name):
    c = store.companions.companion(name)
    settings = store.companions.settings(name)
    tasks = [
        dict(
            t,
            startedAt=epoch(t.get('started')),
            endedAt=epoch(t.get('ended')) or None,
            t3=notify.thread_link(c['profile'], t['thread']) if t.get('thread') else '',
        )
        for t in c['tasks']
    ]
    poll_of = {p['task']: p['id'] for p in c['polls']}
    for t in tasks:
        t.pop('started', None), t.pop('ended', None)
        t['poll'] = poll_of.get(t['id'])
    hb = c['heartbeat']
    mode = next(
        ({o['value']: o['label'] for o in f.get('options', [])}.get(v, v) for f, v in settings if f['key'] == 'mode'),
        hb.get('mode', ''),
    )
    out = {
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
            t = by_id.get((p.get('review') or {}).get('task'))
            if t:
                p['review'].update(t3=t['t3'], slack=t['slack'])
        me = next((v for f, v in settings if f['key'] == 'github_user'), '') or ''
        out['pulls'] = {'github': hb['github'], 'me': me, 'items': c['pulls']}
    channels = store.companions.channels(name)
    if see('companion.ask') and channels is not None:
        out['channels'] = channels
    if see('companion.settings'):
        people = [{'value': p['id'], 'label': p['name'], 'avatar': p.get('avatar', '')} for p in hb.get('people') or []]
        out['settings'] = [
            dict(f, value=v, **({'options': people} if f['type'] == 'people' else {})) for f, v in settings
        ]
    return out


def companion_secrets(name):
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


def companion_logs(name):
    text, at = store.companions.log_tail(name)
    return {'text': text, 'at': at}


def services():
    groups = domains.by_stack()
    out = {'domains': [], 'other': []}
    for prof, sids in domains.by_domain(list(groups)):
        stacks = [domains.stack(sid, groups[sid]) for sid in sids]
        if prof:
            out['domains'].append({'profile': prof, 'stacks': stacks})
        else:
            out['other'] = stacks
    return out


def configs():
    stacks = {s['id']: s for s in store.stacks.stacks()}
    out = {'domains': [], 'other': []}
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


def config(sid):
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


def people_disks():
    """[{email, agents, size?, ...}]: each person in scope with their disk and the agents on it."""
    disks, shown = store.watch.people(), set(shown_profiles())
    return [
        {'email': email, 'agents': [a for a in ids if a in shown], **(disks.get(email) or {})}
        for email, ids in cluster.owners().items()
        if see(f'person.{email}') and any(a in shown for a in ids)
    ]


def my_disk():
    """(disk, label) for the overview: the shared pool, or the person's own disk."""
    if cluster.storage_mode() == 'per-person':
        if scope.current().admin:
            return None, ''
        return store.watch.people().get(scope.current().email), 'Your disk'
    return (store.watch.usage().get('pool'), 'Server disk') if see('storage.manage') else (None, '')


def storage():
    u = store.watch.usage()
    mode = cluster.storage_mode()
    out = {
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
                        'biggest': sorted(
                            ({'path': i['path'], 'bytes': i['bytes']} for i in mine if i['path'].count('/') == 1),
                            key=lambda i: -i['bytes'],
                        )[:6],
                    }
                )
        out['scan'] = {'at': scan.get('at'), 'took': scan.get('took', 0), 'profiles': profs}
    return out


def effect(s):
    if not s['known']:
        return 'Not mapped yet: nothing happens on change.'
    parts = []
    for r in s['apply']:
        if 'copy' in r:
            parts.append('copied into the agent')
        elif 'restart' in r:
            parts.append(f'restarts {r["restart"].rstrip("-")}')
    return ('On change: ' + ', '.join(parts) + '.') if parts else (s['note'] or 'Read when used: nothing to apply.')


def kinds(s):
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


def secrets():
    items = [
        {k: s[k] for k in ('name', 'label', 'used_by', 'about', 'how', 'modified', 'versions', 'group')}
        | {'effect': effect(s), 'kinds': kinds(s)}
        for s in store.secrets.all_secrets()
    ]
    return {'items': items, 'events': store.secrets.events(20)}


def notifications():
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


def display_settings():
    s = display.load()
    groups = {}
    for g, key, label, _ in display.items():
        groups.setdefault(g, []).append({'key': key, 'label': label, 'mode': display.mode(key, s)})
    return {'presenting': s['presenting'], 'groups': [{'name': g, 'items': i} for g, i in groups.items()]}
