"""Coolify's API, for deploy = "coolify": one Coolify service per stack, in one project, with an environment per
agent (its companions share it) and one for the core. Coolify recreates only the containers whose definition changed,
so one stack's deploy never restarts another's."""

import base64
import json
import os
import urllib.error
import urllib.request

from .util import Failed


class Api:
    def __init__(self, cfg, opener=None):
        c = cfg['coolify']
        self.base = c['url'].rstrip('/') + '/api/v1'
        self.token_file = c['token_file']
        self.project_name = c['project']
        self.opener = opener or urllib.request.urlopen

    def token(self):
        try:
            with open(self.token_file) as f:
                return f.read().strip()
        except OSError:
            raise Failed(f'Coolify token missing: {self.token_file} (agentctl install creates it)') from None

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                'Authorization': f'Bearer {self.token()}',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
        )
        try:
            with self.opener(req, timeout=60) as r:
                body = r.read() or b'{}'
        except urllib.error.HTTPError as e:
            raise Failed(f'Coolify {method} {path}: HTTP {e.code} {e.read()[:300]!r}') from None
        except urllib.error.URLError as e:
            raise Failed(f'Coolify unreachable at {self.base}: {e.reason}') from None
        try:
            return json.loads(body)
        except ValueError:
            return body.decode(errors='replace').strip()  # a few endpoints answer plain text (/version: "4.5.3")

    def server(self):
        servers = self.call('GET', '/servers')
        if not servers:
            raise Failed('Coolify has no server yet: finish its first-run setup')
        local = [s for s in servers if s.get('ip') in ('host.docker.internal', 'localhost', '127.0.0.1')]
        return (local or servers)[0]['uuid']

    def project(self):
        found = next((p for p in self.call('GET', '/projects') if p.get('name') == self.project_name), None)
        return found['uuid'] if found else self.call('POST', '/projects', {'name': self.project_name})['uuid']

    def environment(self, project, name):
        envs = self.call('GET', f'/projects/{project}/environments')
        if not any(e.get('name') == name for e in envs):
            self.call('POST', f'/projects/{project}/environments', {'name': name})


def environment_of(kind, key, cfg):
    if kind == 'core':
        return 'core'
    if kind == 'agent':
        return key
    return next(c['agent'] for c in cfg['companions'] if c['name'] == key)


def uuid_file(folder):
    return os.path.join(folder, '.coolify-service-uuid')


def stack_uuid(folder):
    try:
        with open(uuid_file(folder)) as f:
            return f.read().strip() or None
    except OSError:
        return None


def deploy(api, cfg, stack, kind, key, folder, text):
    raw = base64.b64encode(text.encode()).decode()
    uuid = stack_uuid(folder)
    if not uuid:
        project = api.project()
        env = environment_of(kind, key, cfg)
        api.environment(project, env)
        body = {
            'project_uuid': project,
            'server_uuid': api.server(),
            'environment_name': env,
            'name': stack,
            'docker_compose_raw': raw,
            'instant_deploy': False,
        }
        uuid = api.call('POST', '/services', body)['uuid']
        with open(uuid_file(folder), 'w') as f:
            f.write(uuid)
    else:
        api.call('PATCH', f'/services/{uuid}', {'docker_compose_raw': raw})
    started = api.call('POST', f'/deploy?uuid={uuid}')
    for d in (started.get('deployments') or []) if isinstance(started, dict) else []:
        if d.get('deployment_uuid'):
            wait(api, stack, d['deployment_uuid'])
    return uuid


DONE = {'finished', 'failed', 'cancelled', 'cancelled-by-user'}


def wait(api, stack, deployment, timeout_s=20 * 60, sleep=None, clock=None):
    """Until Coolify finishes a queued deployment; its log tail when it fails. (Service deploys usually start
    without a deployment id: the caller then watches the containers instead.)"""
    import time  # noqa: PLC0415 - patched in tests through the arguments

    sleep, clock = sleep or time.sleep, clock or time.time
    deadline = clock() + timeout_s
    while clock() < deadline:
        d = api.call('GET', f'/deployments/{deployment}')
        status = d.get('status', '') if isinstance(d, dict) else ''
        if status == 'finished':
            return
        if status in DONE:
            raise Failed(f'Coolify could not deploy {stack} ({status}): {_log_tail(d.get("logs"))}')
        sleep(5)
    raise Failed(f'Coolify was still deploying {stack} after {timeout_s // 60} min')


def _log_tail(logs, lines=6):
    try:
        entries = json.loads(logs) if isinstance(logs, str) else logs or []
    except ValueError:
        return str(logs)[-600:]
    text = '\n'.join(str(e.get('output', '')).strip() for e in entries if isinstance(e, dict) and e.get('output'))
    return '\n'.join(text.splitlines()[-lines:]) or 'no log'
