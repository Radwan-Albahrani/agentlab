"""The gate end to end over real HTTP. Pass 1 requests carry what the edge sends to /verify (X-Forwarded-Host/-Port/
-Uri plus the identity headers of the mode); pass 2 page requests carry pass 1's X-Agentlab-* answer. A test RSA key
stands in for Cloudflare's and a fake Accounts API answers the onboarding question."""

import base64
import hashlib
import hmac
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from gate.app import safe_next, serve
from gate.config import Config, host_of, port_of
from gate.onboarding import Onboarding
from gate.tokens import Keys

from gate import __main__ as gate_main
from gate import onboarding

TEAM, AUD = 'example', 'aud-tag-123'
ISS = f'https://{TEAM}.cloudflareaccess.com'
DOMAIN, HUB, COOLIFY = 'agents.example.com', 'agents-hub.example.com', 'agents-coolify.example.com'


def new_key(kid):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update(kid=kid, alg='RS256', use='sig')
    return priv, jwk


KEY1, JWK1 = new_key('k1')
KEY2, JWK2 = new_key('k2')


def cluster(owner='sara@example.com', mode='cloudflare-access', audience=AUD, domain=DOMAIN, hub=HUB):
    return {
        'name': 'example',
        'domain': domain,
        'hub_domain': hub,
        'coolify_domain': COOLIFY,
        'auth': {
            'mode': mode,
            'ingress': 'cloudflared',
            'admins': ['Admin@Example.com', 'boss@example.com'],
            'cloudflare': {'team': TEAM, 'audience': audience},
            'tinyauth': {'domain': ''},
            'hub_port': 8443,
        },
        'agents': [
            {'id': 'sara', 'owner': owner, 'upstream': 'http://agent-sara'},
            {'id': 'omar', 'owner': 'omar@example.com', 'upstream': 'http://agent-omar'},
            {'id': 'admin', 'owner': 'admin@example.com', 'upstream': 'http://agent-admin'},
        ],
    }


def token(email='sara@example.com', key=KEY1, kid='k1', **over):
    now = int(time.time())
    claims = {'email': email, 'aud': [AUD], 'iss': ISS, 'iat': now, 'nbf': now, 'exp': now + 600, 'sub': 'x'}
    claims.update(over)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm='RS256', headers={'kid': kid})


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def forged(alg, secret=b''):
    now = int(time.time())
    head = b64(json.dumps({'alg': alg, 'typ': 'JWT', 'kid': 'k1'}).encode())
    body = b64(
        json.dumps({'email': 'sara@example.com', 'aud': [AUD], 'iss': ISS, 'iat': now, 'exp': now + 600}).encode()
    )
    sig = b64(hmac.new(secret, f'{head}.{body}'.encode(), hashlib.sha256).digest()) if alg == 'HS256' else ''
    return f'{head}.{body}.{sig}'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Base(unittest.TestCase):
    mode = 'cloudflare-access'

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'cluster.json')
        self.writes = 0
        self.write(cluster(mode=self.mode))
        self.fetches = []
        self.jwks = [JWK1]
        self.done = {'sara': True, 'omar': True, 'admin': True}
        self.asked = []
        self.keys = Keys(fetch=self.fetch, gap=0)
        self.onboarding = Onboarding(fetch=self.ask)
        self.server = serve(Config(self.path), self.keys, self.onboarding, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir)

    def fetch(self, team):
        self.fetches.append(team)
        return list(self.jwks)

    def ask(self, upstream):
        agent = upstream.removeprefix('http://agent-')
        self.asked.append(agent)
        answer = self.done[agent]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def write(self, data, raw=None):
        with open(self.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(raw if raw is not None else json.dumps(data))
        self.writes += 1
        t = time.time() + self.writes * 10  # every write gets a new mtime, however fast the test runs
        os.utime(self.path, (t, t))

    def http(self, path, headers, method='GET'):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method=method)
        for k, v in headers.items():
            if v is not None:
                req.add_header(k, v)
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode()

    def verify(self, *, host=DOMAIN, port=None, uri='/', view=None, site=None, method='GET', **identity):
        """A pass 1 call. `identity` holds the mode's headers by name, e.g. tok=, said=, cookie=, login=, remote=."""
        headers = {
            'X-Forwarded-Host': host,
            'X-Forwarded-Port': port,
            'X-Forwarded-Uri': uri,
            'X-Agentlab-Site': site,
            **self.identity(**identity),
        }
        if view:
            headers['Cookie'] = '; '.join(c for c in (headers.get('Cookie'), f'agentlab_view={view}') if c)
        return self.http('/verify', headers, method)

    def identity(self, *, tok=None, said=None, cookie=None, login=None, remote=None, accept=None):
        if tok and said is None:
            said = jwt.decode(tok, options={'verify_signature': False}).get('email')
        return {
            'Cf-Access-Jwt-Assertion': tok,
            'Cf-Access-Authenticated-User-Email': said,
            'Cookie': cookie,
            'Tailscale-User-Login': login,
            'Remote-Email': remote,
            'Accept': accept,
        }

    def page(
        self,
        path='/_agentlab/',
        *,
        user='sara@example.com',
        agent='sara',
        admin='0',
        host=DOMAIN,
        site=None,
        method='GET',
    ):
        """A pass 2 call, as the edge forwards it with pass 1's answer."""
        headers = {
            'Host': host,
            'X-Agentlab-User': user,
            'X-Agentlab-Agent': agent,
            'X-Agentlab-Admin': admin,
            'X-Agentlab-Site': site,
        }
        return self.http(path, headers, method)

    def agent_of(self, result):
        status, headers, _ = result
        self.assertEqual(status, 200, result)
        return headers['X-Agentlab-Agent']


