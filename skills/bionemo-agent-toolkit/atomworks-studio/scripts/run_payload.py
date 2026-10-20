"""Freeze run inputs and executable helpers at review time, before acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import uuid
import execution_adapter
from generation import overrides, runtime_overrides
import ownership_adapter
from source_stage import publish


def file_hashes(directory):
    result = {}
    for path in sorted(Path(directory).iterdir()):
        if path.is_symlink() or not path.is_file(): raise ValueError('Run payload must contain only regular files')
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def write(path, value):
    with path.open('xb') as handle:
        handle.write(value); handle.flush(); os.fsync(handle.fileno())


def freeze(directory, target, snapshot, samples, seed, generation, proof, *, scripts=None):
    scripts = Path(scripts) if scripts is not None else Path(__file__).parent
    directory = Path(directory)
    destination = directory / 'execution-payload'
    temporary = directory / ('.run-payload-' + uuid.uuid4().hex)
    temporary.mkdir(mode=0o700)
    try:
        names = {name + '.py' for name in execution_adapter.MODULES} | {'remote_job.py', 'ownership_adapter.py'}
        for name in sorted(names):
            source = scripts / name
            if source.is_symlink(): raise ValueError('Run helper source cannot be a symlink')
            write(temporary / name, source.read_bytes())
        content = (directory / 'input.cif').read_bytes()
        if hashlib.sha256(content).hexdigest() != snapshot['sha256']:
            raise ValueError('Input changed while freezing the reviewed run')
        write(temporary / 'input.cif', content)
        remote = target['remote_root'] + '/runs/' + snapshot['snapshot_id']
        root = target['remote_root']
        args = [root + '/model/.venv/bin/rfd4-generate', 'inputs=' + remote + '/payload/input.cif',
                'out_dir=' + remote + '/output', 'hydra.run.dir=' + remote + '/hydra',
                'num_replicates=' + str(samples), 'seed=' + str(seed), 'batch_size=1',
                'compile_lengths=null', 'prevalidate_inputs=true'] + runtime_overrides(root) + overrides(generation)
        guard = ownership_adapter.command('require_execution_scope', proof['owner'], proof=proof, scripts=temporary)
        script = ('#!/bin/bash\nset -e\n' + guard + '\nset +e\nexport PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1\n(cd ' +
                  shlex.quote(root + '/model') + ' && ' + shlex.join(args) + ')\ncode=$?\nprintf "%s" "$code" > ' +
                  shlex.quote(remote + '/exit_code') + '\nexit "$code"\n')
        write(temporary / 'run.sh', script.encode())
        bundle = execution_adapter.bundle(temporary)
        result = {'protocol': 1, 'files': file_hashes(temporary), 'publication_bundle': bundle,
                  'publication_files': execution_adapter.manifest(bundle)}
        descriptor = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        publish(temporary, destination)
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        return result
    finally:
        if temporary.exists():
            for path in temporary.iterdir(): path.unlink()
            temporary.rmdir()


def verified(directory, review):
    directory = Path(directory) / 'execution-payload'
    if review.get('protocol') != 1 or directory.is_symlink() or file_hashes(directory) != review.get('files'):
        raise ValueError('Frozen run payload changed; no upload or launch was attempted')
    if execution_adapter.manifest(review['publication_bundle']) != review['publication_files']:
        raise ValueError('Frozen publication helper changed')
    return directory
