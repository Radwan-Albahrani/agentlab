"""Root's file access inside agent-controlled folders, never following symlinks or opening FIFOs."""

import contextlib
import json
import os
import stat

DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
AGENT_UID = 1000


class Folder:
    def __init__(self, base, rel, create=False, uid=AGENT_UID):
        self.fd = os.open(base, DIR_FLAGS)
        try:
            for part in [p for p in rel.split('/') if p]:
                if part in ('.', '..'):
                    raise ValueError(f'bad path part {part!r}')
                try:
                    nxt = os.open(part, DIR_FLAGS, dir_fd=self.fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, 0o755, dir_fd=self.fd)
                    nxt = os.open(part, DIR_FLAGS, dir_fd=self.fd)
                    os.fchown(nxt, uid, uid)
                os.close(self.fd)
                self.fd = nxt
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        os.close(self.fd)

    def names(self, suffix=''):
        return sorted(n for n in os.listdir(self.fd) if n.endswith(suffix))

    def is_file(self, name):
        try:
            return stat.S_ISREG(os.stat(name, dir_fd=self.fd, follow_symlinks=False).st_mode)
        except FileNotFoundError:
            return False

    def mtime(self, name):
        try:
            return os.stat(name, dir_fd=self.fd, follow_symlinks=False).st_mtime
        except FileNotFoundError:
            return 0

    def read(self, name, limit=65536):
        """Contents of a regular file, else None."""
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except OSError:
            return None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            return os.read(fd, limit).decode('utf-8', 'replace')
        finally:
            os.close(fd)

    def read_json(self, name):
        text = self.read(name)
        try:
            return json.loads(text) if text else None
        except ValueError:
            return None

    def write(self, name, text, uid=AGENT_UID, mode=0o644):
        tmp = f'.{name}.{os.getpid()}.tmp'
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp, dir_fd=self.fd)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=self.fd)
        try:
            os.write(fd, text.encode())
            os.fchown(fd, uid, uid)
            os.fchmod(fd, mode)
        finally:
            os.close(fd)
        os.replace(tmp, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)

    def write_json(self, name, data, **kw):
        self.write(name, json.dumps(data), **kw)

    def exists(self, name):
        try:
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def remove(self, name):
        with contextlib.suppress(FileNotFoundError, IsADirectoryError, PermissionError):
            os.unlink(name, dir_fd=self.fd)
