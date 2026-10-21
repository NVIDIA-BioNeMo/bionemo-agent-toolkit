# Read-only observations of qualified systemd package scopes.
#
# An empty observation alone never releases ownership: recovery must also fence
# late dispatch and verify the protected transaction and installed package state.
#
import re
import hashlib
import subprocess
from pathlib import Path
from toolchain_review import package_environment

_UNIT = re.compile(r'rfd4-package-[a-f0-9]{32}\.scope\Z')
_INVOCATION = re.compile(r'[a-f0-9]{32}\Z')


def scope_name(job_id, transaction_sha256):
    payload=(job_id+'\0'+transaction_sha256).encode()
    return 'rfd4-package-'+hashlib.sha256(payload).hexdigest()[:32]+'.scope'


def observe(unit, *, invocation=None, run=subprocess.run,
            cgroup_root=Path('/sys/fs/cgroup')):
    if not isinstance(unit,str) or not _UNIT.fullmatch(unit):
        raise ValueError('Invalid package scope identity')
    if invocation is not None and (not isinstance(invocation,str) or not _INVOCATION.fullmatch(invocation)):
        raise ValueError('Invalid recorded scope invocation')
    output=run(['/usr/bin/systemctl','show',unit,
                '--property=LoadState,ActiveState,SubState,ControlGroup,InvocationID'],
               check=True,capture_output=True,text=True,timeout=15,
               env=package_environment()).stdout
    fields={}
    for line in output.splitlines():
        key,separator,value=line.partition('=')
        if not separator or key in fields:raise ValueError('Ambiguous systemd scope response')
        fields[key]=value
    expected={'LoadState','ActiveState','SubState','ControlGroup','InvocationID'}
    if set(fields)!=expected:raise ValueError('Incomplete systemd scope response')
    if fields==dict(LoadState='not-found',ActiveState='inactive',SubState='dead',
                    ControlGroup='',InvocationID=''):
        # Unit garbage collection must not conceal a surviving recorded cgroup.
        # Permission failures are not absence; an existing group remains pending
        # until both systemd and the kernel agree it has disappeared.
        group=cgroup_root/'system.slice'/unit
        try:group.stat()
        except FileNotFoundError:pass
        else:return {'state':'pending','unit':unit,'reason':'recorded_cgroup_still_exists'}
        return {'state':'absent','unit':unit}
    if fields['LoadState']!='loaded':raise ValueError('Package scope is not authoritatively loaded')
    if not _INVOCATION.fullmatch(fields['InvocationID']):
        raise ValueError('Package scope has no valid invocation identity')
    if invocation is not None and fields['InvocationID']!=invocation:
        raise ValueError('Package scope invocation changed')
    group='/system.slice/'+unit
    if fields['ControlGroup']!=group:raise ValueError('Package scope cgroup changed')
    # Missing/unreadable events for a loaded unit is ambiguous, not empty.
    events={}
    for line in (cgroup_root/group.lstrip('/')/'cgroup.events').read_text().splitlines():
        key,value=line.split()
        if key in events:raise ValueError('Ambiguous cgroup event response')
        events[key]=value
    if events.get('populated') not in ('0','1'):
        raise ValueError('Package scope population is unknown')
    # systemd can still be registering tasks while reporting an empty group.
    # Only an inactive/dead unit with empty membership is a quiescent observation.
    empty=(events['populated']=='0' and fields['ActiveState']=='inactive'
           and fields['SubState']=='dead')
    return {'state':'empty' if empty else 'pending','unit':unit,
            'invocation':fields['InvocationID'],'control_group':group,
            'populated':events['populated']=='1',
            'active_state':fields['ActiveState'],'sub_state':fields['SubState']}


def verify_worker_membership(unit, *, run=subprocess.run,
                             cgroup_root=Path('/sys/fs/cgroup'),
                             membership=Path('/proc/self/cgroup')):
    observed=observe(unit,run=run,cgroup_root=cgroup_root)
    if (observed['state']!='pending' or not observed['populated']
            or observed['active_state']!='active' or observed['sub_state']!='running'):
        raise ValueError('Package worker is not in an active populated scope')
    lines=membership.read_text().splitlines()
    if lines!=['0::'+observed['control_group']]:
        raise ValueError('Package worker is outside its authorized unified cgroup')
    return observed


