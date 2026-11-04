"""Private HTTPS sign-in: the gate as an OIDC client (code flow + PKCE) of an Access for SaaS application."""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger('gate')
CALLBACK, LOGOUT = '/_agentlab/oidc/callback', '/_agentlab/oidc/logout'
SESSION, PENDING = '__Host-agentlab_session', '__Host-agentlab_oidc'  # __Host-: Secure, Path=/, this host only
SESSION_TTL = 12 * 3600
PENDING_TTL = 600
PROOF_TTL = 120
LEEWAY = 30
FILES = {'client_id': 'oidc-client-id', 'client_secret': 'oidc-client-secret', 'key': 'session.key'}
LIVE = 'https-live'  # agentctl writes it once Access covers 443; plain HTTP is then redirected


class SignInError(Exception):
    pass


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def derive(key, label):
    """A separate key per use, so a cookie key can never verify a proof or the reverse."""
    return hmac.new(key, label.encode(), hashlib.sha256).digest()


def key_bytes(text):
    text = text.strip()
    try:
        return bytes.fromhex(text)
    except ValueError:
        return text.encode()


def proof(key, user, admin, agent, now=None):
    """X-Agentlab-Proof '<expiry>.<HMAC>'; the hub checks it, so keep the format in sync."""
    exp = int(now if now is not None else time.time()) + PROOF_TTL
    msg = f'{user}\n{admin}\n{agent}\n{exp}'.encode()
    return f'{exp}.{_b64(hmac.new(derive(key, "agentlab proof v1"), msg, hashlib.sha256).digest())}'


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def post_form(url, form, headers):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data, method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SignInError(f'token endpoint answered HTTP {e.code}') from None


class Secrets:
    """The secrets folder's files, re-read when they change."""

    def __init__(self, folder):
        self.folder = folder
        self._seen = {}

    def get(self, name):
        path = os.path.join(self.folder, FILES.get(name, name))
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            return ''
        seen = self._seen.get(path)
        if seen and seen[0] == mtime:
            return seen[1]
        try:
            with open(path, encoding='utf-8') as f:
                value = f.read().strip()
        except OSError:
            return ''
        self._seen[path] = (mtime, value)
        return value

    def ready(self):
        return all(self.get(k) for k in FILES)

    def live(self):
        return os.path.exists(os.path.join(self.folder, LIVE))


