"""Private HTTPS sign-in end to end over real HTTP: the gate's /verify against a fake Access for SaaS OIDC provider
(discovery, keys, token endpoint with PKCE). The browser is played by following the gate's redirects by hand."""

import base64
import hashlib
import hmac
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from gate.oidc import PENDING, SESSION, Provider, SignIn

from .test_gate import DOMAIN, HUB, JWK1, KEY1, KEY2, TEAM, Base, NoRedirect, cluster, token

CLIENT, SECRET = 'cid-123', 'shh'
ISSUER = f'https://{TEAM}.cloudflareaccess.com/cdn-cgi/access/sso/oidc/{CLIENT}'


class Oidc(Base):
    def setUp(self):
        super().setUp()
        data = cluster()
        data['auth']['cloudflare'].update(https=True, network='private')
        self.write(data)
        self.folder = os.path.join(self.dir, 'gate-secrets')
        os.makedirs(self.folder)
        for name, value in (('oidc-client-id', CLIENT), ('oidc-client-secret', SECRET), ('session.key', 'ab' * 32)):
            with open(os.path.join(self.folder, name), 'w') as f:
                f.write(value)
        self.discovery = {
            'issuer': ISSUER,
            'authorization_endpoint': f'{ISSUER}/authorization',
            'token_endpoint': f'{ISSUER}/token',
            'jwks_uri': f'{ISSUER}/jwks',
            'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post'],
        }
        self.codes = {}  # code -> what the provider remembers from the authorization request
        self.claims = {}  # overrides for the next ID token
        self.signing = (KEY1, 'k1')
        self.server.signin = SignIn(self.folder, Provider(fetch=self.idp_get, post=self.idp_post, gap=0))

    # ---- the provider
    def idp_get(self, url):
        if url == f'{ISSUER}/.well-known/openid-configuration':
            return dict(self.discovery)
        if url == f'{ISSUER}/jwks':
            return {'keys': [JWK1]}
        raise OSError(f'unexpected {url}')

    def idp_post(self, url, form, headers):
        assert url == f'{ISSUER}/token', url
        basic = base64.b64decode(headers['Authorization'].removeprefix('Basic ')).decode()
        if basic != f'{CLIENT}:{SECRET}':
            raise OSError('bad client')
        asked = self.codes.pop(form['code'], None)
        if not asked or form['redirect_uri'] != asked['redirect_uri']:
            raise OSError('bad code')
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).rstrip(b'=')
        if challenge.decode() != asked['code_challenge']:
            raise OSError('PKCE verifier does not match')
        now = int(time.time())
        claims = {
            'iss': ISSUER,
            'aud': CLIENT,
            'sub': 'u1',
            'email': asked['email'],
            'nonce': asked['nonce'],
            'iat': now,
            'exp': now + 300,
        }
        claims.update(self.claims)
        claims = {k: v for k, v in claims.items() if v is not None}
        key, kid = self.signing
        return {'id_token': jwt.encode(claims, key, algorithm='RS256', headers={'kid': kid})}

    def authorize(self, location, email='sara@example.com'):
        """Access signs the person in and sends the browser back with a code."""
        url = urllib.parse.urlsplit(location)
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}', f'{ISSUER}/authorization')
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        self.assertEqual((q['response_type'], q['client_id'], q['code_challenge_method']), ('code', CLIENT, 'S256'))
        self.assertEqual(q['scope'], 'openid email profile')
        code = f'code{len(self.codes)}'
        self.codes[code] = {**q, 'email': email}
        return f'/_agentlab/oidc/callback?code={code}&state={q["state"]}'

    # ---- the browser
    def call(self, uri, cookies=None, host=DOMAIN, proto='https', navigate=True):
        headers = {'X-Forwarded-Host': host, 'X-Forwarded-Uri': uri, 'X-Forwarded-Proto': proto}
        if navigate:
            headers.update({'Sec-Fetch-Mode': 'navigate', 'Accept': 'text/html'})
        if cookies:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/verify', headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as r:
                return r.status, r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.headers

    @staticmethod
    def jar(headers):
        out = {}
        for line in headers.get_all('Set-Cookie') or []:
            name, _, rest = line.partition('=')
            out[name] = rest.split(';')[0]
        return out

    def sign_in(self, start='/somewhere?x=1', email='sara@example.com', host=DOMAIN):
        status, headers = self.call(start, host=host)
        self.assertEqual(status, 302)
        pending = self.jar(headers)
        callback = self.authorize(headers['Location'], email)
        return self.call(callback, pending, host=host), pending

    def session(self, **kw):
        (status, headers), _ = self.sign_in(**kw)
        self.assertEqual(status, 302, headers)
        return self.jar(headers)[SESSION]

    # ---- the tests
    def test_full_sign_in(self):
        (status, headers), _ = self.sign_in()
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], '/somewhere?x=1')
        cookies = headers.get_all('Set-Cookie')
        session = next(c for c in cookies if c.startswith(SESSION))
        for flag in ('HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/'):
            self.assertIn(flag, session)
        self.assertIn(f'{PENDING}=;', ' '.join(cookies))  # the pending sign-in is cleared
        status, headers = self.call('/', {SESSION: self.jar(headers)[SESSION]})
        self.assertEqual(status, 200)
        self.assertEqual((headers['X-Agentlab-User'], headers['X-Agentlab-Agent']), ('sara@example.com', 'sara'))
        # the hub's check of the gate's answer (hub/access.py proof_ok)
        exp, _, mac = headers['X-Agentlab-Proof'].partition('.')
        sub = hmac.new(bytes.fromhex('ab' * 32), b'agentlab proof v1', hashlib.sha256).digest()
        msg = f'sara@example.com\n0\nsara\n{exp}'.encode()
        want = base64.urlsafe_b64encode(hmac.new(sub, msg, hashlib.sha256).digest()).rstrip(b'=').decode()
        self.assertEqual(mac, want)

    def test_scripts_get_401_not_a_redirect(self):
        self.assertEqual(self.call('/api/x', navigate=False)[0], 401)
        status, headers = self.call('/', navigate=False)
        self.assertEqual(status, 401)
        self.assertIsNone(headers.get('Set-Cookie'))

    def test_wrong_state_is_refused(self):
        _, headers = self.call('/')
        pending = self.jar(headers)
        callback = self.authorize(headers['Location'])
        forged = callback.replace('state=', 'state=x')
        self.assertEqual(self.call(forged, pending)[0], 403)
        self.assertEqual(self.call(callback, {})[0], 403)  # no pending sign-in at all (another browser)

    def test_a_pending_sign_in_belongs_to_its_host(self):
        _, headers = self.call('/', host=HUB)
        callback = self.authorize(headers['Location'])
        self.assertEqual(self.call(callback, self.jar(headers), host=DOMAIN)[0], 403)

    def test_wrong_nonce_is_refused(self):
        self.claims = {'nonce': 'replayed'}
        (status, _), _ = self.sign_in()
        self.assertEqual(status, 403)

    def test_tampered_expired_or_foreign_tokens_are_refused(self):
        for claims, signing in (
            ({}, (KEY2, 'k1')),  # signed with another key under the known id
            ({}, (KEY2, 'k2')),  # a key the provider never published
            ({'exp': int(time.time()) - 600}, (KEY1, 'k1')),
            ({'aud': 'someone-else'}, (KEY1, 'k1')),
            ({'iss': f'https://{TEAM}.cloudflareaccess.com'}, (KEY1, 'k1')),  # the self-hosted issuer, not this app's
            ({'email': None}, (KEY1, 'k1')),
            ({'nonce': None}, (KEY1, 'k1')),
        ):
            self.claims, self.signing = claims, signing
            (status, _), _ = self.sign_in()
            self.assertEqual(status, 403, claims)

    def test_forged_cookies_get_nothing(self):
        good = self.session()
        bad = good[:-6] + ('AAAAAA' if not good.endswith('AAAAAA') else 'BBBBBB')
        for value in (bad, 'x', '', base64.urlsafe_b64encode(b'{"e":"sara@example.com"}').decode()):
            self.assertEqual(self.call('/', {SESSION: value}, navigate=False)[0], 401, value)
        # a session for one host is not one for the other
        self.assertEqual(self.call('/', {SESSION: good}, host=HUB, navigate=False)[0], 401)
        # nor a cookie sealed with another cluster's key
        other = SignIn(self.folder)
        with open(os.path.join(self.folder, 'session.key'), 'w') as f:
            f.write('cd' * 32)
        sealed = other.session_cookie('sara@example.com', DOMAIN).split(';')[0].split('=', 1)[1]
        with open(os.path.join(self.folder, 'session.key'), 'w') as f:
            f.write('ab' * 32)
        os.utime(os.path.join(self.folder, 'session.key'), (time.time() + 5, time.time() + 5))
        self.assertEqual(self.call('/', {SESSION: sealed}, navigate=False)[0], 401)

    def test_an_expired_session_signs_in_again(self):
        signin = self.server.signin
        old = signin.session_cookie('sara@example.com', DOMAIN, now=time.time() - 13 * 3600)
        status, headers = self.call('/', {SESSION: old.split(';')[0].split('=', 1)[1]})
        self.assertEqual(status, 302)
        self.assertTrue(headers['Location'].startswith(f'{ISSUER}/authorization'))

    def test_logout_clears_the_session_and_ends_access(self):
        status, headers = self.call('/_agentlab/oidc/logout', {SESSION: self.session()})
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], f'https://{TEAM}.cloudflareaccess.com/cdn-cgi/access/logout')
        self.assertIn(f'{SESSION}=; Path=/; Max-Age=0', headers['Set-Cookie'])

    def test_no_open_redirect_after_sign_in(self):
        for start in ('//evil.com/x', '/\\evil.com'):
            (status, headers), _ = self.sign_in(start=start)
            self.assertEqual(status, 302)
            self.assertTrue(headers['Location'].startswith('/') and 'evil' not in headers['Location'], start)

    def test_a_provider_on_another_site_is_refused(self):
        self.discovery['token_endpoint'] = 'https://evil.example.com/token'
        self.assertEqual(self.call('/')[0], 503)
        self.discovery['token_endpoint'] = f'{ISSUER}/token'
        self.discovery['issuer'] = 'https://evil.example.com'
        self.server.signin.provider._conf_for = None  # forget the cached document
        self.assertEqual(self.call('/')[0], 503)

    def test_plain_http_keeps_accesss_token_until_live_then_redirects(self):
        status, headers = self.call('/x', proto='http', navigate=False)
        self.assertEqual(status, 403)  # no token: plain HTTP is still Access's
        headers = {'X-Forwarded-Host': DOMAIN, 'X-Forwarded-Uri': '/x', 'X-Forwarded-Proto': 'http'}
        self.assertEqual(self.http('/verify', {**headers, 'Cf-Access-Jwt-Assertion': token()})[0], 200)
        with open(os.path.join(self.folder, 'https-live'), 'w') as f:
            f.write('now')
        status, headers, _ = self.http('/verify', {**headers, 'Cf-Access-Jwt-Assertion': token()})
        self.assertEqual((status, headers['Location']), (308, f'https://{DOMAIN}/x'))

    def test_without_its_client_https_is_refused_not_opened(self):
        os.remove(os.path.join(self.folder, 'oidc-client-secret'))
        self.assertEqual(self.call('/')[0], 403)
