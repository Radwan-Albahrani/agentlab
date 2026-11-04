"""Cloudflare Access JWT checks; RS256 only, since `none` or HS* would let anyone forge a token."""

import json
import logging
import threading
import time
import urllib.request

import jwt

log = logging.getLogger('gate')
LEEWAY = 30  # seconds of clock skew allowed on exp / nbf / iat


class TokenError(Exception):
    pass


def fetch_keys(team):
    url = f'https://{team}.cloudflareaccess.com/cdn-cgi/access/certs'
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)['keys']


class Keys:
    """Cached signing keys; an unknown kid refetches at most once per `gap` s so junk tokens can't hammer Cloudflare."""

    max_age = 3600

    def __init__(self, fetch=fetch_keys, gap=30):
        self._fetch = fetch
        self.gap = gap
        self._lock = threading.Lock()
        self._team = None
        self._keys = {}
        self._at = float('-inf')

    def get(self, team, kid):
        with self._lock:
            age = time.monotonic() - self._at
            if team != self._team or age > self.max_age or (kid not in self._keys and age > self.gap):
                self._load(team)
            key = self._keys.get(kid)
        if key is None:
            raise TokenError('unknown signing key')
        return key

    def _load(self, team):
        self._at = time.monotonic()
        if team != self._team:
            self._team, self._keys = team, {}
        try:
            found = self._fetch(team)
        except (OSError, ValueError, KeyError) as e:
            log.warning('cannot fetch Access keys for %s: %s', team, e)
            return
        keys = {}
        for k in found:
            if isinstance(k, dict) and k.get('kty') == 'RSA' and k.get('kid'):
                try:
                    keys[k['kid']] = jwt.PyJWK(k, 'RS256').key
                except jwt.PyJWTError as e:
                    log.warning('skipping Access key %s: %s', k.get('kid'), e)
        self._keys = keys


def email_of(token, team, audience, keys):
    if not token:
        raise TokenError('no token')
    if not team or not audience:
        raise TokenError('auth.cloudflare.team / audience not configured')
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise TokenError('malformed token') from e
    if header.get('alg') != 'RS256':
        raise TokenError('wrong algorithm')
    key = keys.get(team, header.get('kid'))
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=audience,
            issuer=f'https://{team}.cloudflareaccess.com',
            leeway=LEEWAY,
            options={'require': ['exp', 'iat', 'iss', 'aud']},
        )
    except jwt.PyJWTError as e:
        raise TokenError(type(e).__name__) from e
    email = claims.get('email')
    if not isinstance(email, str) or '@' not in email:
        raise TokenError('no email in token')  # e.g. an Access service token
    return email.strip().lower()
