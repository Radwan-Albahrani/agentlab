"""The JSON API: one table per method, each route with the display key(s) it needs ('{0}' is the first path group)."""

import re

import actions
import cluster
import display
import scope
import screens
import store


class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


def _agent_get(path):

    def handler(m, q, host):
        status, out = cluster.call(m[0], path)
        if status != 200 or out is None:
            raise ValueError(f'{m[0]} is not reachable right now.')
        return out

    return handler


def _page_host():
    return {'host': cluster.request_host()}


def _agent_post(path, fields, done=None, extra=None):
    """A POST of only `fields` (plus `extra()`) to the agent's Accounts app; answers `done`, else the agent's answer."""

    def handler(m, b, host):
        status, out = cluster.call(m[0], path, {**{k: b[k] for k in fields if k in b}, **(extra() if extra else {})})
        if status == 502 or out is None:
            raise ValueError(f'{m[0]} is not reachable right now.')
        if out.get('ok') is False:
            raise ValueError(out.get('error') or 'That did not work.')
        return done or out

    return handler


def _agent_page(m, q, host):
    status, page = cluster.call(m[0], '/api/page')
    if status != 200 or page is None:
        raise ValueError(f'{m[0]} is not reachable right now.')
    return screens.accounts(host, m[0], page)


def _env_value(m, q, host):
    status, out = cluster.call(m[0], '/api/env/value?k=' + re.sub(r'[^\w]', '', q.get('k', '')))
    if status != 200 or out is None:
        raise ValueError('Not available.')
    return out


def _config(m, q, host):
    try:
        return screens.config(q.get('id', ''))
    except LookupError:
        raise NotFoundError from None


def _secret_value(m, q, host):
    try:
        return {'value': store.secrets.value(q.get('name', ''))}
    except (OSError, ValueError):
        raise NotFoundError from None


def _companion_secret_value(m, q, host):
    try:
        return {'value': store.secrets.value(f'companions/{m[0]}/{q.get("file", "")}')}
    except (OSError, ValueError):
        raise NotFoundError from None


def _logs(m, q, host):
    text, at = store.watch.logs(q.get('name', ''))
    return {'text': text, 'at': at}


GET = [
    (r'/api/nav', None, lambda m, q, host: screens.nav()),
    (r'/api/overview', None, lambda m, q, host: screens.overview()),
    (r'/api/agents', 'page.agents', lambda m, q, host: screens.agents(host)),
    (r'/api/agents/([\w-]+)', 'profile.{0}', lambda m, q, host: screens.agent(host, m[0])),
    (r'/api/agents/([\w-]+)/accounts', 'profile.{0}', _agent_page),
    (r'/api/agents/([\w-]+)/accounts/env-value', ('profile.{0}', 'agent.env'), _env_value),
    (r'/api/agents/([\w-]+)/onboarding', 'profile.{0}', _agent_get('/api/onboarding')),
    (r'/api/agents/([\w-]+)/devices', ('profile.{0}', 'agent.pairing'), _agent_get('/api/devices')),
    (r'/api/companions/([\w-]+)', 'companion.{0}', lambda m, q, host: screens.companion(m[0])),
    (r'/api/companions/([\w-]+)/secrets', 'companion.{0}', lambda m, q, host: screens.companion_secrets(m[0])),
    (r'/api/companions/([\w-]+)/secrets/value', 'companion.{0}', _companion_secret_value),
    (r'/api/companions/([\w-]+)/logs', 'companion.{0}', lambda m, q, host: screens.companion_logs(m[0])),
    (r'/api/services', 'page.services', lambda m, q, host: screens.services()),
    (r'/api/logs', 'page.services', _logs),
    (r'/api/configs', 'page.config', lambda m, q, host: screens.configs()),
    (r'/api/config', 'page.config', _config),
    (r'/api/storage', 'page.storage', lambda m, q, host: screens.storage()),
    (r'/api/secrets', 'page.secrets', lambda m, q, host: screens.secrets()),
    (r'/api/secrets/value', 'page.secrets', _secret_value),
    (
        r'/api/secrets/versions',
        'page.secrets',
        lambda m, q, host: {'versions': store.secrets.secret_versions(q.get('name', ''))},
    ),
    (r'/api/notifications', 'page.notifications', lambda m, q, host: screens.notifications()),
    (r'/api/display', 'display', lambda m, q, host: screens.display_settings()),
]