# ---------------------------------------------------------------- pass 1: cloudflare-access
class Cloudflare(Base):
    def test_owner_gets_own_agent(self):
        status, headers, _ = self.verify(tok=token())
        self.assertEqual(status, 200)
        self.assertEqual(headers['X-Agentlab-User'], 'sara@example.com')
        self.assertEqual(headers['X-Agentlab-Admin'], '0')
        self.assertEqual(headers['X-Agentlab-Agent'], 'sara')

    def test_each_person_gets_their_own(self):
        self.assertEqual(self.agent_of(self.verify(tok=token('omar@example.com'))), 'omar')

    def test_a_cloudflare_one_client_session_token_works_the_same(self):
        # Signed in through the client session (private network / allow_authenticate_via_warp): the token carries the
        # same email plus device claims; only the signed email decides who it is
        tok = token(device_id='3f1c-device', identity_nonce='n0nce', type='app', country='SA', warp=True)
        status, headers, _ = self.verify(tok=tok)
        self.assertEqual(
            (status, headers['X-Agentlab-User'], headers['X-Agentlab-Agent']), (200, 'sara@example.com', 'sara')
        )

    def test_no_agent_gets_gate(self):
        self.assertEqual(self.agent_of(self.verify(tok=token('new@example.com'))), 'gate')

    def test_admin_view_cookie(self):
        _, headers, _ = self.verify(tok=token('admin@example.com'), view='sara')
        self.assertEqual(headers['X-Agentlab-Admin'], '1')
        self.assertEqual(headers['X-Agentlab-Agent'], 'sara')
        self.assertEqual(self.agent_of(self.verify(tok=token('admin@example.com'))), 'admin')
        self.assertEqual(self.agent_of(self.verify(tok=token('admin@example.com'), view='ghost')), 'admin')
        self.assertEqual(self.agent_of(self.verify(tok=token('boss@example.com'))), 'gate')

    def test_view_cookie_ignored_for_non_admin(self):
        self.assertEqual(self.agent_of(self.verify(tok=token(), view='omar')), 'sara')

    def test_email_header_must_match_token(self):
        self.assertEqual(self.verify(tok=token('omar@example.com'), said='sara@example.com')[0], 403)
        self.assertEqual(self.agent_of(self.verify(tok=token(), said='SARA@example.com')), 'sara')
        self.assertEqual(self.agent_of(self.verify(tok=token('Sara@Example.com'))), 'sara')

    def test_hub_for_agent_owners_and_admins(self):
        self.assertEqual(self.agent_of(self.verify(host=HUB, tok=token())), 'sara')
        self.assertEqual(self.verify(host=HUB, tok=token('new@example.com'))[0], 403)
        self.assertEqual(self.agent_of(self.verify(host=HUB, tok=token('boss@example.com'))), 'none')

    def test_coolify_admins_only(self):
        self.assertEqual(self.verify(host=COOLIFY, tok=token())[0], 403)
        status, headers, _ = self.verify(host=COOLIFY, tok=token('admin@example.com'))
        self.assertEqual((status, headers['X-Agentlab-Admin']), (200, '1'))

    def test_unknown_host_denied_even_for_admin(self):
        self.assertEqual(self.verify(host='evil.example.com', tok=token('admin@example.com'))[0], 403)
        self.assertEqual(self.verify(host='', tok=token('admin@example.com'))[0], 403)

    def test_mixed_case_host_and_port_normalized(self):
        self.assertEqual(self.agent_of(self.verify(host='AGENTS.Example.COM:443', tok=token())), 'sara')
        self.assertEqual(self.verify(host='Agents-COOLIFY.example.com', tok=token())[0], 403)
        self.assertEqual(host_of('Agents.Example.com.'), 'agents.example.com')
        self.assertEqual(port_of('a.example.com:8443', ''), '8443')
        self.assertEqual(port_of('a.example.com', '443'), '443')
        self.assertEqual(port_of('[::1]:9', ''), '9')

    def test_wrong_audience(self):
        self.assertEqual(self.verify(tok=token(aud=['other']))[0], 403)

    def test_wrong_issuer(self):
        self.assertEqual(self.verify(tok=token(iss='https://evil.cloudflareaccess.com'))[0], 403)

    def test_expired(self):
        old = int(time.time()) - 3600
        self.assertEqual(self.verify(tok=token(iat=old - 600, nbf=old - 600, exp=old))[0], 403)

    def test_missing_exp_refused(self):
        self.assertEqual(self.verify(tok=token(exp=None))[0], 403)

    def test_alg_none(self):
        self.assertEqual(self.verify(tok=forged('none'))[0], 403)

    def test_hs256_key_confusion(self):
        pem = KEY1.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.assertEqual(self.verify(tok=forged('HS256', pem))[0], 403)

    def test_signed_by_another_key(self):
        self.assertEqual(self.verify(tok=token(key=KEY2, kid='k1'))[0], 403)

    def test_no_email_claim(self):
        self.assertEqual(self.verify(tok=token(email=None), said='sara@example.com')[0], 403)

    def test_missing_token(self):
        status, _, body = self.verify(said='sara@example.com', accept='text/html')
        self.assertEqual(status, 403)
        self.assertIn('<html', body)

    def test_other_modes_headers_mean_nothing_here(self):
        self.assertEqual(self.verify(login='sara@example.com', remote='sara@example.com')[0], 403)

    def test_cookie_fallback(self):
        self.assertEqual(
            self.agent_of(self.verify(cookie=f'other=1; CF_Authorization={token()}', said='sara@example.com')), 'sara'
        )

    def test_unknown_kid_triggers_refetch(self):
        self.assertEqual(self.verify(tok=token())[0], 200)
        self.jwks = [JWK1, JWK2]
        self.assertEqual(self.verify(tok=token(key=KEY2, kid='k2'))[0], 200)
        self.assertEqual(len(self.fetches), 2)

    def test_unknown_kid_refetch_rate_limited(self):
        self.keys.gap = 3600
        self.assertEqual(self.verify(tok=token())[0], 200)
        for _ in range(5):
            self.assertEqual(self.verify(tok=token(key=KEY2, kid='k2'))[0], 403)
        self.assertEqual(len(self.fetches), 1)

    def test_config_reload(self):
        self.assertEqual(self.agent_of(self.verify(tok=token())), 'sara')
        self.write(cluster(owner='new@example.com'))
        self.assertEqual(self.agent_of(self.verify(tok=token())), 'gate')
        self.assertEqual(self.agent_of(self.verify(tok=token('new@example.com'))), 'sara')

    def test_broken_config_keeps_last_good(self):
        self.assertEqual(self.verify(tok=token())[0], 200)
        self.write(None, raw='{not json')
        self.assertEqual(self.agent_of(self.verify(tok=token())), 'sara')

    def test_unconfigured_audience_denies(self):
        self.write(cluster(audience=''))
        self.assertEqual(self.verify(tok=token())[0], 403)

    def test_verify_any_method(self):
        self.assertEqual(self.verify(tok=token(), method='POST')[0], 200)


