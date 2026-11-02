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
    api.call('POST', f'/deploy?uuid={uuid}')
    return uuid
