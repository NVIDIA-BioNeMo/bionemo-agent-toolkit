"""Protected directory handling for the privileged package transaction helper.

Use directory descriptors rather than following caller-controlled path parents.
The caller supplies a trusted root-owned base, never a workspace directory.
"""
import os
import re
import stat
from contextlib import contextmanager


def _check(descriptor, owner_uid):
    metadata=os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid!=owner_uid or metadata.st_mode & 0o022:
        raise ValueError('Privileged transaction ancestry must be owned by root and not group/world writable')


@contextmanager
def protected_directory(path, *, owner_uid=0):
    """Open an existing absolute trusted directory with no symlink components."""
    path=os.fspath(path)
    if not path.startswith('/') or any(part in ('.','..') for part in path.split('/')):
        raise ValueError('Privileged transaction base must be an absolute canonical path')
    descriptor=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        _check(descriptor,owner_uid)
        for part in filter(None,path.split('/')):
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            try:_check(child,owner_uid)
            except BaseException:
                os.close(child);raise
            os.close(descriptor);descriptor=child
        yield descriptor
    finally:os.close(descriptor)


@contextmanager
def transaction_directory(base_descriptor, job_id, *, owner_uid=0):
    """Create/reopen one protected transaction; never accept a path as its ID."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',job_id):raise ValueError('Invalid package transaction ID')
    _check(base_descriptor,owner_uid)
    try:os.mkdir(job_id,0o755,dir_fd=base_descriptor)
    except FileExistsError:pass
    descriptor=os.open(job_id,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=base_descriptor)
    try:
        _check(descriptor,owner_uid)
        yield descriptor
    finally:os.close(descriptor)


def write_record(directory_fd, name, value, *, owner_uid=0):
    """Publish a receipt atomically within an already protected directory."""
    import json,uuid
    _check(directory_fd,owner_uid)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',name):raise ValueError('Invalid receipt name')
    temporary='receipt-'+uuid.uuid4().hex
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=directory_fd)
    try:
        os.fchmod(descriptor,0o644)
        with os.fdopen(descriptor,'w') as handle:
            json.dump(value,handle);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,name,src_dir_fd=directory_fd,dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try:os.unlink(temporary,dir_fd=directory_fd)
        except FileNotFoundError:pass


def read_record(directory_fd, name, *, owner_uid=0):
    import json
    _check(directory_fd,owner_uid)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',name):raise ValueError('Invalid receipt name')
    descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory_fd)
    with os.fdopen(descriptor,'r') as handle:
        metadata=os.fstat(handle.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=owner_uid
                or metadata.st_mode & 0o022 or metadata.st_size>1024*1024):
            raise ValueError('Privileged record is not protected or exceeds its size limit')
        return json.load(handle)
