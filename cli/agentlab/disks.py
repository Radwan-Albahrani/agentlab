"""Agent storage ([storage] mode): a shared folder or pool image, or one sparse ext4 image per person, grown live or
shrunk offline (its agents stop for the minute it takes) to the size the config asks for."""

import os
import shutil
import time

from . import deploy
from .config import person
from .util import AGENT_UID, Failed, Plan, run, size_bytes, warn

SUBDIRS = ('home', 'workspace', 'linuxbrew')
HEADROOM = 1.1  # a disk shrinks only to where its data leaves this much room
STOP_WAIT_S = 180  # Coolify stops a service asynchronously


def undo_file(img):
    """resize2fs's record of every block a shrink overwrote: while it exists, the shrink may not have finished."""
    return f'{img}.shrink-undo'


def host_bytes(cfg):
    """Size of the filesystem the disk images live on."""
    path = f'{cfg["data"]}/disks'
    while not os.path.exists(path):
        path = os.path.dirname(path)
    s = os.statvfs(path)
    return s.f_blocks * s.f_frsize


def reserve_bytes(cfg, total):
    r = cfg['storage'].get('host_reserve') or '15%'
    return total * int(r[:-1]) // 100 if r.endswith('%') else size_bytes(r)


def auto_size(cfg, owners):
    """person_size "auto": the host disk minus its reserve and the fixed person_sizes, split evenly (whole GiB)."""
    fixed = cfg.get('person_sizes') or {}
    total = host_bytes(cfg)
    rest = total - reserve_bytes(cfg, total) - sum(size_bytes(fixed[o]) for o in owners if o in fixed)
    share = rest // max(1, sum(1 for o in owners if o not in fixed)) // 2**30
    if share < 1:
        raise Failed('[storage] person_size "auto": nothing is left for people after host_reserve and person_sizes')
    return f'{share}g'


def units(cfg):
    """[{name, image, mount, size, stacks}] of the images to keep mounted; [] for a plain shared folder."""
    st, data = cfg['storage'], cfg['data']
    if st['mode'] == 'shared':
        if not st['pool_size']:
            return []
        unit = {'name': 'pool', 'image': st['pool_image'], 'mount': f'{data}/agents', 'size': st['pool_size']}
        return [{**unit, 'stacks': _stacks(cfg, cfg['agents'])}]
    sizes = cfg.get('person_sizes') or {}
    owners = {person(a['owner']): a['owner'] for a in cfg['agents']}
    default = auto_size(cfg, set(owners.values())) if st['person_size'] == 'auto' else st['person_size']
    out = {}
    for a in cfg['agents']:
        slug = person(a['owner'])
        out[slug] = {
            'name': slug,
            'image': f'{data}/disks/{slug}.img',
            'mount': f'{data}/people/{slug}',
            'size': sizes.get(owners[slug], default),
            'stacks': _stacks(cfg, [b for b in cfg['agents'] if person(b['owner']) == slug]),
        }
    return list(out.values())


def _stacks(cfg, agents):
    """The stacks whose containers mount these agents' folders: the agents and their companions."""
    ids = {a['id'] for a in agents}
    return [f'agentlab-agent-{i}' for i in sorted(ids)] + [
        f'agentlab-companion-{c["name"]}' for c in cfg.get('companions') or [] if c['agent'] in ids
    ]


def label(name):
    return f'al-{name}'[:16]  # ext4 labels hold 16 bytes


def loop_device(img):
    _, out = run(['losetup', '-j', img], check=False)
    return out.split(':', 1)[0] if out else None


def has_filesystem(img):
    rc, out = run(['blkid', '-o', 'value', '-s', 'TYPE', img], check=False)
    return rc == 0 and bool(out.strip())


def mounted_from(mnt):
    _, out = run(['findmnt', '-n', '-o', 'SOURCE', mnt], check=False)
    return out.strip()


