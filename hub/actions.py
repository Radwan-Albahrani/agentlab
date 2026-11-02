"""Everything the page's buttons change. Each action returns the toast text; ValueError carries a message for the user.
Host work (restarts, logs, deploys, cleanups) is a request file the watcher picks up within a second."""

import re

import cluster
import display
import notify
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
        store.watch.request(f'remove~companion~{name}')  # the watcher stops it and archives its data
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
    """Stacks are rendered by agentctl from cluster.toml, so the page redeploys them as they are; changes go into
    cluster.toml and `agentctl apply`."""
    if b.get('id') not in {s['id'] for s in store.stacks.stacks()}:
        raise ValueError('Unknown stack.')
    store.watch.request('deploy~' + b['id'])
    return 'Deploying; the result shows under Deploys.'


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
    key = re.sub(r'^https?://[^/]+/', '', b.get('deviceKey', '').strip()).split('/')[0]  # a pasted Bark URL works too
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
    url = notify.newest_chat_link(first) if first else ''  # tapping it tries the tap-through into the T3 app
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
