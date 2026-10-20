"""Checksum-bound publication over the existing authenticated transport.

The bootstrap is passed through isolated Python, never executed from a writable
upload. Its reviewed source bundle can be retained with the accepted plan.
"""
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
