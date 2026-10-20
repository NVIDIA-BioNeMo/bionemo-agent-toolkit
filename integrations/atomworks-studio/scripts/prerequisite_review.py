"""Generate a read-only remote prerequisite probe from reviewed local sources."""
import hashlib
import json
from pathlib import Path
from toolchain_launch import BUNDLE_FILES

SCRIPTS=Path(__file__).parent

def profile():return json.loads((SCRIPTS/'toolchain_profile.json').read_text())

def helper_hashes():
    return {name:hashlib.sha256((SCRIPTS/name).read_bytes()).hexdigest() for name in sorted(BUNDLE_FILES)}

def probe_script():
    sources={name:(SCRIPTS/(name+'.py')).read_text() for name in ('toolchain_plan','toolchain_archives','toolchain_review')}
    payload={'sources':sources,'profile':profile()}
    return ('import json,sys,types\npayload=json.loads('+repr(json.dumps(payload))+')\n'
            'for name,source in payload["sources"].items():\n'
            ' module=types.ModuleType(name);sys.modules[name]=module;exec(compile(source,name,"exec"),module.__dict__)\n'
            'try:\n result=sys.modules["toolchain_review"].review(payload["profile"])\n'
            'except sys.modules["toolchain_review"].PreparationRequired as error:\n'
            ' import hashlib\n'
            ' result={"status":"preparation_required","packages":error.packages,"download_bytes":error.download_bytes,'
            '"installation_authorized":False,"profile_sha256":hashlib.sha256(json.dumps(payload["profile"],sort_keys=True,separators=(",",":")).encode()).hexdigest()}\n'
            'print(json.dumps(result))\n')

def bind_review(result):
    expected=hashlib.sha256(json.dumps(profile(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if result.get('profile_sha256')!=expected or result.get('installation_authorized') is not False:
        raise ValueError('Remote prerequisite review does not match the installed profile')
    if result.get('status')=='preparation_required':
        names=result.get('packages')
        packages=profile()['packages']
        if (not isinstance(names,list) or not names or any(not isinstance(name,str) or name not in packages for name in names)
                or len(set(names))!=len(names) or names!=sorted(names)
                or type(result.get('download_bytes')) is not int
                or result['download_bytes']!=sum(int(packages[name]['Size']) for name in names)
                or 'changes' in result):
            raise ValueError('Invalid package preparation request')
        return dict(result,helper_hashes=helper_hashes())
    if not isinstance(result.get('changes'),dict) or type(result.get('download_bytes')) is not int or result['download_bytes']<0:
        raise ValueError('Incomplete prerequisite review')
    return dict(result,helper_hashes=helper_hashes())
