"""The page's button actions: each returns the toast text; ValueError carries a message for the user."""

import re

import cluster
import display
import notify
import scope
import screens
import store


def companion(name, what, b):
    if name not in cluster.companions():
        raise ValueError('Unknown companion.')
    if what == 'restart':
        c = store.watch.companion_container(name)
        if not c:
            raise ValueError(f'No {name} container found.')
        store.watch.request(f'restart~{c}')
        return f'{cluster.display_name(name)} is restarting.'
    if what == 'remove':
        store.watch.request(f'remove~companion~{name}')
        return f'Removing {cluster.display_name(name)}; it stops within a minute.'
    if what == 'poll':
        store.companions.poll_change(name, b.get('poll', ''), b)
        return (
            'Poll closing.'
            if b.get('close')
            else f'Saved. {cluster.display_name(name)} updates the poll within seconds.'
        )
    if what == 'pulls':
        store.companions.pulls_refresh(name)
        return 'Refreshing.'
    if what == 'review':
        pr = store.companions.review(name, str(b.get('pr', '')))
        return f'Reviewing #{pr["number"]}. {cluster.display_name(name)} posts the result on the pull request.'
    if what == 'secret':
        changed = store.companions.save_secret(name, str(b.get('file', '')), str(b.get('value', '')))
        return f'Saved; {cluster.display_name(name)} restarts with it.' if changed else 'No change.'
    if what == 'ask':
        store.companions.ask(name, b.get('text'), b.get('channel', ''), b.get('review', True))
        return f'Sent. {cluster.display_name(name)} is on it; follow along in your Slack DM.'
    f = store.companions.set_setting(name, b.get('key', ''), b.get('value'))
    return f'{f["label"]} saved. {cluster.display_name(name)} picks it up within seconds.'


def service(what, b):
    if b.get('name') not in store.watch.container_names():
        raise ValueError('Unknown container.')
    store.watch.request(f'{what}~{b["name"]}')
    return 'Restarting.' if what == 'restart' else 'Fetching logs…'


def config_deploy(b):
    if b.get('id') not in {s['id'] for s in store.stacks.stacks()}:
        raise ValueError('Unknown stack.')
    store.watch.request('deploy~' + b['id'])
    return 'Deploying; the result shows under Deploys.'


AGENT_ID = re.compile(r'^[a-z][a-z0-9-]{0,30}[a-z0-9]$|^[a-z]$')
EMAIL = re.compile(r'^[^@\s/]+@[^@\s/]+\.[^@\s/]+$')
SIZE = re.compile(r'^\d+(\.\d+)?[kmgt]?b?$', re.IGNORECASE)
RESERVE = re.compile(r'^\d{1,2}%$|^\d+(\.\d+)?[kmgt]?b?$', re.IGNORECASE)
NO_WATCHER = 'The host watcher (agentlab-watch) is not running, so nothing can change right now.'


def _limit_args(b):
    out = {}
    memory, cpus = str(b.get('memory') or '').strip().lower(), str(b.get('cpus') or '').strip().lower()
    if memory:
        if memory != 'default' and not SIZE.match(memory):
            raise ValueError('Memory is a size such as 8g or 16g.')
        out['memory'] = memory
    if cpus:
        try:
            ok = cpus == 'default' or 0 < float(cpus) <= 512
        except ValueError:
            ok = False
        if not ok:
            raise ValueError('CPUs is a number such as 2 or 4.')
        out['cpus'] = cpus
    return out


def manage(what, b):
    """Queue an agent management job for the host; -> the toast text."""
    if not store.watch.alive():
        raise ValueError(NO_WATCHER)
    by, known = scope.current().email, cluster.agents()
    aid = str(b.get('id') or '').strip().lower()
    if what == 'add':
        email = str(b.get('email') or '').strip().lower()
        fixed = screens.access_setup(cluster.load())['fixedOwner']
        if fixed and email and email != fixed:
            raise ValueError(
                f'This setup is for one person ({fixed}): its agents are published straight on the network.'
            )
        email = email or fixed
        if not AGENT_ID.match(aid):
            raise ValueError('The name is lowercase letters, digits and dashes, starting with a letter.')
        if aid in known:
            raise ValueError(f'There is already an agent called {aid}.')
        if not EMAIL.match(email):
            raise ValueError('Enter the email address the person signs in with.')
        store.jobs.submit('agent.add', {'id': aid, 'email': email, **_limit_args(b)}, by)
        return f'Adding {aid}. Follow along below; it takes a few minutes.'
    if aid not in known:
        raise ValueError('Unknown agent.')
    if what == 'resize':
        args = _limit_args(b)
        if not args:
            raise ValueError('Nothing to change.')
        store.jobs.submit('agent.set', {'id': aid, **args}, by)
        return f'Resizing {aid}; it restarts with the new limits.'
    delete = b.get('deleteData') is True
    if delete and str(b.get('confirm') or '').strip() != aid:
        raise ValueError(f'Type {aid} to confirm deleting its files.')
    tied = [n for n, owner in cluster.companions().items() if owner == aid]
    if tied:
        raise ValueError(f'{aid} has companions ({", ".join(tied)}): remove them first, on their pages.')
    store.jobs.submit('agent.remove', {'id': aid, 'delete_data': delete}, by)
    return f'Removing {aid}.'


