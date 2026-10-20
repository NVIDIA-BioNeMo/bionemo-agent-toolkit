"""Manifest-verified, atomic and retryable result collection."""
import fcntl
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import uuid
from registry import atomic

REMOTE_MANIFEST = '''import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
files=[]
for p in sorted(root.rglob('*')):
    if p.is_symlink(): raise ValueError('Symlink in result tree')
    if p.is_file() and (p.name.endswith('.cif') or p.name.endswith('.cif.gz')):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
        files.append(dict(path=p.relative_to(root).as_posix(),size=p.stat().st_size,sha256=h.hexdigest()))
print(json.dumps(dict(version=1,files=files)))
'''


def validate_manifest(manifest):
    import re
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise ValueError('Unsupported artifact manifest')
    files = manifest.get('files')
    if not isinstance(files, list) or not files or len(files) > 10000:
        raise ValueError('No result files or invalid artifact count')
    seen = set()
    for item in files:
        name = item.get('path')
        if not isinstance(name, str):
            raise ValueError('Invalid artifact path')
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name or name in seen:
            raise ValueError('Unsafe or duplicate artifact path')
        if not name.endswith(('.cif', '.cif.gz')):
            raise ValueError('Unexpected artifact type')
        if type(item.get('size')) is not int or item['size'] <= 0:
            raise ValueError('Empty or invalid result file')
        if not re.fullmatch('[0-9a-f]{64}', item.get('sha256', '')):
            raise ValueError('Invalid artifact checksum')
        seen.add(name)
    return manifest


def verify(directory, manifest):
    validate_manifest(manifest)
    for item in manifest['files']:
        path = directory / item['path']
        if any((directory / Path(*Path(item['path']).parts[:i])).is_symlink() for i in range(len(Path(item['path']).parts) + 1)) or not path.is_file():
            raise ValueError('Missing or symlinked result: ' + item['path'])
        if path.stat().st_size != item['size']:
            raise ValueError('Incomplete result: ' + item['path'])
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1048576), b''):
                digest.update(chunk)
        if digest.hexdigest() != item['sha256']:
            raise ValueError('Corrupt result: ' + item['path'])
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*')
              if p.is_file() and p.name.endswith(('.cif', '.cif.gz'))}
    if actual != {item['path'] for item in manifest['files']}:
        raise ValueError('Result set differs from the manifest')
    return [directory / item['path'] for item in manifest['files']]


def collect(backend, job_id):
    from core import safe_id
    directory = backend.state / safe_id(job_id)
    with (directory / 'collection.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = backend.status(job_id)
        if record['status'] != 'completed':
            raise ValueError('Job has not completed successfully')
        destination = directory / 'results'
        marker = destination / '.manifest.json'
        if marker.exists():
            try:
                files = verify(destination, json.loads(marker.read_text()))
                return {'job_id': job_id, 'files': [str(p) for p in files], 'collection': 'complete'}
            except (ValueError, OSError):
                pass  # Recover the cache without changing the scientific run.
        staging = directory / ('.collect-' + uuid.uuid4().hex)
        staging.mkdir(mode=0o700)
        try:
            cfg = backend.validate_config(record['target'])
            backend.verify_target(cfg)
            source = record['remote_dir'] + '/output/inference_samples'
            python = cfg['remote_root'] + '/model/.venv/bin/python'
            manifest = validate_manifest(json.loads(backend.target_exec(cfg,
                shlex.join([python, '-c', REMOTE_MANIFEST, source]), timeout=180)))
            atomic(directory / 'collection.json', {'state': 'collecting'})
            downloaded = staging / 'inference_samples'
            # Every transport nests the source basename under the destination.
            backend.target_copy(cfg, source, staging, download=True, timeout=300)
            verify(downloaded, manifest)
            atomic(downloaded / '.manifest.json', manifest)
            if destination.exists():
                destination.rename(directory / ('.previous-results-' + uuid.uuid4().hex))
            downloaded.rename(destination)
            atomic(directory / 'collection.json', {'state': 'complete', 'manifest': manifest})
            return {'job_id': job_id, 'files': [str(destination / p['path']) for p in manifest['files']], 'collection': 'complete'}
        except Exception as error:
            atomic(directory / 'collection.json', {'state': 'needs_attention', 'detail': str(error)})
            raise
        finally:
            shutil.rmtree(staging)