# Publish reviewed package ownership in an existing protected root directory.
#
# This is not authorization: the setup controller must validate the explicit
# reviewed action and hold its machine reservation before invoking this helper.
#
import fcntl
import json
import os
from toolchain_paths import protected_directory, transaction_directory, read_record, write_record
from remote_job import pending_machine_package


def publish(base, job_id, transaction, expected_checksum):
    if os.geteuid()!=0:raise ValueError('Package ownership publication requires authorized sudo')
    digest=hashlib.sha256(json.dumps(transaction,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=expected_checksum:raise ValueError('Reviewed prerequisite transaction checksum changed')
    base=Path(base)
    with protected_directory(base) as parent:
        descriptor=os.open('ownership.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=parent)
        with os.fdopen(descriptor,'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:previous_owner=read_record(parent,'package-owner.json')
            except FileNotFoundError:previous_owner=None
            pending=pending_machine_package(base)
            if pending:
                if pending['job_id']==job_id and pending['transaction_sha256']==digest:
                    return {'job_id':job_id,'transaction_sha256':digest,'directory':pending['directory'],'reused':True}
                raise ValueError('A prior privileged package transaction must be reconciled first')
            with transaction_directory(parent,job_id) as directory:
                record={'protocol':1,'job_id':job_id,'transaction':transaction,'transaction_sha256':digest}
                try:existing=read_record(directory,'package-intent.json')
                except FileNotFoundError:existing=None
                if existing is not None:
                    if previous_owner and previous_owner['job_id']!=job_id:
                        raise ValueError('A later package owner superseded this unpublished intent')
                    if existing!=record:raise ValueError('Package intent is immutable; use a newly reviewed operation')
                    # Recover the intent-to-owner persistence boundary only when
                    # no stage was dispatched and no later owner replaced it.
                    try:read_record(directory,'package-stage.json')
                    except FileNotFoundError:pass
                    else:raise ValueError('This operation already has a stage outcome; reconcile it')
                else:write_record(directory,'package-intent.json',record)
                owner={'job_id':job_id,'directory':str(base/job_id),'transaction_sha256':digest}
                write_record(parent,'package-owner.json',owner)
                return dict(owner,reused=existing is not None)


# Privileged compiler stage; caller must publish machine ownership before sudo.
#
# Not exposed as a standalone CLI until setup review/dispatch integration is complete.
#
import shutil
import tempfile
from remote_job import identity, pending_machine_package
from toolchain_paths import protected_directory, read_record, write_record
from contextlib import ExitStack
from toolchain_review import verify_archives
from toolchain_review import validate_plan
from toolchain_review import review, package_environment, package_configuration



def verify_installed(profile, run, env):
    audit=run(['dpkg','--audit'],check=True,capture_output=True,text=True,timeout=60,env=env).stdout.strip()
    if audit:raise ValueError('Installed package database needs repair: '+audit)
    names=sorted(profile['packages'])
    output=run(['dpkg-query','-W','-f=${Package}\t${Status}\t${Version}\n',*names],
               check=True,capture_output=True,text=True,timeout=60,env=env).stdout
    observed={}
    for line in output.splitlines():
        name,status,version=line.split('\t')
        if name in observed:raise ValueError('Duplicate installed package identity: '+name)
        if status!='install ok installed':raise ValueError('Package is not fully installed: '+name)
        observed[name]=version
    expected={name:item['Version'] for name,item in profile['packages'].items()}
    if observed!=expected:raise ValueError('Installed prerequisite versions differ from reviewed profile')
    return observed


def verify_dispatch_configuration(transaction, root_config=Path('/root/.dpkg.cfg')):
    if transaction.get('requires_absent_root_dpkg_config') is not True:
        raise ValueError('Review must require absence of root personal dpkg configuration')
    # Only ENOENT is evidence of absence. Permission errors and dangling
    # symlinks must never be interpreted as a missing configuration.
    try:root_config.lstat()
    except FileNotFoundError:pass
    else:raise ValueError('Root personal dpkg configuration is unsupported')
    if package_configuration()!=transaction.get('package_configuration'):
        raise ValueError('Package configuration changed before dispatch; obtain a new review')


def execute(directory, job_id, profile, archives, lease_dir, *, run=subprocess.run,
            inspect=review, process=subprocess.Popen):
    if os.geteuid()!=0:raise ValueError('The package stage requires explicitly authorized sudo')
    with ExitStack() as stack:
        directory_fd=stack.enter_context(protected_directory(directory))
        lease_fd=stack.enter_context(protected_directory(lease_dir))
        # Validate protected records before any root-owned output or subprocess.
        intent=read_record(directory_fd,'package-intent.json')
        read_record(lease_fd,'package-owner.json')
        descriptor=os.open('package-dispatch.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=directory_fd)
        lock=stack.enter_context(os.fdopen(descriptor,'a'))
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('The original package stage is still active; do not dispatch another installer')
        def locked_process(args, **kwargs):
            return process(args,pass_fds=(lock.fileno(),),**kwargs)
        def persist(value):write_record(directory_fd,'package-stage.json',value)
        return _execute_locked(directory,job_id,profile,archives,lease_dir,intent=intent,persist=persist,
                               run=run,inspect=inspect,process=locked_process)


def _execute_locked(directory, job_id, profile, archives, lease_dir, *, intent, persist, run, inspect, process):
    if os.geteuid()!=0:raise ValueError('The package stage requires explicitly authorized sudo')
    directory=Path(directory);lease_dir=Path(lease_dir)
    owner=pending_machine_package(lease_dir)
    if not owner or owner['job_id']!=job_id or Path(owner['directory'])!=directory.resolve():
        raise ValueError('This setup does not own the machine package transaction')
    transaction=intent['transaction']
    stage=directory/'package-stage.json'
    if stage.exists():raise ValueError('Package stage was already dispatched; reconcile it without retrying')
    # The root process must not infer authorization from a fresh, changed proposal.
    verify_dispatch_configuration(transaction)
    package_review={key:value for key,value in transaction.items() if key!='helper_hashes'}
    scope=verify_worker_membership(scope_name(job_id,intent['transaction_sha256']))
    receipt={'job_id':job_id,'transaction_sha256':intent['transaction_sha256'],
             'state':'running','supervisor':identity(os.getpid()),'scope':scope}
    persist(receipt)
    try:
        # A crash at any later point leaves a running receipt, never a false terminal one.
        # Retain archives on every uncertain outcome: a surviving dpkg child may
        # still need them after apt or this wrapper fails. Recovery owns cleanup.
        private=Path(tempfile.mkdtemp(prefix='rfd4-verified-packages-'));private.chmod(0o700)
        receipt['archive_directory']=str(private);persist(receipt)
        staged={}
        for index,(name,source) in enumerate(sorted(archives.items())):
            source=Path(source)
            if source.is_symlink() or not source.is_file():raise ValueError('Invalid source package archive')
            target=private/(str(index)+'.deb')
            shutil.copyfile(source,target);target.chmod(0o600);staged[name]=target
        evidence=verify_archives(profile,transaction,staged)
        if not evidence:raise ValueError('No package changes require privileged installation')
        if inspect(profile,run=run,archives=staged)!=package_review:
            raise ValueError('Prerequisite transaction changed; obtain a new review')
        # Apt must acquire local .deb files; --no-download also disables that
        # acquisition on the qualified apt version. Empty private source/list
        # directories prevent repository candidates or a network fallback.
        apt=private/'apt';apt.mkdir(mode=0o700)
        for name in ('sources','lists','cache','config-parts'):(apt/name).mkdir(mode=0o700)
        (apt/'sources.list').write_text('');(apt/'sources.list').chmod(0o600)
        base=['apt-get','-o','Dir::Etc::sourcelist='+str(apt/'sources.list'),
              '-o','Dir::Etc::sourceparts='+str(apt/'sources'),
              '-o','Dir::State::lists='+str(apt/'lists'),
              '-o','Dir::Cache::archives='+str(apt/'cache'),
              '-o','Dir::Cache::pkgcache=','-o','Dir::Cache::srcpkgcache=',
              '--no-install-recommends','--no-remove']
        paths=[str(staged[name]) for name in sorted(staged)]
        # APT_CONFIG is loaded before host fragments. Command-line -o flags
        # alone cannot prevent hooks from those fragments from being loaded.
        empty=apt/'empty.conf';empty.write_text('');empty.chmod(0o600)
        config=apt/'isolated.conf'
        config.write_text('Dir::Etc::parts '+json.dumps(str(apt/'config-parts'))+';\n'
                          'Dir::Etc::main '+json.dumps(str(empty))+';\n')
        config.chmod(0o600)
        env=dict(package_environment(),APT_CONFIG=str(config))
        proposal=run([*base,'--simulate','install',*paths],check=True,capture_output=True,text=True,timeout=120,env=env).stdout
        effects=validate_plan(proposal,{name:entry['Version'] for name,entry in profile['packages'].items()})
        expected={name:{key:entry[key] for key in ('version','actions')} for name,entry in transaction['changes'].items()}
        if effects!=expected:raise ValueError('Privileged package solver differs from reviewed transaction')
        receipt['archives']={name:{k:v for k,v in item.items() if k!='path'} for name,item in evidence.items()}
        persist(receipt)
        verify_dispatch_configuration(transaction)
    except Exception as error:
        receipt.update(state='failed',dispatch_not_started=True,preparation_error=str(error))
        persist(receipt)
        raise
    receipt['dispatch_started']=True;persist(receipt)
    child=process([*base,'-y','install',*paths],env=env,stdin=subprocess.DEVNULL)
    receipt['package_process']=identity(child.pid);persist(receipt)
    code=child.wait()
    # Preserve exact package outcome; no automatic apt/dpkg repair or rollback.
    receipt.update(exit_code=code,package_manager_waited=True)
    persist(receipt)
    if code==0:
        try:
            receipt['installed_packages']=verify_installed(profile,run,env)
            # The worker itself is a scope member. Only an external reconciler
            # can prove all descendants have exited and release ownership.
            receipt['needs_reconciliation']=True
        except Exception as error:
            receipt.update(state='running',needs_attention=True,verification_error=str(error))
    else:
        receipt.update(state='running',needs_attention=True,detail='Package manager exited unsuccessfully; reconcile surviving children and package state before releasing ownership')
    persist(receipt)
    return receipt


# Protected package recovery; never repairs packages or redispatches work.
import uuid




BOOT_ID_PATH=Path('/proc/sys/kernel/random/boot_id')
PACKAGE_LOCKS=(Path('/var/lib/dpkg/lock-frontend'),Path('/var/lib/dpkg/lock'))


def recover_preparation(base, job_id, *, reconcile_reboot=False, profile=None, finalize_success=False, run=subprocess.run):
    if os.geteuid()!=0:raise ValueError('Protected package recovery requires authorized sudo')
    base=Path(base)
    with ExitStack() as stack:
        parent=stack.enter_context(protected_directory(base))
        for name in ('ownership.lock',):
            fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=parent)
            handle=stack.enter_context(os.fdopen(fd,'a'))
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Package ownership is changing; retry recovery')
        owner=read_record(parent,'package-owner.json')
        if owner.get('job_id')!=job_id or owner.get('directory')!=str(base/job_id):
            raise ValueError('Recovery does not match the protected package owner')
        directory=stack.enter_context(protected_directory(base/job_id))
        fd=os.open('package-dispatch.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=directory)
        handle=stack.enter_context(os.fdopen(fd,'a'))
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Package stage is still active; recovery made no changes')
        intent=read_record(directory,'package-intent.json')
        if intent.get('protocol')!=1:raise ValueError('Package recovery cannot prove this older preparation protocol')
        # Verifies immutable transaction correlation; never resolves based on PID absence.
        pending_machine_package(base)
        try:receipt=read_record(directory,'package-stage.json')
        except FileNotFoundError:receipt=None
        if receipt and receipt.get('state') in ('succeeded','failed') and receipt.get('scope_quiescent') is True:
            # pending_machine_package above validated this durable terminal receipt.
            # Never upgrade an interrupted/failed outcome on a later call.
            return receipt
        if receipt and (receipt.get('dispatch_started') or receipt.get('package_process') or receipt.get('package_manager_waited')):
            if not reconcile_reboot and profile is None:
                raise ValueError('Package installation may have started; process and package-state reconciliation is required')
            prior=receipt.get('supervisor',{}).get('boot')
            current=BOOT_ID_PATH.read_text().strip()
            try:uuid.UUID(prior);uuid.UUID(current)
            except (ValueError,TypeError,AttributeError):raise ValueError('No valid boot identity proves the original processes ended')
            if prior==current:
                if profile is None:raise ValueError('Same-boot package recovery requires surviving-process reconciliation')
                return reconcile_scope(directory,intent,receipt,current,profile,stack,run,finalize_success=finalize_success)
            if not reconcile_reboot:raise ValueError('Boot changed; use explicit reboot reconciliation')
            for path in PACKAGE_LOCKS:
                fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
                package_lock=stack.enter_context(os.fdopen(fd,'r+'))
                try:fcntl.lockf(package_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise ValueError('Package manager is active; recovery made no changes')
            audit=run(['dpkg','--audit'],check=True,capture_output=True,text=True,timeout=60,
                      env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'}).stdout.strip()
            if audit:raise ValueError('Package database requires repair; ownership retained: '+audit)
            result=dict(receipt,state='failed',execution_outcome='unknown',recovery='reboot_reconciled',
                        recovery_boot=current,package_database_clean=True,package_locks_verified=True)
            write_record(directory,'package-stage.json',result)
            return result
        if receipt and receipt.get('dispatch_not_started') is True:return receipt
        result={'job_id':job_id,'transaction_sha256':intent['transaction_sha256'],
                'state':'failed','dispatch_not_started':True,
                'preparation_error':'Interrupted preparation was fenced before package dispatch; review a new setup to retry',
                'recovery':'undispatched_preparation_fenced'}
        write_record(directory,'package-stage.json',result)
        return result


def reconcile_scope(directory,intent,receipt,current,profile,stack,run,*,finalize_success=False):
    """Caller holds owner/dispatch locks; existing stage fences delayed workers."""
    digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if intent['transaction'].get('profile_sha256')!=digest:
        raise ValueError('Recovery profile differs from the reviewed transaction')
    saved=receipt.get('scope',{})
    unit=scope_name(intent['job_id'],intent['transaction_sha256'])
    if (saved.get('unit')!=unit or saved.get('control_group')!='/system.slice/'+unit
            or saved.get('populated') is not True or saved.get('active_state')!='active'
            or saved.get('sub_state')!='running' or not saved.get('invocation')):
        raise ValueError('No verified pre-install scope membership; ownership retained')
    observed=observe(unit,invocation=saved['invocation'],run=run)
    if observed['state'] not in ('empty','absent'):
        raise ValueError('Package scope still has activity; ownership retained')
    # This lock remains held through postcondition checks and the final receipt.
    # A delayed worker must acquire it and then refuses the existing stage.
    for path in PACKAGE_LOCKS:
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
        lock=stack.enter_context(os.fdopen(fd,'r+'))
        try:fcntl.lockf(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Package manager is active; ownership retained')
    installed=verify_installed(profile,run,package_environment())
    result=dict(receipt,state='failed',recovery='same_boot_reconciled',
                recovery_boot=current,execution_outcome='unknown',
                scope_quiescent=True,scope_observation=observed,
                package_database_clean=True,package_locks_verified=True,
                installed_packages=installed,needs_reconciliation=False,
                detail='Interrupted setup reconciled without retry; review setup again to verify the runtime')
    if finalize_success:
        process=receipt.get('package_process',{})
        if (receipt.get('dispatch_started') is not True
                or receipt.get('package_manager_waited') is not True
                or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0
                or type(process.get('pid')) is not int or process['pid']<=0
                or not str(process.get('start','')).isdigit() or process.get('boot')!=current):
            raise ValueError('Normal package completion lacks a matching successful process receipt')
        for stale in ('needs_attention','verification_error','preparation_error'):
            result.pop(stale,None)
        result.update(state='succeeded',recovery='normal_completion',execution_outcome='succeeded',
                      detail='Reviewed prerequisites completed and independently verified; runtime setup is not yet complete')
    # Preserve an observed apt exit separately. This is not a setup success or
    # readiness claim, including when all package versions happen to match.
    write_record(directory,'package-stage.json',result)
    return result


# One-shot privileged scope dispatch. No launch acknowledgment permits retry.
import stat


BUNDLE_FILES = frozenset({'toolchain_process.py', 'toolchain_review.py',
                          'toolchain_paths.py', 'remote_job.py'})
BOOT_ID=Path('/proc/sys/kernel/random/boot_id')


def verify_bundle(bundle, hashes):
    if set(hashes)!=BUNDLE_FILES:raise ValueError('Incomplete reviewed package helper bundle')
    with protected_directory(bundle) as directory:
        if set(os.listdir(directory))!=BUNDLE_FILES:
            raise ValueError('Package helper directory contains unreviewed files or bytecode')
        for name,digest in hashes.items():
            descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            with os.fdopen(descriptor,'rb') as handle:
                metadata=os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_mode & 0o022:
                    raise ValueError('Package helper must be a protected root-owned file')
                if hashlib.sha256(handle.read()).hexdigest()!=digest:
                    raise ValueError('Reviewed package helper changed: '+name)


def launch(base,job_id,bundle,hashes,profile,archives,*,process=subprocess.Popen):
    if os.geteuid()!=0:raise ValueError('Package dispatch requires authorized sudo')
    base=Path(base);bundle=Path(bundle)
    verify_bundle(bundle,hashes)
    with ExitStack() as stack:
        parent=stack.enter_context(protected_directory(base))
        directory=stack.enter_context(protected_directory(base/job_id))
        descriptor=os.open('package-dispatch.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o644,dir_fd=directory)
        lock=stack.enter_context(os.fdopen(descriptor,'a'))
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Package worker is active; observe it without redispatch')
        intent=read_record(directory,'package-intent.json')
        owner=read_record(parent,'package-owner.json')
        if owner.get('job_id')!=job_id or owner.get('directory')!=str(base/job_id):
            raise ValueError('Package launch does not own the protected transaction')
        pending_machine_package(base)
        if intent['transaction'].get('helper_hashes')!=hashes:
            raise ValueError('Package helper hashes are not bound to the authorized review')
        digest=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=intent['transaction'].get('profile_sha256'):
            raise ValueError('Package profile differs from the authorized review')
        try:stage=read_record(directory,'package-stage.json')
        except FileNotFoundError:stage=None
        if stage is not None:return {'state':'already_dispatched','stage':stage}
        try:previous=read_record(directory,'package-launch.json')
        except FileNotFoundError:previous=None
        if previous is not None:return {'state':'dispatch_uncertain','launch':previous}
        record={'job_id':job_id,'transaction_sha256':intent['transaction_sha256'],
                'boot':BOOT_ID.read_text().strip(),
                'unit':scope_name(job_id,intent['transaction_sha256']),
                'bundle':str(bundle),'hashes':hashes,'profile':profile,
                'archives':{name:str(path) for name,path in archives.items()}}
        write_record(directory,'package-launch.json',record)
        log_fd=os.open('package-launch.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    # The journal precedes dispatch. Recovery can win this boundary and write a
    # stage fence; the delayed worker checks that fence under the same lock.
    with os.fdopen(log_fd,'ab') as log:
        child=process(['/usr/bin/systemd-run','--system','--scope','--unit='+record['unit'],
            '/usr/bin/python3','-I','-S','-B','-c',
            'import sys;sys.path.insert(0,sys.argv[1]);from toolchain_process import worker;worker(sys.argv[2],sys.argv[3])',
            str(bundle),str(base),job_id],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            env=package_environment(),start_new_session=True,close_fds=True)
    return {'state':'dispatch_uncertain','job_id':job_id,'launcher_pid':child.pid}


def worker(base,job_id):
    # Scope containment is verified again by execute before any package command.
    with protected_directory(Path(base)/job_id) as directory:
        launch_record=read_record(directory,'package-launch.json')
    if launch_record['job_id']!=job_id:raise ValueError('Package worker job mismatch')
    if BOOT_ID.read_text().strip()!=launch_record['boot']:
        raise ValueError('Package worker belongs to an earlier boot')
    verify_bundle(launch_record['bundle'],launch_record['hashes'])
    pass
    execute(Path(base)/job_id,job_id,launch_record['profile'],launch_record['archives'],base)
