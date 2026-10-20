"""Privileged compiler stage; caller must publish machine ownership before sudo.

Not exposed as a standalone CLI until setup review/dispatch integration is complete.
"""
import json
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from remote_job import identity, pending_machine_package
from toolchain_paths import protected_directory, read_record, write_record
from contextlib import ExitStack
from toolchain_archives import verify_archives
from toolchain_plan import validate_plan
from toolchain_review import review, package_environment, package_configuration
from toolchain_scope import scope_name, verify_worker_membership


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
