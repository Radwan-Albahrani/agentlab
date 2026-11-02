"""T3 pairing and paired devices. T3 answers only paired devices (bearer sessions), and a one-time pairing link
(`<base>/pair#token=...`) turns a browser or the T3 app into one. The token is redeemed by T3's own page on whatever
host the link names, so the link must use a host that device can reach:
  browser  the cluster domain (the person is signed in there already), 5 minutes
  app      the agent's pair host (cloudflare-access / tinyauth: Access bypass straight to T3), or the cluster domain on a
           tailnet (identity comes with the connection), 10 minutes; the hub draws the QR from `url`."""

import json
import os
import re

from util import run, sh_quote

TTL = {'browser': '5m', 'app': '10m'}
DEVICE_SUBJECT = 'one-time-token'  # sessions made by redeeming a pairing link (not the bridge's short tokens)
NO_DEVICE = 'No such device.'


def _host(kind):
    """(host, reason it isn't available)."""
    domain = os.environ.get('AGENTLAB_DOMAIN', '')
    if kind == 'browser' or os.environ.get('AGENTLAB_AUTH_MODE') == 'tailscale':
        return domain, '' if domain else 'AGENTLAB_DOMAIN is not set'
    host = os.environ.get('AGENTLAB_PAIR_HOST', '')
    reason = (
        ''
        if host
        else 'The T3 app needs its own address for this agent (pair_domain in cluster.toml), which this cluster '
        "doesn't have. Pair in a browser instead, or ask the admin to set it up."
    )
    return host, reason


def pair(kind, label):
    """A fresh pairing link -> {available, url, token, expires, id} or {available: False, reason}."""
    if kind not in TTL:
        raise ValueError('kind must be browser or app')
    host, reason = _host(kind)
    if not host:
        return {'available': False, 'reason': reason}
    label = re.sub(r'[^\w .@-]', '', label)[:40] or kind
    rc, out = run(
        f't3 auth pairing create --json --ttl {TTL[kind]} --label {sh_quote(label)} '
        f'--base-url {sh_quote("https://" + host)}',
        timeout=30,
    )
    try:
        made = json.loads(out[out.index('{') :]) if rc == 0 else {}
    except ValueError:
        made = {}
    token = made.get('token') or made.get('credential') or ''
    if not token:
        return {'available': False, 'reason': f'T3 could not make a pairing link: {out[-200:]}'}
    url = made.get('pairUrl') or made.get('url') or f'https://{host}/pair#token={token}'
    return {
        'available': True,
        'kind': kind,
        'url': url,
        'token': token,
        'expires': made.get('expiresAt', ''),
        'id': made.get('id', ''),
    }


def _sessions():
    rc, out = run('t3 auth session list --json', timeout=20)
    try:
        return json.loads(out) if rc == 0 else []
    except ValueError:
        return []


def devices():
    """Paired browsers and apps, newest first, without their tokens."""
    out = []
    for s in _sessions():
        if s.get('subject') != DEVICE_SUBJECT:
            continue
        client = s.get('client') or {}
        out.append(
            {
                'id': s.get('sessionId', ''),
                'label': client.get('label', ''),
                'ip': client.get('ipAddress', ''),
                'userAgent': client.get('userAgent', ''),
                'created': s.get('issuedAt') or s.get('createdAt', ''),
                'lastSeen': s.get('lastConnectedAt') or s.get('lastSeenAt', ''),
                'expires': s.get('expiresAt', ''),
                'connected': bool(s.get('connected')),
            }
        )
    return sorted(out, key=lambda d: d['created'] or '', reverse=True)


def revoke(session_id):
    """-> '' or why not. Only paired devices can be revoked here."""
    if session_id not in {d['id'] for d in devices()}:
        return NO_DEVICE
    rc, out = run(f't3 auth session revoke {sh_quote(session_id)}', timeout=20)
    return '' if rc == 0 else f'T3 refused: {out[-200:]}'
