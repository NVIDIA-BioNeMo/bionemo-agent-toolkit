"""Offline legacy upgrade. Never starts/stops compute or retries scientific work.

The operator must disable the old installation first. Read-only quarantine fences
ordinary old API writes, not a same-user program deliberately changing permissions
or explicitly redirecting the old binary at the new root.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import uuid

from registry import atomic
from managed_state import State, SCHEMA


def inventory(root):
    result={}
    for path in [root,*sorted(root.rglob('*'))]:
        relative=str(path.relative_to(root))
        info=path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError('Legacy state contains a symlink or nonregular entry: '+relative)
        item={'mode':stat.S_IMODE(info.st_mode),'directory':path.is_dir()}
        if not item['directory']:
            digest=hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda:handle.read(1048576),b''):digest.update(chunk)
            item['sha256']=digest.hexdigest()
        result[relative]=item
    return result


def content(items):
    return {name:{key:value for key,value in item.items() if key!='mode'} for name,item in items.items()}


def writers(root,run=subprocess.run):
    """Inspect relevant controller processes; never print/store raw environments."""
    process=run(['ps','-axo','pid=,command='],capture_output=True,text=True,check=True)
    found=[]
    for line in process.stdout.splitlines():
        pid_text,_,command=line.strip().partition(' ')
        if not pid_text.isdigit() or int(pid_text)==os.getpid():continue
        if not any(name in command for name in ('server.py','worker.py','preview.py','editor_app.py','start_server')):continue
        pid=int(pid_text)
        details=run(['ps','eww','-p',str(pid),'-o','command='],capture_output=True,text=True)
        if details.returncode:
            try:os.kill(pid,0)
            except ProcessLookupError:continue
            raise ValueError('Cannot establish whether a relevant legacy controller has ended')
        raw=details.stdout
        paths=[]
        for key in ('RFD4_STUDIO_HOME','ANNOTATION_STUDIO_SESSION_DIR'):
            match=re.search(r'(?:^| )'+key+r'=(.*?)(?= [A-Za-z_][A-Za-z0-9_]*=|$)',raw.strip())
            if match:paths.append(Path(match.group(1)).expanduser().resolve())
        paths.extend(Path(token).resolve() for token in command.split() if token.startswith('/'))
        explicit=any(path==root or root in path.parents for path in paths)
        default=('RFD4_STUDIO_HOME=' not in raw and root==Path.home()/'.local/share/bionemo-rfd4')
        if explicit or default:found.append(pid)
    return found


def require_idle(root,scan):
    active=scan(root)
    if active:raise ValueError('Stop the disabled legacy installation’s controllers/workers before upgrade: '+','.join(map(str,active)))
    for path in (root/'state').glob('*/job.json'):
        job=json.loads(path.read_text())
        if job.get('status') not in ('completed','failed','cancelled'):
            raise ValueError('Reconcile active or unresolved legacy run before upgrade: '+path.parent.name)
    for path in (root/'setup').glob('*.json'):
        if json.loads(path.read_text()).get('stage') not in ('complete','cancelled'):
            raise ValueError('Reconcile active or unresolved legacy setup before upgrade: '+path.stem)


def quarantine(root,snapshot,checkpoint=lambda phase:None):
    # Files first, then deepest directories: atomic replacement needs write
    # access to its parent, so protecting files alone is insufficient.
    ordered=sorted(snapshot,key=lambda name:(snapshot[name]['directory'],-len(Path(name).parts)))
    for name in ordered:
        path=root/name
        info=path.lstat()
        if stat.S_ISLNK(info.st_mode):raise ValueError('Legacy path changed to a symlink during quarantine')
        path.chmod(snapshot[name]['mode']&~0o222)
        checkpoint('quarantine_entry')


def flush_tree(root):
    for path in [*sorted(root.rglob('*')),root]:
        if path.is_symlink():raise ValueError('Symlink appeared while flushing upgrade')
        descriptor=os.open(str(path),os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)


def source_identity(root):
    info=root.stat()
    return {'device':info.st_dev,'inode':info.st_ino}


def require_completed_activation(root):
    """Validate publication before a backend can mutate an upgraded workspace."""
    root=Path(root).resolve()
    marker_path=root/'activation.json'
    journal_path=root.parent/('.'+root.name+'.upgrade.json')
    if not marker_path.is_file() or not journal_path.is_file():
        raise ValueError('Offline upgrade activation is incomplete; resume upgrade before opening this workspace')
    marker=json.loads(marker_path.read_text())
    journal=json.loads(journal_path.read_text())
    if (journal.get('phase')!='activated' or journal.get('schema')!=SCHEMA
            or marker.get('schema')!=SCHEMA
            or marker.get('upgrade_id')!=journal.get('id')
            or marker.get('new_root')!=str(root) or journal.get('new')!=str(root)
            or marker.get('legacy_root')!=journal.get('legacy')
            or marker.get('old_installation_disabled') is not True
            or marker.get('legacy_quarantined') is not True):
        raise ValueError('Offline upgrade activation is incomplete; resume upgrade before opening this workspace')
    metadata=json.loads((root/'managed-v2/state.json').read_text())
    from managed_state import BACKEND_PROTOCOL
    protocol=metadata.get('minimum_backend_protocol',SCHEMA)
    if (metadata.get('schema')!=SCHEMA or type(protocol) is not int
            or not 1<=protocol<=BACKEND_PROTOCOL):
        raise ValueError('Activated managed schema or backend protocol is unsupported')
    return marker


def require_workspace_activation(root):
    """Read-only startup gate; legacy roots need explicit offline activation."""
    root=Path(root).resolve()
    if ((root/'activation.json').exists()
            or (root.parent/('.'+root.name+'.upgrade.json')).exists()):
        return require_completed_activation(root)
    metadata_path=root/'managed-v2/state.json'
    metadata=json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    if metadata_path.exists():
        from managed_state import BACKEND_PROTOCOL
        protocol=metadata.get('minimum_backend_protocol',SCHEMA)
        if (metadata.get('schema')!=SCHEMA or type(protocol) is not int
                or not 1<=protocol<=BACKEND_PROTOCOL):
            raise ValueError('Incompatible compute schema or backend protocol; update before opening this workspace')
    legacy=(root/'config.json').exists() or (root/'compute-targets.json').exists()
    legacy=legacy or any((root/'sessions').glob('*.compute.json'))
    legacy=legacy or bool(metadata.get('migration',{}).get('sources'))
    legacy=legacy or (not metadata_path.exists() and any((root/'state').glob('*/job.json')))
    legacy=legacy or (not metadata_path.exists() and any((root/'setup').glob('*.json')))
    if legacy:
        raise ValueError('Legacy workspace requires offline upgrade with the old installation disabled; preserve this root')


def upgrade(legacy,new,*,old_installation_disabled=False,scan=writers,checkpoint=lambda phase:None):
    legacy,new=Path(legacy),Path(new)
    if legacy.is_symlink() or new.is_symlink():raise ValueError('State roots cannot be symlinks')
    legacy,new=legacy.resolve(strict=True),new.resolve()
    if not old_installation_disabled:
        raise ValueError('Disable the old installation before requesting offline upgrade')
    if legacy==new or legacy in new.parents or new in legacy.parents:
        raise ValueError('Legacy and new state roots must be separate, nonoverlapping directories')
    if legacy.is_symlink() or not legacy.is_dir() or new.is_symlink():
        raise ValueError('Use an existing real legacy directory and a new real destination')
    new.parent.mkdir(parents=True,exist_ok=True)
    journal_path=new.parent/('.'+new.name+'.upgrade.json')
    with (new.parent/('.'+new.name+'.upgrade.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if journal_path.exists():
            journal=json.loads(journal_path.read_text())
            if journal.get('legacy')!=str(legacy) or journal.get('new')!=str(new):
                raise ValueError('Upgrade journal belongs to different state roots')
        else:
            if new.exists():raise ValueError('Destination already exists; never overwrite a workspace')
            if (legacy/'managed-v2').exists():
                raise ValueError('This is already a managed-state root; do not run legacy upgrade against it')
            require_idle(legacy,scan)
            journal={'id':uuid.uuid4().hex,'legacy':str(legacy),'new':str(new),'phase':'snapshotted',
                     'old_installation_disabled':True,'source':inventory(legacy),'schema':SCHEMA,
                     'legacy_identity':source_identity(legacy)}
            atomic(journal_path,journal)
            checkpoint('snapshotted')
        if journal.get('legacy_identity')!=source_identity(legacy):
            raise ValueError('Legacy root filesystem identity changed; activation refused')
        activation=new/'activation.json'
        if new.exists():
            marker=json.loads(activation.read_text()) if activation.is_file() else {}
            if (marker.get('upgrade_id')!=journal['id'] or marker.get('schema')!=SCHEMA
                    or marker.get('legacy_root')!=str(legacy) or marker.get('new_root')!=str(new)):
                raise ValueError('Destination is not this upgrade; preserve it and inspect')
            current=inventory(legacy)
            if content(current)!=content(journal['source']) or any(item['mode']&0o222 for item in current.values()):
                raise ValueError('Legacy quarantine changed; activation replay refused')
            if journal['phase']!='activated' and inventory(new)!=journal.get('import_inventory'):
                raise ValueError('Published upgrade changed before completion; reconcile without restoring backups')
            metadata=json.loads((new/'managed-v2/state.json').read_text())
            if metadata.get('schema')!=SCHEMA:raise ValueError('Activated schema changed; update before continuing')
            journal['phase']='activated';atomic(journal_path,journal)
            return {'state':'activated','root':str(new),'journal':str(journal_path)}
        require_idle(legacy,scan)
        if content(inventory(legacy))!=content(journal['source']):
            raise ValueError('Legacy content changed; reconcile it before activation. Quarantine is not undone automatically.')
        quarantine(legacy,journal['source'],checkpoint)
        # Persist the fence itself before publishing any replacement workspace.
        # Flushing only the copied tree cannot make legacy chmods durable.
        flush_tree(legacy)
        require_idle(legacy,scan)
        quarantined=inventory(legacy)
        if (content(quarantined)!=content(journal['source'])
                or any(item['mode']&0o222 for item in quarantined.values())):
            raise ValueError('Legacy content changed while quarantining; activation refused')
        journal['phase']='quarantined';atomic(journal_path,journal);checkpoint('quarantined')
        staging=new.parent/('.'+new.name+'.upgrade-'+journal['id'])
        reusable=False
        if staging.exists() and journal.get('import_inventory'):
            if inventory(staging)!=journal['import_inventory']:
                raise ValueError('Imported upgrade changed; preserve it and reconcile before activation')
            reusable=True
        if staging.exists() and not reusable:
            if staging.is_symlink():raise ValueError('Upgrade staging path became a symlink')
            # Only this journal's unpublished staging tree can be rebuilt.
            for path in [staging,*staging.rglob('*')]:
                if path.is_symlink():raise ValueError('Unexpected symlink in upgrade staging')
                if path.is_dir():path.chmod(0o700)
            shutil.rmtree(staging)
        if not reusable:
            shutil.copytree(legacy,staging)
            for name,item in sorted(journal['source'].items(),key=lambda pair:len(Path(pair[0]).parts)):
                (staging/name).chmod(item['mode'])
            State(staging).migrate_legacy()
        if content(inventory(legacy))!=content(journal['source']):
            raise ValueError('Legacy content changed during import; activation refused')
        if not reusable:
            atomic(staging/'activation.json',{'upgrade_id':journal['id'],'schema':SCHEMA,
                    'legacy_root':str(legacy),'new_root':str(new),'legacy_quarantined':True,
                    'old_installation_disabled':True})
            flush_tree(staging)
            journal['import_inventory']=inventory(staging)
        journal['phase']='imported';atomic(journal_path,journal);checkpoint('imported')
        checkpoint('before_activation')
        staging.rename(new)
        descriptor=os.open(str(new.parent),os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        checkpoint('after_activation')
        journal['phase']='activated';atomic(journal_path,journal)
        return {'state':'activated','root':str(new),'journal':str(journal_path)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy',type=Path,required=True)
    parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--old-installation-disabled',action='store_true')
    args=parser.parse_args()
    print(json.dumps(upgrade(args.legacy,args.new,old_installation_disabled=args.old_installation_disabled),indent=2))
