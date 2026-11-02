import json
import os
import secrets
import string
import threading

DATA = os.environ.get('NOTIFY_DATA', '/data')
SETTINGS = os.path.join(DATA, 'notify.json')
DEFAULTS = {
    'device_key': '',
    'sound': 'multiwayinvitation',
    'muted': False,
    'min_minutes': 1,
    'encrypt': False,
    'enc_key': '',
    'enc_iv': '',
}
lock = threading.Lock()


def random_text(n=16):
    abc = string.ascii_letters + string.digits
    return ''.join(secrets.choice(abc) for _ in range(n))


def load():
    try:
        with open(SETTINGS) as f:
            s = {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        s = dict(DEFAULTS)
    if not s['enc_key']:  # generated once; typed into Bark to turn on encryption
        s['enc_key'], s['enc_iv'] = random_text(), random_text()
        save(s)
    return s


def save(s):
    os.makedirs(DATA, exist_ok=True)
    with open(SETTINGS + '.tmp', 'w') as f:
        json.dump(s, f, indent=1)
    os.replace(SETTINGS + '.tmp', SETTINGS)


def update(**kw):
    with lock:
        s = load()
        s.update(kw)
        save(s)
        return s