# ---------------------------------------------------------------- the edge's X-Agentlab-Site stamp
class Site(Base):
    def test_site_decides_over_host(self):
        self.assertEqual(self.agent_of(self.verify(site='agent', tok=token())), 'sara')
        self.assertEqual(self.agent_of(self.verify(host=HUB, site='agent', tok=token())), 'sara')
        self.assertEqual(self.verify(host=DOMAIN, site='hub', tok=token('new@example.com'))[0], 403)
        self.assertEqual(self.verify(host=DOMAIN, site='coolify', tok=token())[0], 403)
        self.assertEqual(self.verify(host=DOMAIN, site='Coolify', tok=token('admin@example.com'))[0], 200)

    def test_unknown_or_empty_site_refused(self):
        for site in ('pair', 'gate', '', 'agents'):
            self.assertEqual(self.verify(site=site, tok=token('admin@example.com'))[0], 403, site)

    def test_host_must_still_be_ours(self):
        self.assertEqual(self.verify(host='evil.example.com', site='agent', tok=token('admin@example.com'))[0], 403)

    def test_coolify_site_needs_coolify_domain(self):
        data = cluster()
        data['coolify_domain'] = ''
        self.write(data)
        self.assertEqual(self.verify(site='coolify', tok=token('admin@example.com'))[0], 403)

    def test_email_header_check_follows_site(self):
        # On the agent site Cloudflare's email header must match the token, whatever the host says.
        self.assertEqual(
            self.verify(host=HUB, site='agent', tok=token('omar@example.com'), said='sara@example.com')[0], 403
        )

    def test_pages_need_agent_site(self):
        self.assertEqual(self.page(site='agent')[0], 200)
        self.assertEqual(self.page(site='hub')[0], 403)
        self.assertEqual(self.page(host=HUB, site='agent')[0], 200)


