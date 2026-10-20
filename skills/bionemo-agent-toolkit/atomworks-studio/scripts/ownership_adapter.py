"""Build isolated, checksum-verified ownership helpers without remote imports."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
from executor_ownership import checksum, validate

MODULES=('toolchain_paths','executor_ownership')
BOOTSTRAP=r'''
import base64,hashlib,json,sys,types
payload=json.loads(base64.b64decode(sys.argv[1],validate=True))
if set(payload['sources'])!={'toolchain_paths','executor_ownership'}:raise ValueError('Unexpected ownership helper modules')
for name,source in payload['sources'].items():
    if hashlib.sha256(source.encode()).hexdigest()!=payload['files'][name+'.py']:raise ValueError('Ownership helper changed')
for name in ('toolchain_paths','executor_ownership'):
    module=types.ModuleType(name);module.__file__='<reviewed:'+name+'>';sys.modules[name]=module
    exec(compile(payload['sources'][name],module.__file__,'exec'),module.__dict__)
import executor_ownership as ownership
if payload['action'] in ('inspect','require'):
    result=ownership.inspect(payload['owner'])
    if payload['action']=='require' and result.get('state')!='owned':raise ValueError('Protected executor ownership is not committed; no runtime was started')
elif payload['action']=='claim':result=ownership.claim(payload['owner'],payload['review_checksum'],allow_initial=payload['allow_initial'])
else:raise ValueError('Unsupported ownership helper action')
print(json.dumps(result))
'''


def sources(scripts=None):
    directory=Path(scripts) if scripts is not None else Path(__file__).parent
    result={}
    for name in MODULES:
        path=directory/(name+'.py')
        if path.is_symlink():raise ValueError('Ownership helper source cannot be a symlink')
        result[name]=path.read_text()
    return result


def manifest(scripts=None):
    return {name+'.py':hashlib.sha256(source.encode()).hexdigest() for name,source in sources(scripts).items()} | {'ownership_bootstrap':hashlib.sha256(BOOTSTRAP.encode()).hexdigest()}


def command(action, owner, *, files=None, allow_initial=False, scripts=None):
    validate(owner)
    if action not in ('inspect','require','claim'):raise ValueError('Unsupported ownership action')
    content=sources(scripts)
    hashes={name+'.py':hashlib.sha256(source.encode()).hexdigest() for name,source in content.items()} | {'ownership_bootstrap':hashlib.sha256(BOOTSTRAP.encode()).hexdigest()}
    if (action=='claim' and files is None) or (files is not None and hashes!=files):
        raise ValueError('Ownership helper changed since review; obtain a new review')
    payload={'action':action,'owner':owner,'sources':content,'files':hashes,
             'allow_initial':allow_initial,
             'review_checksum':checksum({'action':'claim_executor','owner':owner,'allow_initial':allow_initial})}
    encoded=base64.b64encode(json.dumps(payload,separators=(',',':')).encode()).decode()
    args=['python3','-I','-c',BOOTSTRAP,encoded]
    if action=='claim':args[0]='/usr/bin/python3'
    return shlex.join((['sudo','-n','--'] if action=='claim' else [])+args)
