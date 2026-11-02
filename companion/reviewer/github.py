"""A GitHub App: its id and private key make a JWT; the JWT lists installations and mints installation tokens
(an hour each, cached until shortly before they expire). Calls go to api.github.com over HTTPS, out only."""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

import jwt

API = 'https://api.github.com'


class GitHubError(Exception):
    def __init__(self, status, message):
        super().__init__(f'GitHub {status}: {message}')
        self.status = status


class App:
    def __init__(self, app_id, private_key):
        self.app_id, self.key = str(app_id).strip(), private_key
        self._tokens = {}  # installation id -> (token, expires epoch)
        self._installs = (0.0, [])
        self._slug = ''

    # -------------------------------------------------------------- identity
    def _jwt(self):
        now = int(time.time())
        return jwt.encode({'iat': now - 60, 'exp': now + 540, 'iss': self.app_id}, self.key, algorithm='RS256')

    def slug(self):
        """The App's slug: its bot is <slug>[bot] in REST and <slug> in GraphQL."""
        if not self._slug:
            self._slug = self.call('GET', '/app', auth=f'Bearer {self._jwt()}')['slug']
        return self._slug

    def installations(self):
        """[{id, account}] where the App is installed, re-read every 10 minutes."""
        at, cached = self._installs
        if time.time() - at > 600:
            found = self.call('GET', '/app/installations?per_page=100', auth=f'Bearer {self._jwt()}')
            cached = [{'id': i['id'], 'account': i['account']['login']} for i in found]
            self._installs = (time.time(), cached)
        return cached

    def token(self, installation):
        tok, until = self._tokens.get(installation, ('', 0))
        if time.time() > until - 300:
            r = self.call('POST', f'/app/installations/{installation}/access_tokens', auth=f'Bearer {self._jwt()}')
            tok = r['token']
            until = time.time() + 3600 if not r.get('expires_at') else _epoch(r['expires_at'])
            self._tokens[installation] = (tok, until)
        return tok

    def installation_for(self, repo):
        """The installation that covers owner/repo (by its account), or None."""
        owner = repo.split('/', 1)[0].lower()
        return next((i['id'] for i in self.installations() if i['account'].lower() == owner), None)

    # -------------------------------------------------------------- calls
    def call(self, method, path, body=None, auth=None, installation=None):
        """One REST call. `installation` signs it with that installation's token."""
        if installation is not None:
            auth = f'token {self.token(installation)}'
        req = urllib.request.Request(
            path if path.startswith('http') else API + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
                'User-Agent': 'agentlab-companion',
                'Authorization': auth or '',
                **({'Content-Type': 'application/json'} if body is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get('message', '')
            except ValueError:
                msg = e.reason
            raise GitHubError(e.code, msg) from None
        return json.loads(raw) if raw else {}

    def pages(self, path, installation, limit=3000):
        """Every item of a paginated list (per_page=100), up to `limit`."""
        out, page = [], 1
        sep = '&' if '?' in path else '?'
        while len(out) < limit:
            batch = self.call('GET', f'{path}{sep}per_page=100&page={page}', installation=installation)
            out += batch
            if len(batch) < 100:
                break
            page += 1
        return out[:limit]

    def graphql(self, query, installation, **variables):
        r = self.call('POST', '/graphql', {'query': query, 'variables': variables}, installation=installation)
        if r.get('errors'):
            raise GitHubError(200, '; '.join(e.get('message', '') for e in r['errors'])[:300])
        return r['data']


def _epoch(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()
