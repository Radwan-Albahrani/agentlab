"""What needs the owner's decision or a fix, most urgent first."""

import time

import cluster
import display
import domains
import scope
import store
from shapes import epoch, link, post

DAY = 86400
TONE_ORDER = {'bad': 0, 'warn': 1, 'info': 2}
WAITING_LABEL = {
    'approval': 'Approve a change',
    'send': 'Send the reply',
    'login': 'Send a login',
    'answer': 'Answer a question',
}
WAITING_ICON = {'approval': 'alert', 'send': 'send', 'login': 'key', 'answer': 'chat'}


def _item(about, tone, icon, title, detail, actions=(), since=None):
    """`about` is the display key the item concerns; it is dropped when that key is hidden."""
    return about, {
        'tone': tone,
        'icon': icon,
        'title': title,
        'detail': detail,
        'since': since,
        'actions': list(actions),
    }


def _companions(comps):
    for c in comps:
        nice, about = c['display'], f'companion.{c["name"]}'
        if c['state'] == 'unconfigured':
            why = 'Its Slack app or secrets are missing. Your agent can set it up: ask it in T3.'
            settings = link('Secrets', f'{c["url"]}#secrets', 'key')
            yield _item(about, 'info', 'bot', f'{nice} is not set up yet', why, [settings])
        elif c['state'] != 'live':
            where = 'offline' if c['state'] == 'offline' else 'disconnected from Slack'
            restart = post('Restart', f'/api/companions/{c["name"]}/restart', 'power')
            yield _item(
                about,
                'bad',
                'bot',
                f'{nice} is {where}',
                'It cannot take or finish tasks.',
                [restart],
                c['heartbeat'].get('at'),
            )
        for t in c['tasks']:
            if t['status'] != 'waiting':
                continue
            who = f' · for {t["requester"]}' if t.get('requester') else ''
            title = f'{WAITING_LABEL.get(t["waiting"], "Needs you")}: {t["title"]}'
            open_slack = [link('Open in Slack', t['slack'], 'slack', True)] if t.get('slack') else []
            yield _item(
                about,
                'warn',
                WAITING_ICON.get(t['waiting'], 'alert'),
                title,
                f'{nice}{who}',
                open_slack,
                epoch(t['started']),
            )


def _full(pool, about, title):
    pct = 100 * pool['used'] / pool['size']
    if pct >= 80:
        free = f'{pool["avail"] / 2**30:.1f} GB left of {pool["size"] / 2**30:.0f} GB.'
        actions = [post('Clean up now', '/api/storage/cleanup', 'broom'), link('Storage', '/storage', 'arrow')]
        yield _item(about, 'bad' if pct >= 90 else 'warn', 'disk', f'{title} {pct:.0f}% full', free, actions)


def _storage():
    usage = store.watch.usage()
    if not usage:
        return
    if cluster.storage_mode() == 'shared':
        if usage.get('pool'):
            yield from _full(usage['pool'], 'storage.manage', 'Agents pool')
        return
    disks = store.watch.people()
    for email in cluster.owners():
        disk, about = disks.get(email), f'person.{email}'
        whose = 'Your disk' if email == scope.current().email else f"{email}'s disk"
        if disk:
            yield from _full(disk, about, whose)
        else:
            why = 'Their agents cannot start without it (agentlab-disks.service mounts it).'
            yield _item(about, 'bad', 'disk', f'{whose} is not mounted', why)


def _watcher():
    if not store.watch.alive():
        why = 'Storage numbers, secret changes and restarts wait for it (systemd agentlab-watch).'
        yield _item('page.services', 'bad', 'clock', 'The host watcher is not running', why)


def _secrets():
    for e in store.watch.events({'secret'}, 20):
        if not e.get('ok', True) and time.time() - e['at'] < DAY:
            open_secrets = [link('Secrets', '/secrets', 'arrow')]
            yield _item(
                'page.secrets',
                'bad',
                'key',
                f'Secret change not applied: {e["title"]}',
                e.get('detail', ''),
                open_secrets,
            )


def _containers():
    for r in store.watch.containers().get('items') or []:
        if not domains.healthy(r):
            title = f'{r["service"]} is {r["status"] or r["state"]}'
            where = domains.stack_label(r.get('stack') or 'other')
            yield _item('page.services', 'bad', 'power', title, where, [link('Services', '/services', 'arrow')])


def _accounts(summaries):
    for name, s in summaries.items():
        if s is None:
            continue
        a = s['accounts']
        open_accounts = [link('Open', f'/agents/{name}/accounts', 'arrow')]
        if not (a['claude']['signedIn'] or a['codex']['signedIn']):
            why = 'Sign in to Claude or Codex; the agent cannot work without one.'
            yield _item(f'profile.{name}', 'warn', 'key', f'{name} has no AI account', why, open_accounts)
        elif not a['github']['signedIn']:
            why = 'It cannot open pull requests until you do.'
            yield _item(f'profile.{name}', 'info', 'github', f'{name} is not signed in to GitHub', why, open_accounts)


def _shown(about):
    return display.visible(about) and scope.current().sees(about)


def needs(summaries, comps):
    items = [*_companions(comps), *_storage(), *_watcher(), *_secrets(), *_containers(), *_accounts(summaries)]
    return sorted((i for about, i in items if _shown(about)), key=lambda i: TONE_ORDER[i['tone']])


def count(comps):
    """Menu badge count from the cheap sources only (no calls to the agents)."""
    waiting = sum(1 for c in comps for t in c['tasks'] if t['status'] == 'waiting')
    down = sum(1 for c in comps if c['state'] not in ('live', 'unconfigured'))
    usage = store.watch.usage()
    disks = [(usage.get('pool'), 'storage.manage')] if cluster.storage_mode() == 'shared' else []
    disks += [(d, f'person.{email}') for email, d in store.watch.people().items()]
    full = sum(1 for d, about in disks if d and d['used'] / d['size'] >= 0.8 and _shown(about))
    return waiting + down + full