# ---------------------------------------------------------------- pass 1: other modes
class Tailscale(Base):
    mode = 'tailscale'

    def setUp(self):
        super().setUp()
        self.write(cluster(mode='tailscale', domain='box.tail1234.ts.net', hub=''))

    def test_login_header_is_identity(self):
        self.assertEqual(self.agent_of(self.verify(host='box.tail1234.ts.net', login='Sara@Example.com')), 'sara')

    def test_login_header_required(self):
        self.assertEqual(self.verify(host='box.tail1234.ts.net')[0], 403)
        self.assertEqual(self.verify(host='box.tail1234.ts.net', tok=token())[0], 403)

    def test_site_header_on_one_name(self):
        host = 'box.tail1234.ts.net'
        self.assertEqual(self.agent_of(self.verify(host=host, site='hub', login='sara@example.com')), 'sara')
        self.assertEqual(self.verify(host=host, site='hub', login='new@example.com')[0], 403)
        self.assertEqual(
            self.agent_of(self.verify(host=host, port='8443', site='agent', login='new@example.com')), 'gate'
        )

    def test_hub_is_same_name_on_hub_port(self):
        self.assertEqual(
            self.agent_of(self.verify(host='box.tail1234.ts.net', port='8443', login='sara@example.com')), 'sara'
        )
        self.assertEqual(self.verify(host='box.tail1234.ts.net:8443', login='new@example.com')[0], 403)
        self.assertEqual(
            self.agent_of(self.verify(host='box.tail1234.ts.net', port='443', login='new@example.com')), 'gate'
        )

    def test_onboarding_link_uses_hub_port(self):
        self.done['sara'] = False
        status, headers, _ = self.verify(host='box.tail1234.ts.net', login='sara@example.com')
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], 'https://box.tail1234.ts.net:8443/agents/sara/onboarding')


class Tinyauth(Base):
    mode = 'tinyauth'

    def test_remote_email_is_identity(self):
        self.assertEqual(self.agent_of(self.verify(remote='omar@example.com')), 'omar')

    def test_remote_email_required(self):
        self.assertEqual(self.verify(login='omar@example.com')[0], 403)
        self.assertEqual(self.verify(remote='not-an-email')[0], 403)


