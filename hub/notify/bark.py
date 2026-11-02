import base64
import ctypes
import json
import os
import time
import urllib.error
import urllib.request

from .settings import DATA, load, lock, random_text

BARK = os.environ.get('BARK_URL', '')  # empty: phone pushes are off
LOG = os.path.join(DATA, 'notify-log.json')
recent = []  # newest first, shown on the page; mutated in place


def load_recent():
    try:
        with open(LOG) as f:
            recent[:] = json.load(f)
    except (OSError, ValueError):
        pass


def send(title, body, subtitle='', level='active', group='agents', s=None, kind='test', profile='', url=''):
    """Push one notification. Returns (ok, detail)."""
    s = s or load()
    if not BARK:
        return False, 'no Bark server configured (BARK_URL)'
    if not s['device_key']:
        return False, 'no device key yet'
    msg = {
        k: v
        for k, v in {
            'title': title,
            'subtitle': subtitle,
            'body': body or ' ',
            'group': group,
            'level': level,
            'sound': s['sound'],
            'url': url,
        }.items()
        if v
    }
    while len(json.dumps(msg).encode()) > (2600 if s['encrypt'] else 3500) and len(msg['body']) > 200:
        msg['body'] = msg['body'][: int(len(msg['body']) * 0.85)].rsplit(' ', 1)[0] + '…'  # APNs: 4 KB per push
    if s['encrypt']:
        iv = random_text()  # fresh IV per push
        ct = base64.b64encode(aes_cbc(s['enc_key'].encode(), iv.encode(), json.dumps(msg).encode())).decode()
        payload = {
            'device_key': s['device_key'],
            'ciphertext': ct,
            'iv': iv,
            'level': level,
            'group': group,
            'url': url,
            'body': 'Agent update',
        }  # body: shown only if the app can't decrypt
    else:
        payload = {'device_key': s['device_key'], **msg}
    ok, detail = post({k: v for k, v in payload.items() if v})
    with lock:
        recent.insert(
            0,
            {
                'at': time.time(),
                'kind': kind,
                'profile': profile,
                'title': title,
                'subtitle': subtitle,
                'body': body[:160],
                'ok': ok,
                'detail': '' if ok else detail,
            },
        )
        del recent[30:]
        try:
            with open(LOG, 'w') as f:
                json.dump(recent, f)
        except OSError:
            pass
    return ok, detail


def post(payload):
    req = urllib.request.Request(
        BARK + '/push',
        data=json.dumps(payload).encode(),
        method='POST',
        headers={'Content-Type': 'application/json; charset=utf-8'},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read() or b'{}')
        return res.get('code') == 200, res.get('message', '')
    except urllib.error.HTTPError as e:  # Bark explains itself in the body
        try:
            detail = json.loads(e.read()).get('message', str(e))
        except ValueError:
            detail = str(e)
        return False, detail[:200]
    except Exception as e:
        return False, str(e)[:160]


def server_up():
    if not BARK:
        return False
    try:
        with urllib.request.urlopen(BARK + '/ping', timeout=3) as r:
            return json.loads(r.read()).get('code') == 200
    except Exception:
        return False


def aes_cbc(key, iv, data):
    """AES-CBC with PKCS7 padding through libcrypto (already loaded by Python's ssl; no extra package)."""
    lib = ctypes.CDLL('libcrypto.so.3')
    vp, cp, ip = ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)
    lib.EVP_CIPHER_CTX_new.restype = vp
    cipher = {16: lib.EVP_aes_128_cbc, 24: lib.EVP_aes_192_cbc, 32: lib.EVP_aes_256_cbc}[len(key)]
    cipher.restype = vp
    lib.EVP_EncryptInit_ex.argtypes = [vp, vp, vp, cp, cp]
    lib.EVP_EncryptUpdate.argtypes = [vp, vp, ip, cp, ctypes.c_int]
    lib.EVP_EncryptFinal_ex.argtypes = [vp, vp, ip]
    lib.EVP_CIPHER_CTX_free.argtypes = [vp]
    ctx = lib.EVP_CIPHER_CTX_new()
    out = ctypes.create_string_buffer(len(data) + 32)
    n1, n2 = ctypes.c_int(0), ctypes.c_int(0)
    try:
        if not (
            lib.EVP_EncryptInit_ex(ctx, cipher(), None, key, iv)
            and lib.EVP_EncryptUpdate(ctx, out, ctypes.byref(n1), data, len(data))
            and lib.EVP_EncryptFinal_ex(ctx, ctypes.addressof(out) + n1.value, ctypes.byref(n2))
        ):
            raise RuntimeError('encryption failed')
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)
    return out.raw[: n1.value + n2.value]
