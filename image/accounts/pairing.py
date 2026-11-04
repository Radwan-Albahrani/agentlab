"""T3 pairing links and paired devices; a link must name a host the pairing device can reach."""

import json
import os
import re

from util import published, run, sh_quote

TTL = {'browser': '5m', 'app': '10m'}
DEVICE_SUBJECT = 'one-time-token'  # sessions from redeemed pairing links
NO_DEVICE = 'No such device.'


def _published(host):
    """http://host:port when T3 is published on a port and `host` is a plain hostname, else ''."""
    port, host = published('t3'), (host or '').strip().lower()
    ok = bool(port) and 0 < len(host) <= 253 and all(c.isalnum() or c in '.-' for c in host)
    return f'http://{host}:{port}' if ok and not host.startswith(('.', '-')) else ''


def _host(kind):
    """-> (host, reason it isn't available)."""
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


def pair(kind, label, host=''):
    """`host`: the host the hub page was opened with (used only when T3 is published on a port)."""
    if kind not in TTL:
        raise ValueError('kind must be browser or app')
    base = _published(host)
    if not base:
        host, reason = _host(kind)
        if not host:
            return {'available': False, 'reason': reason}
        base = 'https://' + host
    label = re.sub(r'[^\w .@-]', '', label)[:40] or kind
    rc, out = run(
        f't3 auth pairing create --json --ttl {TTL[kind]} --label {sh_quote(label)} --base-url {sh_quote(base)}',
        timeout=30,
    )
    try:
        made = json.loads(out[out.index('{') :]) if rc == 0 else {}
    except ValueError:
        made = {}
    token = made.get('token') or made.get('credential') or ''
    if not token:
        return {'available': False, 'reason': f'T3 could not make a pairing link: {out[-200:]}'}
    url = made.get('pairUrl') or made.get('url') or f'{base}/pair#token={token}'
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
    """-> '' or why not; only paired devices, never other T3 sessions."""
    if session_id not in {d['id'] for d in devices()}:
        return NO_DEVICE
    rc, out = run(f't3 auth session revoke {sh_quote(session_id)}', timeout=20)
    return '' if rc == 0 else f'T3 refused: {out[-200:]}'
