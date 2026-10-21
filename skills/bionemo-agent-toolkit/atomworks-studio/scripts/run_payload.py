# Checksum-bound publication over the existing authenticated transport.
#
# The bootstrap is passed through isolated Python, never executed from a writable
# upload. Its reviewed source bundle can be retained with the accepted plan.
#
import base64
import hashlib
import json
from pathlib import Path
import shlex

MODULES = ('toolchain_paths', 'executor_ownership', 'source_integrity', 'source_stage', 'execution_payload')
BOOTSTRAP = r'''
import base64,hashlib,json,sys,types
p=json.loads(base64.b64decode(sys.argv[1],validate=True))
names=('toolchain_paths','executor_ownership','source_integrity','source_stage','execution_payload')
if set(p['sources'])!=set(names):raise ValueError('Unexpected publication helper modules')
for name in names:
    source=p['sources'][name]
    if hashlib.sha256(source.encode()).hexdigest()!=p['files'][name+'.py']:raise ValueError('Publication helper changed')
    module=types.ModuleType(name);module.__file__='<reviewed:'+name+'>';sys.modules[name]=module
    exec(compile(source,module.__file__,'exec'),module.__dict__)
import executor_ownership as ownership
import execution_payload as execution
e=p['expected'];b=e['binding']
if e!=execution.validate_manifest(e['files'],b):raise ValueError('Invalid execution publication')
if set(b)!={'kind','id','review_checksum','executor_ownership'} or b['kind'] not in ('run','setup') or b['id']!=p['job_id']:raise ValueError('Publication review identity differs')
import re
if not isinstance(b['review_checksum'],str) or not re.fullmatch('[0-9a-f]{64}',b['review_checksum']):raise ValueError('Invalid publication review checksum')
proof=b['executor_ownership'];owner=ownership.validate(proof['owner'])
ownership.require_execution_scope(proof)
result=execution.publish_payload(p['upload'],p['destination'],e['files'],b)
execution.verify_path(p['destination'],e)
print(json.dumps(result))
'''


def bundle(scripts=None):
    scripts = Path(scripts) if scripts is not None else Path(__file__).parent
    sources = {}
    for name in MODULES:
        path = scripts / (name + '.py')
        if path.is_symlink(): raise ValueError('Publication helper source cannot be a symlink')
        sources[name] = path.read_text()
    return {'protocol': 1, 'sources': sources, 'bootstrap': BOOTSTRAP}


def manifest(value):
    if (not isinstance(value, dict) or set(value) != {'protocol', 'sources', 'bootstrap'}
            or value['protocol'] != 1 or set(value['sources']) != set(MODULES)):
        raise ValueError('Invalid reviewed publication helper bundle')
    return {name + '.py': hashlib.sha256(source.encode()).hexdigest() for name, source in value['sources'].items()} | {
        'publication_bootstrap': hashlib.sha256(value['bootstrap'].encode()).hexdigest()}


def command(upload, destination, expected, job_id, *, reviewed_bundle, reviewed_files):
    if manifest(reviewed_bundle) != reviewed_files:
        raise ValueError('Publication helper differs from accepted review')
    payload = {'upload': str(upload), 'destination': str(destination), 'expected': expected,
               'job_id': job_id, 'sources': reviewed_bundle['sources'], 'files': reviewed_files}
    encoded = base64.b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()
    return shlex.join(['python3', '-I', '-c', reviewed_bundle['bootstrap'], encoded])


# Freeze run inputs and executable helpers at review time, before acceptance.
import os
import uuid
import run_payload as execution_adapter
from runtime_recipe import overrides, runtime_overrides
import ownership_operation as ownership_adapter
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
        names = {name + '.py' for name in execution_adapter.MODULES} | {'remote_job.py', 'ownership_operation.py'}
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