class ModeNone(Base):
    def setUp(self):
        super().setUp()
        self.write(cluster(mode='none'))

    def test_needs_env(self):
        with mock.patch.dict(os.environ, {'GATE_ALLOW_NONE': ''}):
            self.assertEqual(self.verify()[0], 403)
        with mock.patch.dict(os.environ, {'GATE_ALLOW_NONE': '1'}):
            status, headers, _ = self.verify(view='omar')
            self.assertEqual(self.verify(host='evil.example.com')[0], 403)
        self.assertEqual(status, 200)
        self.assertEqual(headers['X-Agentlab-User'], 'local@localhost')
        self.assertEqual(headers['X-Agentlab-Admin'], '1')
        self.assertEqual(headers['X-Agentlab-Agent'], 'omar')

    def test_refuses_to_start(self):
        with mock.patch.dict(os.environ, {'GATE_CONFIG': self.path, 'GATE_ALLOW_NONE': '0'}):
            self.assertEqual(gate_main.main(), 2)


# ---------------------------------------------------------------- onboarding
class Onboard(Base):
    def test_redirects_t3_paths_of_own_agent(self):
        self.done['sara'] = False
        status, headers, _ = self.verify(tok=token(), uri='/chat/42')
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], f'https://{HUB}/agents/sara/onboarding')

    def test_not_on_agentlab_paths(self):
        self.done['sara'] = False
        self.assertEqual(self.agent_of(self.verify(tok=token(), uri='/_agentlab/terminal/')), 'sara')
        self.assertEqual(self.agent_of(self.verify(tok=token(), uri='/_agentlab')), 'sara')

    def test_admin_viewing_someone_else_not_redirected(self):
        self.done['sara'] = False
        self.assertEqual(self.agent_of(self.verify(tok=token('admin@example.com'), view='sara')), 'sara')

    def test_not_on_hub(self):
        self.done['sara'] = False
        self.assertEqual(self.agent_of(self.verify(host=HUB, tok=token())), 'sara')

    def test_done_cached_forever(self):
        for _ in range(3):
            self.assertEqual(self.verify(tok=token())[0], 200)
        self.assertEqual(self.asked, ['sara'])

    def test_not_done_cached_briefly(self):
        self.done['sara'] = False
        self.assertEqual(self.verify(tok=token())[0], 302)
        self.done['sara'] = True
        self.assertEqual(self.verify(tok=token())[0], 302)  # still cached
        self.assertEqual(len(self.asked), 1)
        with mock.patch.object(onboarding, 'NOT_DONE_TTL', 0):
            self.assertEqual(self.verify(tok=token())[0], 200)
        self.assertEqual(len(self.asked), 2)

    def test_unreachable_agent_lets_through(self):
        self.done['sara'] = OSError('connection refused')
        self.assertEqual(self.agent_of(self.verify(tok=token())), 'sara')
        self.assertEqual(self.agent_of(self.verify(tok=token())), 'sara')
        self.assertEqual(len(self.asked), 2)  # errors aren't cached


# ---------------------------------------------------------------- several agents per person
class Several(Base):
    def setUp(self):
        super().setUp()
        data = cluster()
        data['agents'].append({'id': 'sara-lab', 'owner': 'sara@example.com', 'upstream': 'http://agent-sara-lab'})
        self.write(data)
        self.done['sara-lab'] = True

    def test_no_cookie_gets_picker(self):
        self.assertEqual(self.agent_of(self.verify(tok=token())), 'gate')

    def test_cookie_picks_own_second_agent(self):
        self.assertEqual(self.agent_of(self.verify(tok=token(), view='sara-lab')), 'sara-lab')
        self.assertEqual(self.agent_of(self.verify(tok=token(), view='sara')), 'sara')

    def test_cookie_for_someone_elses_agent_ignored(self):
        self.assertEqual(self.agent_of(self.verify(tok=token(), view='omar')), 'gate')

    def test_onboarding_applies_to_each_owned_agent(self):
        self.done['sara-lab'] = False
        status, headers, _ = self.verify(tok=token(), view='sara-lab')
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], f'https://{HUB}/agents/sara-lab/onboarding')

    def test_hub_allowed(self):
        self.assertEqual(self.verify(host=HUB, tok=token())[0], 200)

    def test_owner_may_switch_without_admin(self):
        status, headers, _ = self.page('/_agentlab/view/sara-lab', agent='gate')
        self.assertEqual(status, 303)
        self.assertTrue(headers['Set-Cookie'].startswith('agentlab_view=sara-lab;'))
        self.assertEqual(self.page('/_agentlab/view/omar', agent='gate')[0], 403)

    def test_picker_lists_own_agents_with_current_marked(self):
        _, _, body = self.page(agent='sara-lab')
        self.assertIn('/_agentlab/view/sara"', body)
        self.assertNotIn('/_agentlab/view/sara-lab"', body)
        self.assertIn('Current', body)
        self.assertNotIn('omar', body)

    def test_admin_picker_grouped_by_owner(self):
        _, _, body = self.page(user='boss@example.com', agent='gate', admin='1')
        self.assertIn('sara@example.com', body)
        self.assertIn('omar@example.com', body)
        self.assertIn('/_agentlab/view/sara-lab', body)