def disk_sizes(b):
    if not store.watch.alive():
        raise ValueError(NO_WATCHER)
    size = str(b.get('personSize') or '').strip().lower()
    reserve = str(b.get('hostReserve') or '').strip().lower()
    if size and size != 'auto' and not SIZE.match(size):
        raise ValueError('The disk size is "auto" or a size such as 80g.')
    if reserve and not RESERVE.match(reserve):
        raise ValueError('The host reserve is a share such as 15% or a size such as 64g.')
    if not (size or reserve):
        raise ValueError('Nothing to change.')
    store.jobs.submit('storage.set', {'person_size': size, 'host_reserve': reserve}, scope.current().email)
    return 'Resizing disks. Agents on a disk that shrinks stop for a few minutes.'


def storage(what):
    store.watch.request(what)
    return (
        'Measuring now; the breakdown updates in about a minute.'
        if what == 'rescan'
        else 'Cleanup started; the result shows below.'
    )


def secret(what, b):
    name = b.get('name', '')
    if what == 'save':
        return (
            f'{name} saved; it applies within 30 s.' if store.secrets.save(name, b.get('value', '')) else 'No change.'
        )
    if what == 'create':
        store.secrets.save(name, b.get('value', ''), create=True)
        return f'{name} added.'
    if what == 'delete':
        store.secrets.delete(name)
        return f'{name} deleted (a copy stays in its versions).'
    store.secrets.restore(name, b['version'])
    return f'{name} restored; it applies within 30 s.'


def _toggle(setting):
    notify.update(**{setting: not notify.load()[setting]})
    return notify.load()[setting]


def _device_key(b):
    key = re.sub(r'^https?://[^/]+/', '', b.get('deviceKey', '').strip()).split('/')[0]  # accepts a pasted Bark URL
    if re.fullmatch(r'[0-9a-f]{64}', key):
        raise ValueError("That is the phone's Apple push token. Paste the short key shown under the server in Bark.")
    notify.update(device_key=key)
    return 'Device key saved.'


def _encryption_key(b):
    key = b.get('key', '').strip()
    if len(key) != 16:
        raise ValueError('The key is 16 characters.')
    notify.update(enc_key=key)
    return 'Key saved.'


def _test_push(_b):
    body = 'If you can read this, agent notifications work.'
    first = next(iter(cluster.ids()), '')
    url = notify.newest_chat_link(first) if first else ''
    notify.send('Agents · Test', body, 'Sent from the hub', 'timeSensitive', group='test', kind='test', url=url)
    return 'Test sent.'


def _minutes(b):
    notify.update(min_minutes=max(0, min(240, int(b.get('minutes') or 3))))
    return 'Saved.'


NOTIFICATION_ACTIONS = {
    'test': _test_push,
    'mute': lambda _b: 'Muted.' if _toggle('muted') else 'Unmuted.',
    'encrypt': lambda _b: 'Encryption on.' if _toggle('encrypt') else 'Encryption off.',
    'minutes': _minutes,
    'enckey': _encryption_key,
    'key': _device_key,
}


def notification(act, b):
    if act not in NOTIFICATION_ACTIONS:
        raise ValueError('Unknown action.')
    return NOTIFICATION_ACTIONS[act](b)


def display_mode(b):
    display.set_mode(b.get('key', ''), b.get('value'))
    return 'Saved.'


def presenting(b):
    on = (not display.load()['presenting']) if b.get('toggle') else bool(b.get('on'))
    display.set_presenting(on)
    return 'Done.'
