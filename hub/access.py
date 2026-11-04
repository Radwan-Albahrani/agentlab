"""Who is asking: the edge's X-Agentlab-User, backed by the Access JWT or the gate's HMAC proof (X-Agentlab-Proof)."""

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.request

import cluster
import scope

CERTS_URL = os.environ.get('HUB_ACCESS_CERTS_URL', 'https://{team}.cloudflareaccess.com/cdn-cgi/access/certs')
GATE_KEY = os.environ.get('HUB_GATE_KEY', '/secrets/gate/session.key')
KEYS_FOR = 3600  # s before the team's keys are fetched again
LEEWAY = 60  # s of clock difference allowed on exp / nbf
MODES = ('cloudflare-access', 'tailscale', 'tinyauth')
SHA256_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')  # DER DigestInfo header for SHA-256
_keys = {'team': None, 'at': 0.0, 'keys': {}}
_lock = threading.Lock()


class DeniedError(Exception):
    pass


def _b64(part):
    return base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))


def _int(part):
    return int.from_bytes(_b64(part), 'big')


def _fetch(team):
    with urllib.request.urlopen(CERTS_URL.format(team=team), timeout=10) as r:
        jwks = json.loads(r.read())
    return {k['kid']: (_int(k['n']), _int(k['e'])) for k in jwks.get('keys') or [] if k.get('kty') == 'RSA'}


def _key(team, kid):
    with _lock:
        stale = _keys['team'] != team or time.time() - _keys['at'] > KEYS_FOR
        if stale or kid not in _keys['keys']:
            if not stale and time.time() - _keys['at'] < 30:  # unknown kid right after a fetch: don't hammer
                raise DeniedError('unknown signing key')
            _keys.update(team=team, at=time.time(), keys=_fetch(team))
        if kid not in _keys['keys']:
            raise DeniedError('unknown signing key')
        return _keys['keys'][kid]


def rsa_ok(signed, signature, n, e):
    """RSASSA-PKCS1-v1_5 with SHA-256."""
    size = (n.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    em = pow(int.from_bytes(signature, 'big'), e, n).to_bytes(size, 'big')
    t = SHA256_PREFIX + hashlib.sha256(signed).digest()
    want = b'\x00\x01' + b'\xff' * (size - len(t) - 3) + b'\x00' + t
    return hmac.compare_digest(em, want)


def verify(token, team, audience, now=None):
    """The token's claims if it is a valid Access token for this application, else raises DeniedError."""
    now = time.time() if now is None else now
    try:
        head_b64, body_b64, sig_b64 = token.split('.')
        head, claims = json.loads(_b64(head_b64)), json.loads(_b64(body_b64))
        signature = _b64(sig_b64)
    except (ValueError, AttributeError) as e:
        raise DeniedError('malformed token') from e
    if head.get('alg') != 'RS256':
        raise DeniedError('wrong algorithm')
    n, e = _key(team, head.get('kid'))
    if not rsa_ok(f'{head_b64}.{body_b64}'.encode(), signature, n, e):
        raise DeniedError('bad signature')
    aud = claims.get('aud')
    if audience not in (aud if isinstance(aud, list) else [aud]):
        raise DeniedError('wrong audience')
    if claims.get('iss') != f'https://{team}.cloudflareaccess.com':
        raise DeniedError('wrong issuer')
    if not isinstance(claims.get('exp'), int | float) or claims['exp'] < now - LEEWAY:
        raise DeniedError('expired')
    if isinstance(claims.get('nbf'), int | float) and claims['nbf'] > now + LEEWAY:
        raise DeniedError('not valid yet')
    if not claims.get('email'):
        raise DeniedError('no email')
    return claims


def _gate_key():
    try:
        with open(GATE_KEY, encoding='utf-8') as f:
            text = f.read().strip()
    except OSError:
        return b''
    try:
        return bytes.fromhex(text)
    except ValueError:
        return text.encode()


def proof_ok(headers, user, now=None):
    """Whether X-Agentlab-Proof is the gate's signature over this answer (gate/gate/oidc.py proof())."""
    exp, _, mac = (headers.get('X-Agentlab-Proof') or '').partition('.')
    key = _gate_key()
    if not key or not exp.isdigit() or int(exp) < (time.time() if now is None else now):
        return False
    admin, agent = headers.get('X-Agentlab-Admin') or '', headers.get('X-Agentlab-Agent') or ''
    msg = f'{user}\n{admin}\n{agent}\n{exp}'
    sub = hmac.new(key, b'agentlab proof v1', hashlib.sha256).digest()
    want = base64.urlsafe_b64encode(hmac.new(sub, msg.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
    return hmac.compare_digest(mac, want)


def token_of(headers):
    token = headers.get('Cf-Access-Jwt-Assertion')
    if token:
        return token
    for part in (headers.get('Cookie') or '').split(';'):
        name, _, value = part.strip().partition('=')
        if name == 'CF_Authorization':
            return value
    return ''


def viewer(headers):
    """Who is asking (scope.Viewer), or raises DeniedError; the edge strips client copies of X-Agentlab-User."""
    conf = cluster.auth()
    mode = conf.get('mode')
    user = (headers.get('X-Agentlab-User') or '').strip().lower()
    published = os.environ.get('HUB_PUBLISHED_OWNER', '').strip().lower()
    if not user and published:
        # Hub on a host port (one-person cluster): no edge, so no identity headers; agentctl sets this only then.
        return scope.of(published, admin=True)
    if mode == 'none':
        if os.environ.get('HUB_ALLOW_NONE') != '1':
            raise DeniedError('auth.mode is "none" but HUB_ALLOW_NONE is not set')
        return scope.of(user) if user else scope.ADMIN
    if mode not in MODES:
        raise DeniedError('sign-in is not configured')
    if not user:
        raise DeniedError('not signed in')
    if mode == 'cloudflare-access':
        cf = conf.get('cloudflare') or {}
        if cf.get('https') is True and proof_ok(headers, user):
            pass  # gate-signed HTTPS sign-in: carries no Access JWT
        elif not cf.get('team') or not cf.get('audience'):
            raise DeniedError('Cloudflare Access is not configured')
        else:
            claims = verify(token_of(headers), cf['team'], cf['audience'])
            if str(claims['email']).lower() != user:
                raise DeniedError('the sign-in does not match')
    who = scope.of(user)
    if not who.admin and not who.agents:
        raise DeniedError(f'{user} has no agent here')
    return who
