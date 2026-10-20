"""Download reviewed prerequisite archives as the user; never invoke installation."""
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit,unquote
from runtime_download import fetch,valid
from toolchain_archives import verify_archives


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
