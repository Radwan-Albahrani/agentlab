"""`agentctl storage set`: disk sizes for per-person storage; apply grows or shrinks the disks to match."""

from . import apply, config, tomledit
from .util import Needs, need_root, say, write_if_changed


def set_sizes(config_path, person_size=None, host_reserve=None, dry=False):
    with open(config_path) as f:
        text = f.read()
    if person_size is None and host_reserve is None:
        raise Needs('nothing to change: give --person-size and/or --host-reserve')
    new_text = text
    if person_size is not None:
        new_text = tomledit.set_key(new_text, 'storage', 'person_size', person_size.lower())
    if host_reserve is not None:
        new_text = tomledit.set_key(new_text, 'storage', 'host_reserve', host_reserve.lower())
    cfg = config.loads(new_text)
    if cfg['storage']['mode'] != 'per-person':
        raise Needs('disk sizes apply to per-person storage ([storage] mode = "per-person")')
    say(f'person_size {cfg["storage"]["person_size"]}, host_reserve {cfg["storage"]["host_reserve"]}')
    if dry:
        return apply.apply(cfg, config_path, dry=True)
    need_root('agentctl storage set')
    write_if_changed(config_path, new_text)
    return apply.apply(cfg, config_path)
