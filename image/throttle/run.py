"""Runs one shimmed heavy command once the host broker (agents/throttle) says go, and reports its peak memory."""

import contextlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time
import uuid

SPOOL = os.path.expanduser('~/.local/state/agent-throttle')
BROKER_FRESH_S = 10
DEFAULT_MAX_WAIT_S = 480
FALLBACK_ESTIMATE_MB = 1500
LOCAL_HEADROOM_MB = 1024
DAEMON_TOOLS = {'docker'}  # work runs in a daemon outside the measured tree: don't learn from them
MB = 2**20


def spool(name):
    return os.path.join(SPOOL, name)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    with open(path + '.tmp', 'w') as f:
        json.dump(data, f)
    os.replace(path + '.tmp', path)


def read_text(path):
    with open(path) as f:
        return f.read()


def project():
    d = os.getcwd()
    while d != '/':
        if os.path.exists(os.path.join(d, '.git')):
            return os.path.basename(d)
        d = os.path.dirname(d)
    return os.path.basename(os.getcwd())


def describe(tool, args):
    """-> (signature the broker learns peaks under, label the owner sees)."""
    command = ' '.join([tool, *[a for a in args if not a.startswith('-')][:2]])
    return f'{command} @ {project()}', f'{command} · {project()}'


def broker_alive():
    return time.time() - read_json(spool('broker.alive'), {}).get('at', 0) < BROKER_FRESH_S


def own_room_mb():
    """Memory left under this agent's own limit (file cache counts as free); effectively unlimited if unknown."""
    try:
        limit = read_text('/sys/fs/cgroup/memory.max').strip()
        current = int(read_text('/sys/fs/cgroup/memory.current'))
        stat = dict(line.split() for line in read_text('/sys/fs/cgroup/memory.stat').splitlines())
    except (OSError, ValueError):
        return 10**6
    return (int(limit) - current + int(stat.get('file', 0))) // MB if limit.isdigit() else 10**6


def wait_locally(deadline):
    while time.time() < deadline and own_room_mb() - LOCAL_HEADROOM_MB < FALLBACK_ESTIMATE_MB:
        time.sleep(2)


def wait_for_broker(job_id, deadline):
    last_touch = 0.0
    while time.time() < deadline:
        if os.path.exists(spool(f'{job_id}.go')):
            return
        if not broker_alive():
            wait_locally(deadline)
            return
        if time.time() - last_touch > 5:  # the broker reaps jobs that stop touching
            os.utime(spool(f'{job_id}.job'))
            last_touch = time.time()
        time.sleep(0.5)


def tree_rss_mb(root):
    children, rss = {}, {}
    for pid in filter(str.isdigit, os.listdir('/proc')):
        try:
            stat = read_text(f'/proc/{pid}/stat')
            fields = stat[stat.rindex(')') + 2 :].split()
            children.setdefault(int(fields[1]), []).append(int(pid))
            rss[int(pid)] = int(fields[21]) * 4096
        except (OSError, ValueError, IndexError):
            continue
    total, todo = 0, [root]
    while todo:
        pid = todo.pop()
        total += rss.get(pid, 0)
        todo += children.get(pid, [])
    return total // MB


def run(argv, job_id):
    """-> (exit code, peak MB); nice 19 so it yields CPU to T3 (nice 10)."""
    child = subprocess.Popen(['nice', '-n', '19', *argv])
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda s, _: child.send_signal(s))
    peak = 0

    def sample():
        nonlocal peak
        while child.poll() is None:
            rss = tree_rss_mb(child.pid)
            peak = max(peak, rss)
            if job_id:
                write_json(spool(f'{job_id}.run'), {'rss_mb': rss})
            time.sleep(1)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    code = child.wait()
    sampler.join()
    return code, peak


def admit(tool, signature, label, deadline):
    """Wait for a go -> the broker's job id (None on the local check)."""
    if not broker_alive():
        wait_locally(deadline)
        return None
    job_id = uuid.uuid4().hex[:12]
    write_json(spool(f'{job_id}.job'), {'signature': signature, 'tool': tool, 'label': label, 'created': time.time()})
    wait_for_broker(job_id, deadline)
    return job_id


def report(job_id, tool, signature, peak):
    write_json(spool(f'{job_id}.done'), {'signature': signature, 'peak_mb': None if tool in DAEMON_TOOLS else peak})
    for ext in ('.job', '.go', '.run'):
        with contextlib.suppress(FileNotFoundError):
            os.remove(spool(job_id + ext))


def main():
    tool, real, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    # No-op, not SIG_IGN: exec resets it, so the tool still gets Ctrl-C.
    for sig in (signal.SIGINT, signal.SIGQUIT):
        signal.signal(sig, lambda *_: None)
    signature, label = describe(tool, args)
    max_wait = read_json(spool('settings.json'), {}).get('max_wait_s', DEFAULT_MAX_WAIT_S)
    try:
        job_id = admit(tool, signature, label, time.time() + max_wait)
    except OSError:
        job_id = None
    leader = spool(f'pid-{os.getpid()}')  # the shim skips the gate below this process
    with contextlib.suppress(OSError):
        pathlib.Path(leader).touch()
    try:
        code, peak = run([real, *args], job_id)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(leader)
    if job_id:
        with contextlib.suppress(OSError):
            report(job_id, tool, signature, peak)
    if code < 0:
        signal.signal(-code, signal.SIG_DFL)
        os.kill(os.getpid(), -code)
    sys.exit(code)


if __name__ == '__main__':
    main()