def ensure_unit(cfg, u, plan):
    img, mnt, want = u['image'], u['mount'], size_bytes(u['size'])
    if not os.path.exists(img):
        if os.path.ismount(mnt):
            warn(f'{mnt} is already a mount but {img} does not exist; leaving it alone')
            return
        plan.do(f'create the {u["size"]} {u["name"]} disk ({img})', fn=lambda: _create(img, want, u['name']))
    elif os.path.exists(undo_file(img)):
        if os.path.ismount(mnt):
            warn(f'{undo_file(img)} is left from a shrink, but {mnt} is mounted; leaving both alone')
            return
        plan.do(f'roll back the interrupted shrink of the {u["name"]} disk', fn=lambda: _roll_back(img))
    else:
        have = os.path.getsize(img)
        if want > have:
            plan.do(
                f'grow the {u["name"]} disk {have // 2**30} -> {want // 2**30} GiB', fn=lambda: _grow(img, mnt, want)
            )
        elif want < have:
            shrink(cfg, u, have, want, plan)
    if os.path.ismount(mnt):
        dev = loop_device(img) if os.path.exists(img) else None
        if dev is None or mounted_from(mnt) != dev:
            warn(f'{mnt} is mounted from {mounted_from(mnt) or "something else"}, not {img}; leaving it alone')
        return
    plan.do(f'mount the {u["name"]} disk at {mnt}', fn=lambda: _mount(img, mnt))


def ensure(cfg, plan):
    for u in units(cfg):
        ensure_unit(cfg, u, plan)
    for a in cfg['agents']:
        for sub in ('', *SUBDIRS):
            path = os.path.join(a['path'], sub) if sub else a['path']
            if not os.path.isdir(path):
                plan.do(f'create {path}', fn=lambda p=path: _owned_dir(p))


def _create(img, size, name):
    os.makedirs(os.path.dirname(img), exist_ok=True)
    if os.path.exists(img) and has_filesystem(img):
        raise Failed(f'{img} already holds a filesystem; refusing to format it')
    with open(img, 'wb') as f:
        f.truncate(size)
    run(['mkfs.ext4', '-q', '-m', '0', '-L', label(name), img])


def _grow(img, mnt, size):
    with open(img, 'r+b') as f:
        f.truncate(size)
    dev = loop_device(img) if os.path.ismount(mnt) else None
    if dev:
        run(['losetup', '-c', dev])
        run(['resize2fs', dev])
    else:
        run(['e2fsck', '-f', '-p', img], check=False)
        run(['resize2fs', img])


