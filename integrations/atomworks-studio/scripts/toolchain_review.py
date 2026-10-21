# Verify the exact package archives required by a reviewed transaction.
#
# A privileged installer must perform this check in its private staging directory
# immediately before use; validation of user-writable files is not a TOCTOU guard.
#
import hashlib
import json
from pathlib import Path
import stat


def verify_archives(profile, transaction, archives):
    expected_profile=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if transaction.get('profile_sha256')!=expected_profile:
        raise ValueError('Package transaction does not match the reviewed profile')
    needed={name:change for name,change in transaction['changes'].items() if 'Inst' in change['actions']}
    if set(archives)!=set(needed):
        raise ValueError('Staged archives do not exactly match the reviewed installations')
    verified={}
    for name,change in needed.items():
        expected=profile['packages'][name]
        if change['version']!=expected['Version'] or change['sha256']!=expected['SHA256']:
            raise ValueError('Package transaction artifact identity mismatch: '+name)
        path=Path(archives[name])
        # Reject symlinks and nonregular files before opening (e.g. FIFO/device).
        metadata=path.lstat()
        if not stat.S_ISREG(metadata.st_mode):raise ValueError('Package archive must be a regular file: '+name)
        if metadata.st_size!=int(expected['Size']):raise ValueError('Package archive size mismatch: '+name)
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(4*1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=expected['SHA256']:raise ValueError('Package archive checksum mismatch: '+name)
        verified[name]={'path':str(path.resolve()),'sha256':digest.hexdigest(),'size':metadata.st_size,'version':expected['Version']}
    return verified


# Validate apt's proposed effects against a reviewed compiler package manifest.
#
# This is a preparation guard, not an installer or permission to mutate a host.
# The eventual installation must revalidate under its package-manager lock.
#
import re


def validate_plan(output, packages):
    """Return exact proposed package effects; fail closed on unexpected changes."""
    effects = {}
    for line in output.splitlines():
        if line.startswith(('Remv ', 'Purg ')):
            raise ValueError('Compiler setup must not remove packages: '+line)
        if not line.startswith(('Inst ', 'Conf ')):
            continue
        match = re.fullmatch(r'(Inst|Conf) ([A-Za-z0-9+.:_-]+)(?: \[[^\]]+\])? \(([^\s)]+)(?: .*)?\)(?: \[.*\])?', line)
        if not match:
            raise ValueError('Unrecognized package-manager change: '+line)
        action, name, version = match.groups()
        # Architecture-qualified names remain distinct; never silently normalize.
        if packages.get(name) != version:
            raise ValueError('Unreviewed compiler package or version: '+name+'='+version)
        previous = effects.setdefault(name, {'version':version, 'actions':[]})
        if action in previous['actions']:
            raise ValueError('Duplicate package-manager change: '+name)
        previous['actions'].append(action)
    return effects


# Read-only prerequisite transaction review; never installs or repairs packages.
import os
import subprocess
import tempfile



def package_environment():
    """Do not let caller PATH, APT_CONFIG or loader variables change the review."""
    return {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/root',
            'LC_ALL':'C','LANG':'C','DEBIAN_FRONTEND':'noninteractive'}


def local_archive_proposal(profile, archives, *, run=subprocess.run):
    """Simulate exact cached packages without reading host repository indexes.

    This writes temporary APT configuration only. No download or installation
    occurs. Privileged callers must supply their protected copies of archives.
    """
    pass
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    verification={'profile_sha256':digest,'changes':{
        name:{'version':profile['packages'][name]['Version'],
              'sha256':profile['packages'][name]['SHA256'],'actions':['Inst']}
        for name in archives}}
    verify_archives(profile,verification,archives)
    env=package_environment()
    for name,path in sorted(archives.items()):
        output=run(['dpkg-deb','--field',str(Path(path).resolve()),'Package','Version','Architecture'],
                   check=True,capture_output=True,text=True,timeout=30,env=env).stdout
        fields={}
        for line in output.splitlines():
            key,separator,value=line.partition(': ')
            if not separator or key in fields:
                raise ValueError('Malformed package control identity: '+name)
            fields[key]=value
        expected={key:profile['packages'][name][key] for key in ('Package','Version','Architecture')}
        if fields!=expected:raise ValueError('Package control identity differs from profile: '+name)
    with tempfile.TemporaryDirectory(prefix='rfd4-package-proposal-') as temporary:
        root=Path(temporary)
        for name in ('parts','sources','lists','cache'):(root/name).mkdir(mode=0o700)
        for name in ('empty.conf','sources.list'):
            (root/name).write_text('');(root/name).chmod(0o600)
        config=root/'isolated.conf'
        config.write_text('Dir::Etc::parts '+json.dumps(str(root/'parts'))+';\n'
                          'Dir::Etc::main '+json.dumps(str(root/'empty.conf'))+';\n')
        config.chmod(0o600)
        env=dict(env,APT_CONFIG=str(config))
        args=['apt-get','-o','Dir::Etc::sourcelist='+str(root/'sources.list'),
              '-o','Dir::Etc::sourceparts='+str(root/'sources'),
              '-o','Dir::State::lists='+str(root/'lists'),
              '-o','Dir::Cache::archives='+str(root/'cache'),
              '-o','Dir::Cache::pkgcache=','-o','Dir::Cache::srcpkgcache=',
              '--simulate','--no-install-recommends','--no-remove','install',
              *[str(Path(archives[name]).resolve()) for name in sorted(archives)]]
        output=run(args,check=True,capture_output=True,text=True,timeout=120,env=env).stdout
    effects=validate_plan(output,{name:item['Version'] for name,item in profile['packages'].items()})
    # Only canonical effects belong in authorization identity: solver output
    # embeds temporary/cache paths that legitimately differ at revalidation.
    return {'effects':effects,'diagnostic_sha256':hashlib.sha256(output.encode()).hexdigest()}


def package_configuration(root=Path('/'), *, owner=0):
    """Bind dpkg inputs to a review; this is not configuration qualification."""
    root=Path(root)
    records={}
    def checked(path, directory=False):
        metadata=path.lstat()
        kind=stat.S_ISDIR if directory else stat.S_ISREG
        if not kind(metadata.st_mode) or metadata.st_uid!=owner or metadata.st_mode & 0o022:
            raise ValueError('Package configuration must be protected and nonsymlinked: '+str(path))
        return metadata
    def parents(path):
        for parent in reversed(path.relative_to(root).parents):
            checked(root/parent,True)
    def capture(relative):
        path=root/relative
        parents(path)
        if not path.exists() and not path.is_symlink():
            records[relative]=None
            return
        metadata=checked(path)
        if metadata.st_size>1024*1024:raise ValueError('Package configuration file is too large')
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor,'rb') as handle:
            opened=os.fstat(handle.fileno())
            if (opened.st_dev,opened.st_ino)!=(metadata.st_dev,metadata.st_ino):
                raise ValueError('Package configuration changed while reading')
            content=handle.read(1024*1024+1)
            after=os.fstat(handle.fileno())
        if len(content)>1024*1024 or (opened.st_size,opened.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('Package configuration changed while reading')
        records[relative]={'sha256':hashlib.sha256(content).hexdigest(),
                           'mode':stat.S_IMODE(metadata.st_mode),'uid':metadata.st_uid}
    capture('etc/dpkg/dpkg.cfg')
    fragments=root/'etc/dpkg/dpkg.cfg.d'
    parents(fragments);checked(fragments,True)
    names=sorted(item.name for item in fragments.iterdir())
    for name in names:capture('etc/dpkg/dpkg.cfg.d/'+name)
    if names!=sorted(item.name for item in fragments.iterdir()):
        raise ValueError('Package configuration inventory changed while reading')
    capture('usr/lib/needrestart/dpkg-status')
    return records


class PreparationRequired(ValueError):
    def __init__(self, names, download_bytes):
        self.packages=sorted(names)
        self.download_bytes=download_bytes
        super().__init__('Prepare pinned package archives before installation review: '+
                         ', '.join(self.packages)+' ('+str(download_bytes)+' bytes). No packages were installed.')


def review(profile, *, run=subprocess.run, os_release=Path('/etc/os-release'),
           configuration=package_configuration, archives=None):
    environment=package_environment()
    def command(args):
        return run(args,check=True,capture_output=True,text=True,timeout=120,env=environment).stdout.strip()
    release={}
    for line in os_release.read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1);release[key]=value.strip('"')
    if (release.get('ID'),release.get('VERSION_ID')) != ('ubuntu','22.04'):
        raise ValueError('Compiler installation supports only the qualified Ubuntu 22.04 image')
    config=configuration()
    if config!=profile.get('qualified_package_configuration'):
        raise ValueError('Package configuration is not qualified for this compiler profile')
    if command(['dpkg','--print-architecture'])!='amd64':
        raise ValueError('Compiler installation requires amd64')
    if command(['dpkg','--audit']):
        raise ValueError('Package-manager state needs repair; no automatic repair or installation attempted')
    artifacts=profile['packages']
    expected={name:item['Version'] for name,item in artifacts.items()}
    inventory={}
    for line in command(['dpkg-query','-W','-f=${Package}\t${Status}\t${Version}\n']).splitlines():
        name,status,version=line.split('\t')
        if status=='install ok installed':inventory[name]=version
    for name,version in expected.items():
        if name in inventory and inventory[name]!=version:
            comparison=run(['dpkg','--compare-versions',inventory[name],'gt',version],
                           check=False,capture_output=True,text=True,timeout=15,env=environment)
            if comparison.returncode not in (0,1):raise ValueError('Could not compare installed package versions')
            if comparison.returncode==0:raise ValueError('Compiler setup refuses downgrade: '+name)
    needed={name for name,version in expected.items() if inventory.get(name)!=version}
    if archives is None:
        cache=Path.home()/'.cache/bionemo-rfd4/packages'
        archives={name:cache/(artifacts[name]['SHA256']+'.deb') for name in needed}
        missing=[]
        for name,path in archives.items():
            item=artifacts[name]
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=int(item['Size']):
                missing.append(name);continue
            digest=hashlib.sha256()
            with path.open('rb') as handle:
                for block in iter(lambda:handle.read(4*1024*1024),b''):digest.update(block)
            if digest.hexdigest()!=item['SHA256']:missing.append(name)
        if missing:
            raise PreparationRequired(missing,sum(int(artifacts[name]['Size']) for name in missing))
    if set(archives)!=needed:
        raise ValueError('Prepared package set differs from current prerequisites; review again')
    effects=local_archive_proposal(profile,archives,run=run)['effects'] if needed else {}
    for name in needed:
        if 'Inst' not in effects.get(name,{}).get('actions',[]):
            raise ValueError('Package solver omitted required installation: '+name)
    changes={name:dict(effect,previous_version=inventory.get(name),sha256=artifacts[name]['SHA256'])
             for name,effect in effects.items()}
    total=sum(int(artifacts[name]['Size']) for name,effect in effects.items() if 'Inst' in effect['actions'])
    return {'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'os':'ubuntu-22.04','architecture':'amd64','changes':changes,'download_bytes':total,
            'simulation_sha256':hashlib.sha256(json.dumps(effects,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'installation_authorized':False,'package_configuration':config,
            'requires_absent_root_dpkg_config':True,
            'effect':'Requires separately reviewed privileged installation; this review made no package changes.'}