class Provider:
    """Cached discovery document and keys; endpoints must stay on the team's Access domain whatever it says."""

    max_age = 3600

    def __init__(self, fetch=get_json, post=post_form, gap=30):
        self._fetch, self._post, self.gap = fetch, post, gap
        self._lock = threading.Lock()
        self._conf, self._conf_at, self._conf_for = {}, float('-inf'), None
        self._keys, self._keys_at = {}, float('-inf')

    @staticmethod
    def issuer(team, client_id):
        return f'https://{team}.cloudflareaccess.com/cdn-cgi/access/sso/oidc/{client_id}'

    def config(self, team, client_id):
        issuer = self.issuer(team, client_id)
        with self._lock:
            if self._conf_for == issuer and time.monotonic() - self._conf_at < self.max_age:
                return self._conf
        try:
            conf = self._fetch(f'{issuer}/.well-known/openid-configuration')
        except (OSError, ValueError) as e:
            raise SignInError(f'cannot read the sign-in configuration: {e}') from None
        if not isinstance(conf, dict) or conf.get('issuer') != issuer:
            raise SignInError('the sign-in configuration names another issuer')
        site = f'https://{team}.cloudflareaccess.com/'
        for k in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
            if not str(conf.get(k, '')).startswith(site):
                raise SignInError(f'{k} is not on {site}')
        with self._lock:
            self._conf, self._conf_at, self._conf_for = conf, time.monotonic(), issuer
            self._keys, self._keys_at = {}, float('-inf')
        return conf

    def key(self, conf, kid):
        with self._lock:
            age = time.monotonic() - self._keys_at
            if age > self.max_age or (kid not in self._keys and age > self.gap):
                self._keys_at = time.monotonic()
                try:
                    found = self._fetch(conf['jwks_uri']).get('keys') or []
                except (OSError, ValueError, AttributeError) as e:
                    log.warning('cannot fetch the sign-in keys: %s', e)
                    found = None
                if found is not None:
                    keys = {}
                    for k in found:
                        if isinstance(k, dict) and k.get('kty') == 'RSA' and k.get('kid'):
                            try:
                                keys[k['kid']] = jwt.PyJWK(k, 'RS256').key
                            except jwt.PyJWTError:
                                continue
                    self._keys = keys
            key = self._keys.get(kid)
        if key is None:
            raise SignInError('unknown signing key')
        return key

    def exchange(self, conf, client_id, client_secret, code, verifier, redirect_uri):
        """The code for an ID token at the token endpoint (client secret by HTTP Basic unless only POST is offered)."""
        form = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'code_verifier': verifier,
            'client_id': client_id,
        }
        headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
        methods = conf.get('token_endpoint_auth_methods_supported') or ['client_secret_basic']
        if 'client_secret_basic' in methods:
            pair = f'{urllib.parse.quote(client_id, safe="")}:{urllib.parse.quote(client_secret, safe="")}'
            headers['Authorization'] = 'Basic ' + base64.b64encode(pair.encode()).decode()
        else:
            form['client_secret'] = client_secret
        try:
            reply = self._post(conf['token_endpoint'], form, headers)
        except (OSError, ValueError) as e:
            raise SignInError(f'token endpoint unreachable: {e}') from None
        token = (reply or {}).get('id_token') if isinstance(reply, dict) else None
        if not token:
            raise SignInError('no ID token in the answer')
        return token

    def verify(self, conf, client_id, token, nonce):
        """The lowercased email in a valid ID token for this application and sign-in, or SignInError."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise SignInError('malformed ID token') from e
        if header.get('alg') != 'RS256':
            raise SignInError('wrong algorithm')
        key = self.key(conf, header.get('kid'))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=client_id,
                issuer=conf['issuer'],
                leeway=LEEWAY,
                options={'require': ['exp', 'iat', 'iss', 'aud', 'nonce']},
            )
        except jwt.PyJWTError as e:
            raise SignInError(type(e).__name__) from e
        if not hmac.compare_digest(str(claims.get('nonce')), nonce):
            raise SignInError('wrong nonce')
        aud = claims.get('aud')
        if isinstance(aud, list) and len(aud) > 1 and claims.get('azp') != client_id:
            raise SignInError('token issued to another client')
        email = claims.get('email')
        if not isinstance(email, str) or '@' not in email:
            raise SignInError('no email in the ID token')
        return email.strip().lower()


class SignIn:
    def __init__(self, folder, provider=None):
        self.secrets = Secrets(folder)
        self.provider = provider or Provider()

    def _fernet(self, label):
        return Fernet(base64.urlsafe_b64encode(derive(key_bytes(self.secrets.get('key')), label)))

    def ready(self):
        return self.secrets.ready()

    def live(self):
        return self.ready() and self.secrets.live()

    def proof(self, user, admin, agent):
        key = self.secrets.get('key')
        return proof(key_bytes(key), user, admin, agent) if key else ''

    # ---- cookies
    def _seal(self, label, data):
        return self._fernet(label).encrypt(json.dumps(data, separators=(',', ':')).encode()).decode()

    def _open(self, label, value, ttl):
        if not value or not self.secrets.get('key'):
            return None
        try:
            data = json.loads(self._fernet(label).decrypt(value.encode(), ttl=ttl))
        except (InvalidToken, ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def session_cookie(self, email, host, now=None):
        exp = int(now if now is not None else time.time()) + SESSION_TTL
        value = self._seal('agentlab session v1', {'e': email, 'h': host, 'x': exp})
        return f'{SESSION}={value}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; Secure; SameSite=Lax'

    def session_email(self, value, host):
        """The person a session cookie names, if it is ours, for this host and not expired; else ''."""
        data = self._open('agentlab session v1', value, SESSION_TTL)
        if not data or data.get('h') != host or not isinstance(data.get('x'), int) or data['x'] < time.time():
            return ''
        email = data.get('e')
        return email if isinstance(email, str) and '@' in email else ''

    # ---- the flow
    def start(self, team, host, nxt):
        """(authorization URL, Set-Cookie for the pending sign-in)."""
        conf = self.provider.config(team, self.secrets.get('client_id'))
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        pending = self._seal('agentlab pending v1', {'s': state, 'n': nonce, 'v': verifier, 'r': nxt, 'h': host})
        query = urllib.parse.urlencode(
            {
                'response_type': 'code',
                'client_id': self.secrets.get('client_id'),
                'redirect_uri': f'https://{host}{CALLBACK}',
                'scope': 'openid email profile',
                'state': state,
                'nonce': nonce,
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
            }
        )
        cookie = f'{PENDING}={pending}; Path=/; Max-Age={PENDING_TTL}; HttpOnly; Secure; SameSite=Lax'
        return f'{conf["authorization_endpoint"]}?{query}', cookie

    def finish(self, team, host, query, pending_value):
        """(email, where to go next) for the callback's query string, or SignInError."""
        q = urllib.parse.parse_qs(query)
        pending = self._open('agentlab pending v1', pending_value, PENDING_TTL)
        if not pending or pending.get('h') != host:
            raise SignInError('no sign-in in progress (or it took too long)')
        state = (q.get('state') or [''])[0]
        if not hmac.compare_digest(state, str(pending.get('s', ''))):
            raise SignInError('wrong state')
        if q.get('error'):
            raise SignInError(f'Access said: {q["error"][0]}')
        code = (q.get('code') or [''])[0]
        if not code:
            raise SignInError('no code')
        client_id = self.secrets.get('client_id')
        conf = self.provider.config(team, client_id)
        token = self.provider.exchange(
            conf, client_id, self.secrets.get('client_secret'), code, pending['v'], f'https://{host}{CALLBACK}'
        )
        return self.provider.verify(conf, client_id, token, pending['n']), pending.get('r') or '/'


def cleared(name):
    return f'{name}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax'