# ---------------------------------------------------------------- pass 2: pages
class Pages(Base):
    def test_need_pass1_headers(self):
        self.assertEqual(self.page(user=None)[0], 403)
        self.assertEqual(self.http('/_agentlab/', {'Host': DOMAIN})[0], 403)

    def test_menu_shows_own_tools(self):
        status, _, body = self.page()
        self.assertEqual(status, 200)
        self.assertIn(f'https://{HUB}/agents/sara', body)
        self.assertIn('/_agentlab/accounts/browser', body)
        self.assertIn('/_agentlab/terminal/', body)
        self.assertIn('/_agentlab/files/', body)
        self.assertNotIn('omar', body)
        self.assertNotIn('All agents', body)

    def test_menu_admin_sees_all_and_hub(self):
        _, _, body = self.page(user='admin@example.com', agent='admin', admin='1')
        self.assertIn('/_agentlab/view/omar', body)
        self.assertIn(f'https://{HUB}/', body)

    def test_menu_viewing_banner(self):
        _, _, body = self.page(user='admin@example.com', agent='omar', admin='1')
        self.assertIn('Stop viewing', body)

    def test_menu_onboarding_banner(self):
        self.done['sara'] = False
        _, _, body = self.page()
        self.assertIn(f'https://{HUB}/agents/sara/onboarding', body)

    def test_no_agent_page(self):
        status, _, body = self.page('/', user='new@example.com', agent='gate')
        self.assertEqual(status, 200)
        self.assertIn('have an agent yet', body)

    def test_only_on_main_domain(self):
        self.assertEqual(self.page(host=HUB, admin='1')[0], 403)

    def test_view_sets_cookie_for_admin(self):
        status, headers, _ = self.page('/_agentlab/view/omar?next=/chat/1', user='admin@example.com', admin='1')
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/chat/1')
        cookie = headers['Set-Cookie']
        self.assertTrue(cookie.startswith('agentlab_view=omar;'))
        for flag in ('Path=/', 'HttpOnly', 'SameSite=Lax', 'Secure'):
            self.assertIn(flag, cookie)

    def test_view_refused_for_non_admin_and_missing_agent(self):
        self.assertEqual(self.page('/_agentlab/view/omar')[0], 403)
        self.assertEqual(self.page('/_agentlab/view/ghost', user='admin@example.com', admin='1')[0], 403)

    def test_view_me_clears(self):
        status, headers, _ = self.page('/_agentlab/view/me')
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')
        self.assertIn('Max-Age=0', headers['Set-Cookie'])

    def test_open_redirect_guard(self):
        for bad in ('//evil.com', '/\\evil.com', 'https://evil.com', 'evil', '/a\\b', '/a\r\nX: y'):
            self.assertEqual(safe_next('next=' + urllib.parse.quote(bad)), '/', bad)
        self.assertEqual(safe_next('next=/x?y=1'), '/x?y=1')
        self.assertEqual(self.page('/_agentlab/view/me?next=//evil.com')[1]['Location'], '/')

    def test_get_only(self):
        self.assertEqual(self.page(method='POST')[0], 405)

    def test_health(self):
        self.assertEqual(self.http('/health', {})[0], 200)


if __name__ == '__main__':
    unittest.main()
