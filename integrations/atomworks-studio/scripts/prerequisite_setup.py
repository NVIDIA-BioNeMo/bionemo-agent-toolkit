# Download reviewed prerequisite archives as the user; never invoke installation.
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit,unquote
from runtime_download import fetch,valid
from toolchain_review import verify_archives


def resolve(name,item,origins,*,run=subprocess.run):
    # The locator is part of the reviewed profile, not ambient APT indexes.
    url=item.get('URL')
    if not isinstance(url,str) or not url or any(char.isspace() for char in url):
        raise ValueError('Missing or malformed pinned package URL: '+name)
    parsed=urlsplit(url)
    if (parsed.scheme not in ('http','https') or parsed.scheme+'://'+parsed.netloc not in origins
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Package locator is outside the reviewed public repositories: '+name)
    filename=item['Filename'].removeprefix('./')
    decoded=unquote(parsed.path)
    if ('..' in decoded.split('/') or '..' in filename.split('/') or
            not decoded.endswith('/'+filename)):
        raise ValueError('Package locator artifact path changed: '+name)
    return url


def prepare_archives(profile,names,directory,*,download=fetch,check_cancel=lambda:None):
    """Fetch pinned bytes for proposal preparation; does not authorize installation."""
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('Package cache cannot be a symlink')
    archives={};locators={}
    for name in sorted(names):
        check_cancel()
        item=profile['packages'][name]
        path=directory/(item['SHA256']+'.deb');archives[name]=path
        expected={'size':int(item['Size']),'sha256':item['SHA256']}
        url=resolve(name,item,profile['download_origins'])
        if not valid(path,expected):locators[name]=url
    # Validate every requested pinned URL before downloading any bytes. Package
    # manager configuration remains untouched; fetch resumes verified partials.
    for name,url in locators.items():
        check_cancel();item=profile['packages'][name]
        download(url,archives[name],{'size':int(item['Size']),'sha256':item['SHA256']})
    check_cancel()
    for name,path in archives.items():
        item=profile['packages'][name]
        if not valid(path,{'size':int(item['Size']),'sha256':item['SHA256']}):
            raise ValueError('Package archive checksum mismatch: '+name)
    return {name:str(path) for name,path in archives.items()}


def download_archives(profile,transaction,directory,*,run=subprocess.run,download=fetch,check_cancel=lambda:None):
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if transaction.get('profile_sha256')!=digest:raise ValueError('Package download profile changed')
    needed={name:change for name,change in transaction['changes'].items() if 'Inst' in change['actions']}
    for name,change in needed.items():
        item=profile['packages'][name]
        if change['version']!=item['Version'] or change['sha256']!=item['SHA256']:
            raise ValueError('Package download transaction changed: '+name)
    archives=prepare_archives(profile,needed,directory,download=download,check_cancel=check_cancel)
    verify_archives(profile,transaction,archives)
    return archives


# Generate a read-only remote prerequisite probe from reviewed local sources.
from toolchain_process import BUNDLE_FILES

SCRIPTS=Path(__file__).parent

def profile():return json.loads((SCRIPTS/'toolchain_profile.json').read_text())

def helper_hashes():
    return {name:hashlib.sha256((SCRIPTS/name).read_bytes()).hexdigest() for name in sorted(BUNDLE_FILES)}

def probe_script():
    sources={name:(SCRIPTS/(name+'.py')).read_text() for name in ('toolchain_review',)}
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


# Coordinate one reviewed prerequisite stage under the existing setup lease.
#
# The privileged adapter owns publication, one-shot launch and external finalization.
# This coordinator never retries a dispatch or treats transport failure as absence.
#
import time

from toolchain_review import review as package_review


def install_prerequisites(root, operation_id, reviewed, *, privileged, journal,
                          check_cancel, publication_started=lambda:None, record_terminal=lambda receipt:None, download=download_archives,
                          review=package_review, sleep=time.sleep):
    transaction=reviewed['prerequisites']
    profile=json.loads(Path(__file__).with_name('toolchain_profile.json').read_text())
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if transaction['profile_sha256']!=digest:
        raise ValueError('Prerequisite profile changed after setup review')
    fresh=dict(review(profile),helper_hashes=transaction['helper_hashes'])
    if fresh!=transaction:raise ValueError('Prerequisite state changed; obtain a new setup review')
    check_cancel()
    if not transaction['changes']:
        return {'state':'not_needed','profile_sha256':digest}
    # Production activation remains gated until the image/profile is qualified.
    if profile.get('status')!='qualified':
        raise ValueError('Privileged prerequisite profile has not completed qualification')
    journal('prerequisites_downloading')
    archives=download(profile,transaction,Path(root)/'setup-operations'/operation_id/'package-cache',check_cancel=check_cancel)
    check_cancel()
    if dict(review(profile),helper_hashes=transaction['helper_hashes'])!=transaction:
        raise ValueError('Prerequisite state changed during download; review again')
    # From this point, cancellation must reconcile published ownership first.
    publication_started()
    published=False
    try:
        privileged('publish',operation_id,transaction,profile,archives)
        published=True
        check_cancel()
    except BaseException:
        if published:
            record_terminal(privileged('fence',operation_id,transaction,profile,archives))
        raise
    journal('prerequisites_installing')
    # Lost acknowledgement escapes as needs-attention to the existing setup
    # journal. Never redispatch here, including on a timeout.
    privileged('launch',operation_id,transaction,profile,archives)
    pending_observations=0
    while True:
        journal('prerequisites_reconciling')
        receipt=privileged('observe',operation_id,transaction,profile,archives)
        if receipt.get('job_id')!=operation_id or receipt.get('transaction_sha256')!=hashlib.sha256(json.dumps(transaction,sort_keys=True,separators=(',',':')).encode()).hexdigest():
            raise ValueError('Prerequisite observation identity changed')
        if receipt.get('state')=='succeeded':
            record_terminal(receipt)
            check_cancel()
            return receipt
        if receipt.get('state')=='failed':
            record_terminal(receipt)
            raise ValueError('Prerequisite installation failed; review its recorded outcome before continuing')
        if receipt.get('state') not in ('running','pending'):
            raise ValueError('Prerequisite outcome is uncertain; reconcile the original operation')
        pending_observations=pending_observations+1 if receipt.get('state')=='pending' else 0
        if pending_observations>=60:
            raise TimeoutError('Package worker receipt remains unconfirmed; reconcile the original operation without redispatch')
        # Cancellation during apt does not kill it or release machine ownership.
        # The outer setup checks cancellation after safe terminal reconciliation.
        sleep(2)