def shrink(cfg, u, have, want, plan):
    """Shrink toward `want`, never below the data plus HEADROOM; skips while one of its agents is mid-turn or the host
    lacks room for the blocks the shrink moves (once inside the image, once in the undo file)."""
    use = usage(u['mount']) if os.path.ismount(u['mount']) else None
    if use is None:
        warn(f'{u["name"]} disk is not mounted, so its data cannot be measured; it shrinks on an apply once it is')
        return
    least = -(-int(use['used'] * HEADROOM) // 2**30) * 2**30
    target = max(want, least)
    if have - target < 2**30:  # not worth stopping anyone for
        if target > want:
            warn(
                f'{u["name"]} disk holds {use["used"] / 2**30:.0f} GiB, so it stays {have // 2**30} GiB, not {u["size"]}'
            )
        return
    busy = [a['id'] for a in cfg['agents'] if f'agentlab-agent-{a["id"]}' in u['stacks'] and deploy.agent_busy(a)]
    if busy:
        warn(f'{u["name"]} disk: {", ".join(busy)} mid-turn, so it shrinks on the next apply')
        return
    room = 2 * min(use['used'], have - target) + 2**30
    free = usage(os.path.dirname(u['image']))['avail']
    if free < room:
        warn(
            f'{u["name"]} disk: shrinking it safely needs {room / 2**30:.0f} GiB free on the host, which has {free / 2**30:.0f}'
        )
        return
    if target > want:
        warn(
            f'{u["name"]} disk holds {use["used"] / 2**30:.0f} GiB, so it shrinks to {target // 2**30} GiB, not {u["size"]}'
        )
    stops = f' (stops {", ".join(u["stacks"])} for a few minutes)' if u['stacks'] else ''
    plan.do(
        f'shrink the {u["name"]} disk {have // 2**30} -> {target // 2**30} GiB{stops}',
        fn=lambda: _shrink(cfg, u, target),
    )


def _wait_stopped(cfg, stacks, sleep=time.sleep):
    for _ in range(STOP_WAIT_S // 3):
        if not any(c['state'] == 'running' for s in stacks for c in deploy.stack_containers(cfg, s)):
            return
        sleep(3)
    raise Failed(f'{", ".join(stacks)} did not stop within {STOP_WAIT_S} s')


def _shrink(cfg, u, want, sleep=time.sleep):
    """Stop whatever uses the disk, then shrink its filesystem offline with an undo file, check it, and only then cut
    the image. Any failure rolls the filesystem back; the disk is always remounted (unless a roll back failed, when
    nothing touches it again until a person looks) and its stacks restarted."""
    img, mnt, undo, quiet = u['image'], u['mount'], undo_file(u['image']), Plan(False)
    running = [s for s in u['stacks'] if any(c['state'] == 'running' for c in deploy.stack_containers(cfg, s))]
    was_mounted, intact = os.path.ismount(mnt), True
    try:
        for s in running:
            deploy.stop(cfg, s, quiet)
        _wait_stopped(cfg, running, sleep)
        if was_mounted:
            run(['umount', mnt])  # fails while anything still holds a file there, before anything changed
        rc, out = run(['e2fsck', '-f', '-p', img], check=False)
        if rc >= 4:
            raise Failed(f'{img} needs a manual e2fsck: {out[-300:]}')
        if os.path.exists(undo):
            os.remove(undo)  # resize2fs will not overwrite one; the check above found the filesystem whole
        try:
            # Through a loop device, which resize2fs cannot cut: the image's tail holds the old copies of moved blocks
            # until the end, and the undo file only records overwritten ones.
            dev = run(['losetup', '--find', '--show', img])[1].strip()
            try:
                run(['resize2fs', '-z', undo, dev, f'{want // 1024}K'])  # refuses, changing nothing, if it won't fit
            finally:
                run(['losetup', '-d', dev], check=False)
            rc, out = run(['e2fsck', '-f', '-n', img], check=False)
            if rc:
                raise Failed(f'the shrunk filesystem did not check clean: {out[-300:]}')
            if fs_bytes(img) > want:
                raise Failed(f'the filesystem is still larger than {want // 2**30} GiB')
        except Failed:
            if os.path.exists(undo):
                intact = False
                _roll_back(img)
                intact = True
            raise
        os.remove(undo)
        with open(img, 'r+b') as f:
            f.truncate(want)  # past the end of the checked filesystem
    except Failed as e:
        warn(f'{u["name"]} disk was not shrunk; its data is as it was: {e}')
        if not intact:
            warn(f'{img} could not be rolled back: it stays unmounted with {undo}; run e2undo {undo} {img} by hand')
    finally:
        if intact and was_mounted and not os.path.ismount(mnt):
            run(['mount', '-o', 'loop,noatime', img, mnt])
        if intact:
            for s in running:
                deploy.start(cfg, s, quiet)


def _roll_back(img):
    """After a shrink stopped partway: a filesystem that still checks clean is kept as it is (resize2fs refused before
    moving anything, or finished); otherwise its undo file puts it back as it was before the shrink."""
    undo = undo_file(img)
    if run(['e2fsck', '-f', '-n', img], check=False)[0] == 0:
        os.remove(undo)
        return
    run(['e2undo', undo, img])
    rc, out = run(['e2fsck', '-f', '-p', img], check=False)
    if rc >= 4:
        raise Failed(f'{img} needs a manual e2fsck after rolling back: {out[-300:]}')
    os.remove(undo)


def fs_bytes(img):
    """Size of the ext4 filesystem in the image, from its superblock."""
    _, out = run(['dumpe2fs', '-h', img], check=False)  # prints the superblock even when it fails further on
    field = dict(line.split(':', 1) for line in out.splitlines() if ':' in line)
    try:
        return int(field['Block count'].strip()) * int(field['Block size'].strip())
    except (KeyError, ValueError):
        raise Failed(f'no ext4 superblock readable in {img}: {out[-300:]}') from None


def _mount(img, mnt):
    os.makedirs(mnt, exist_ok=True)
    if os.listdir(mnt):
        raise Failed(f'{mnt} is not empty but its disk is not mounted there; move its contents aside first')
    run(['mount', '-o', 'loop,noatime', img, mnt])


def _owned_dir(path):
    os.makedirs(path, exist_ok=True)
    os.chown(path, AGENT_UID, AGENT_UID)


def usage(path):
    """{size, used, avail} bytes of the filesystem holding path (None when the path is missing)."""
    if not os.path.exists(path):
        return None
    s = os.statvfs(path)
    size = s.f_blocks * s.f_frsize
    return {'size': size, 'used': size - s.f_bfree * s.f_frsize, 'avail': s.f_bavail * s.f_frsize}


def du(path):
    _, out = run(['du', '-sxb', path], check=False)
    return int(out.split()[0]) if out and out.split()[0].isdigit() else 0


def remove_agent_files(a, plan):
    """Deletes one agent's folder; a per-person disk stays (the owner's other agents, or a later agent, use it)."""
    if os.path.isdir(a['path']):
        plan.do(f'delete {a["path"]}', fn=lambda: shutil.rmtree(a['path']))
