"""Resumable public checkpoint downloads; publish only verified release bytes."""
import fcntl
import hashlib
import os
import re
from pathlib import Path
import urllib.request
import uuid


def valid(path, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected['size']:
        return False
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(4*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()==expected['sha256']


def fetch(url, destination, expected, opener=urllib.request.urlopen):
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    partial=destination.with_name(destination.name+'.part')
    with destination.with_name(destination.name+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if valid(destination,expected):
            # A previous rename may have succeeded before directory fsync failed.
            with destination.open('rb') as handle:os.fsync(handle.fileno())
            fd=os.open(str(destination.parent),os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            return destination
        if destination.is_symlink() or partial.is_symlink():raise ValueError('Refusing symlink checkpoint paths')
        if partial.exists() and partial.stat().st_size>=expected['size']:
            if valid(partial,expected):
                # A prior attempt may have failed during fsync after writing all bytes.
                with partial.open('rb') as handle:os.fsync(handle.fileno())
                partial.replace(destination)
                fd=os.open(str(destination.parent),os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
                return destination
            partial.rename(partial.with_name(partial.name+'.invalid-'+uuid.uuid4().hex))
        offset=partial.stat().st_size if partial.exists() else 0
        request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
        with opener(request,timeout=60) as response:
            append=offset>0 and response.status==206
            if response.status==206:
                match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                if not match or tuple(map(int,match.groups()))!=(offset,expected['size']-1,expected['size']):
                    raise ValueError('Invalid checkpoint resume response')
            if response.status not in (200,206):raise ValueError('Unexpected checkpoint response')
            count=offset if append else 0
            with partial.open('ab' if append else 'wb') as output:
                partial.chmod(0o600)
                while True:
                    chunk=response.read(4*1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>expected['size']:raise ValueError('Checkpoint exceeds pinned size')
                    output.write(chunk)
                output.flush();os.fsync(output.fileno())
        if not valid(partial,expected):raise ValueError('Checkpoint size or SHA-256 mismatch; file was not published')
        partial.replace(destination)
        fd=os.open(str(destination.parent),os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return destination


if __name__=='__main__':
    import json,sys
    recipe=json.loads(Path(__file__).with_name('runtime_recipe.json').read_text())
    data=Path(sys.argv[1])
    for weight in recipe['weights']:
        fetch(recipe['weights_base_url']+'/'+weight['directory']+'/'+weight['name'],data/weight['directory']/weight['name'],weight)
        print('Verified '+weight['name'],flush=True)