def _account_act(m, b, host):
    status, out = cluster.call(m[0], '/api/act', b)
    if status == 502 or out is None:
        raise ValueError(f'{m[0]} is not reachable right now.')
    if not out.get('ok'):
        raise ValueError(out.get('error') or 'That did not work.')
    return out.get('message') or 'Done.'


def _env(m, b, host):
    _status, out = cluster.call(m[0], f'/api/env/{m[1]}', b)
    if out is None:
        raise ValueError(f'{m[0]} is not reachable right now.')
    if not out.get('ok'):
        raise ValueError('; '.join(out.get('errors') or ['Not saved.']))
    return 'Saved.' if m[1] != 'delete' else 'Removed.'


def _companion(m, b, host):
    return actions.companion(m[0], m[1], b)


POST = [
    (r'/api/agents/([\w-]+)/accounts/act', 'profile.{0}', _account_act),
    (r'/api/agents/([\w-]+)/accounts/env/(set|delete|import)', ('profile.{0}', 'agent.env'), _env),
    (r'/api/agents/([\w-]+)/onboarding/finish', 'profile.{0}', _agent_post('/api/onboarding/finish', (), 'All set.')),
    (r'/api/agents/([\w-]+)/pair', 'profile.{0}', _agent_post('/api/pair', ('kind', 'label'), extra=_page_host)),
    (
        r'/api/agents/([\w-]+)/devices/revoke',
        ('profile.{0}', 'agent.pairing'),
        _agent_post('/api/devices/revoke', ('id',), 'Signed out.'),
    ),
    (r'/api/companions/([\w-]+)/(restart|remove|settings)', 'companion.{0}', _companion),
    (r'/api/companions/([\w-]+)/(ask)', ('companion.{0}', 'companion.ask'), _companion),
    (r'/api/companions/([\w-]+)/(poll)', ('companion.{0}', 'companion.polls'), _companion),
    (r'/api/companions/([\w-]+)/(pulls|review)', ('companion.{0}', 'companion.pulls'), _companion),
    (r'/api/companions/([\w-]+)/(secret)', ('companion.{0}', 'companion.settings'), _companion),
    (r'/api/services/(restart|logs)', 'page.services', lambda m, b, host: actions.service(m[0], b)),
    (r'/api/config/deploy', 'page.config', lambda m, b, host: actions.config_deploy(b)),
    (r'/api/storage/(rescan|cleanup)', ('page.storage', 'storage.manage'), lambda m, b, host: actions.storage(m[0])),
    (r'/api/secrets/(save|create|delete|restore)', 'page.secrets', lambda m, b, host: actions.secret(m[0], b)),
    (
        r'/api/notify/(test|mute|encrypt|minutes|enckey|key)',
        'page.notifications',
        lambda m, b, host: actions.notification(m[0], b),
    ),
    (r'/api/display/mode', 'display', lambda m, b, host: actions.display_mode(b)),
    (r'/api/display/presenting', 'display', lambda m, b, host: actions.presenting(b)),
]


def resolve(table, path):
    """(handler, groups) for a route this person may use, else NotFoundError / ForbiddenError."""
    for pattern, keys, handler in table:
        m = re.fullmatch(pattern, path)
        if m:
            for key in (keys,) if isinstance(keys, str) else keys or ():
                k = key.format(*m.groups())
                if not _known(key, m.groups()) or not display.visible(k):
                    raise NotFoundError
                if not scope.current().sees(k):
                    raise ForbiddenError
            return handler, m.groups()
    raise NotFoundError


def _known(key, groups):
    if key == 'profile.{0}':
        return groups[0] in cluster.agents()
    if key == 'companion.{0}':
        return groups[0] in cluster.companions()
    return True
