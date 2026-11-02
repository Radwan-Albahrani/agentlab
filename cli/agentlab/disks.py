"""Where agents' files live ([storage] mode). `shared`: every agent under <data>/agents, a plain folder or, with
pool_size, one sparse ext4 image so agents together can't fill the host. `per-person`: one sparse ext4 image per
owner (<data>/disks/<person>.img at <data>/people/<person>), so one person filling theirs stops no one else.
Images grow when the size rises (online, resize2fs) and never shrink: shrinking an ext4 in use risks the data. An
image that already has a filesystem is never formatted, and a mount someone else made (e.g. fstab) is left alone.

Ownership: agent folders are owned by uid/gid 1000, the agent user inside the image. With Sysbox the container's
root is a high host uid, but Sysbox ID-maps bind mounts (kernel >= 5.12, ext4 supports it), so a host file owned by
1000 is seen as 1000 inside; without Sysbox uid 1000 is uid 1000. The same ownership works in both modes."""

import os
import shutil

from .config import person
from .util import AGENT_UID, Failed, run, size_bytes, warn

SUBDIRS = ('home', 'workspace', 'linuxbrew')


def units(cfg):
    """[{name, image, mount, size}] of the images to keep mounted; [] for a plain shared folder."""
    st, data = cfg['storage'], cfg['data']
    if st['mode'] == 'shared':
        if not st['pool_size']:
            return []
        return [{'name': 'pool', 'image': st['pool_image'], 'mount': f'{data}/agents', 'size': st['pool_size']}]
    sizes = cfg.get('person_sizes') or {}
    out = {}
    for a in cfg['agents']:
        slug = person(a['owner'])
        out[slug] = {
            'name': slug,
            'image': f'{data}/disks/{slug}.img',
            'mount': f'{data}/people/{slug}',
            'size': sizes.get(a['owner'], st['person_size']),
        }
    return list(out.values())


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


def ensure_unit(u, plan):
    img, mnt, want = u['image'], u['mount'], size_bytes(u['size'])
    if not os.path.exists(img):
        if os.path.ismount(mnt):
            warn(f'{mnt} is already a mount but {img} does not exist; leaving it alone')
            return
        plan.do(f'create the {u["size"]} {u["name"]} disk ({img})', fn=lambda: _create(img, want, u['name']))
    else:
        have = os.path.getsize(img)
        if want > have:
            plan.do(
                f'grow the {u["name"]} disk {have // 2**30} -> {want // 2**30} GiB', fn=lambda: _grow(img, mnt, want)
            )
        elif want < have:
            warn(f'{u["name"]} disk: {u["size"]} is below its current {have // 2**30} GiB; disks never shrink')
    if os.path.ismount(mnt):
        dev = loop_device(img) if os.path.exists(img) else None
        if dev is None or mounted_from(mnt) != dev:
            warn(f'{mnt} is mounted from {mounted_from(mnt) or "something else"}, not {img}; leaving it alone')
        return
    plan.do(f'mount the {u["name"]} disk at {mnt}', fn=lambda: _mount(img, mnt))


def ensure(cfg, plan):
    """Every storage image mounted, and every agent's folders present and owned by the agent user."""
    for u in units(cfg):
        ensure_unit(u, plan)
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
        f.truncate(size)  # sparse: takes space only as agents write
    run(['mkfs.ext4', '-q', '-m', '0', '-L', label(name), img])


def _grow(img, mnt, size):
    with open(img, 'r+b') as f:
        f.truncate(size)
    dev = loop_device(img) if os.path.ismount(mnt) else None
    if dev:
        run(['losetup', '-c', dev])  # the loop device picks up the new file size
        run(['resize2fs', dev])  # ext4 grows online
    else:
        run(['e2fsck', '-f', '-p', img], check=False)
        run(['resize2fs', img])


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
