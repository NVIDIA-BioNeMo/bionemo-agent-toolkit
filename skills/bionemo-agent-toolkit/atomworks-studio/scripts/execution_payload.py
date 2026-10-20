"""Publish reviewed execution bytes without reusing writable upload inodes.

Uploads are disposable attempts. A surviving SCP may still hold them open, so
even a verified upload directory must never itself become executable payload.
Mutable process markers and outputs belong outside the destination directory.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
from source_stage import publish

RECEIPT = 'payload-manifest.json'
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def validate_manifest(manifest, binding):
    if not isinstance(manifest, dict) or not manifest or len(manifest) > 128:
        raise ValueError('Invalid execution payload manifest')
    for name, digest in manifest.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name)
                or name == RECEIPT or not isinstance(digest, str)
                or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ValueError('Invalid execution payload filename or digest')
    if not isinstance(binding, dict) or not binding:
        raise ValueError('Missing execution payload identity binding')
    # Roundtrip also refuses non-JSON values before any filesystem mutation.
    identity = json.loads(canonical(binding))
    return {'protocol': 1, 'files': dict(manifest), 'binding': identity}


@contextlib.contextmanager
def directory(path, *, create=False):
    """Traverse with descriptors; reject symlinks at every path component."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Execution payload paths must be absolute without parent traversal')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                os.fsync(descriptor)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def read_file(descriptor, name, *, synchronize=False):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('Execution payload contains a nonregular file')
        value = handle.read(MAX_FILE + 1)
        if len(value) > MAX_FILE:
            raise ValueError('Execution payload file exceeds its size limit')
        if synchronize:
            os.fsync(handle.fileno())
        return value


def verify(descriptor, expected):
    if set(os.listdir(descriptor)) != set(expected['files']) | {RECEIPT}:
        raise ValueError('Published execution payload file set differs')
    if read_file(descriptor, RECEIPT, synchronize=True) != canonical(expected):
        raise ValueError('Published execution payload identity differs')
    if stat.S_IMODE(os.stat(RECEIPT, dir_fd=descriptor, follow_symlinks=False).st_mode) != 0o444:
        raise ValueError('Published execution payload receipt mode differs')
    total = 0
    for name, digest in expected['files'].items():
        content = read_file(descriptor, name, synchronize=True)
        total += len(content)
        if total > MAX_TOTAL or hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('Published execution payload checksum differs: ' + name)
        mode = os.stat(name, dir_fd=descriptor, follow_symlinks=False).st_mode
        if stat.S_IMODE(mode) != 0o444:
            raise ValueError('Published execution payload mode differs')
    if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o555:
        raise ValueError('Published execution payload directory mode differs')
    os.fsync(descriptor)


def verify_path(path, expected):
    """Revalidate the actual execution path, not a prior returned path string."""
    if (not isinstance(expected, dict) or set(expected) != {'protocol', 'files', 'binding'}
            or expected.get('protocol') != 1
            or validate_manifest(expected['files'], expected['binding']) != expected):
        raise ValueError('Invalid expected execution publication')
    with directory(path) as descriptor:
        verify(descriptor, expected)
    return expected


def publish_payload(upload, destination, manifest, binding):
    expected = validate_manifest(manifest, binding)
    destination = Path(destination)
    if destination.name in ('', '.', '..'):
        raise ValueError('Invalid execution payload destination')
    # One lock per writable job directory, shared by all upload attempts.
    with directory(destination.parent, create=True) as parent:
        try:
            lock = os.open('.payload-publish.lock', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=parent)
        except FileExistsError:
            lock = os.open('.payload-publish.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise ValueError('Execution publication lock is not a regular file')
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                existing = os.open(destination.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                try:
                    verify(existing, expected)
                    os.fsync(parent)
                finally:
                    os.close(existing)
                return {'path': str(destination), 'manifest_sha256': hashlib.sha256(canonical(expected)).hexdigest(), 'reused': True}
            temporary = '.payload-' + uuid.uuid4().hex
            os.mkdir(temporary, 0o700, dir_fd=parent)
            private = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                with directory(upload) as source:
                    if set(os.listdir(source)) != set(manifest):
                        raise ValueError('Upload file set differs from reviewed execution payload')
                    total = 0
                    for name, digest in sorted(manifest.items()):
                        content = read_file(source, name)
                        total += len(content)
                        if total > MAX_TOTAL or hashlib.sha256(content).hexdigest() != digest:
                            raise ValueError('Upload differs from reviewed execution payload: ' + name)
                        target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                         0o600, dir_fd=private)
                        with os.fdopen(target, 'wb') as handle:
                            handle.write(content)
                            os.fchmod(handle.fileno(), 0o444)
                            handle.flush()
                            os.fsync(handle.fileno())
                target = os.open(RECEIPT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=private)
                with os.fdopen(target, 'wb') as handle:
                    handle.write(canonical(expected))
                    os.fchmod(handle.fileno(), 0o444)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.fchmod(private, 0o555)
                verify(private, expected)
                # Never rename upload: private owns freshly allocated inodes.
                publish(temporary, destination.name, directory_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    try:
                        os.chmod(temporary, 0o700, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        # Only our unpublished flat tree, using held descriptors.
                        for name in os.listdir(private):
                            os.unlink(name, dir_fd=private)
                        os.rmdir(temporary, dir_fd=parent)
                finally:
                    os.close(private)
            return {'path': str(destination), 'manifest_sha256': hashlib.sha256(canonical(expected)).hexdigest(), 'reused': False}
        finally:
            os.close(lock)
