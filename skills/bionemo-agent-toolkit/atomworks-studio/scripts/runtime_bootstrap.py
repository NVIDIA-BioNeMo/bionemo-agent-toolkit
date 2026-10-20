"""Extract one checksum-pinned uv executable; never execute an install shell script."""
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile
from runtime_download import fetch, valid


def bootstrap(directory, spec, download=fetch):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    wheel=directory/'uv-bootstrap.whl'
    download(spec['url'],wheel,{'sha256':spec['digests']['sha256'],'size':spec['size']})
    if not valid(wheel,{'sha256':spec['digests']['sha256'],'size':spec['size']}):
        raise ValueError('Bootstrap wheel does not match the pinned release')
    executable=directory/'uv'
    expected={'sha256':spec['binary_sha256'],'size':spec['binary_size']}
    if executable.is_symlink():raise ValueError('Bootstrap executable cannot be a symlink')
    if valid(executable,expected):
        executable.chmod(0o700)
        return executable
    with zipfile.ZipFile(wheel) as archive:
        matches=[entry for entry in archive.infolist() if entry.filename==spec['binary_member']]
        if len(matches)!=1 or matches[0].file_size!=spec['binary_size']:
            raise ValueError('Bootstrap wheel member is missing, duplicated or has an unexpected size')
        payload=archive.read(matches[0])
    if hashlib.sha256(payload).hexdigest()!=spec['binary_sha256']:
        raise ValueError('Bootstrap executable checksum mismatch')
    fd,name=tempfile.mkstemp(prefix='.uv-',dir=directory)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(payload);out.flush();os.fsync(out.fileno())
        os.chmod(name,0o700)
        os.replace(name,executable)
        fd=os.open(directory,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(name):os.unlink(name)
    return executable
