# Exact, reviewed infrastructure roles; never learn exemptions at stop time.


def qualified_role(process, profile, used, parents):
    """Return a role id only for a stable exact match and verified parent.

    All filesystem/process observations are supplied by the root probe. This
    classifier cannot itself grant qualification to an observed process.
    """
    if profile.get('status') != 'qualified' or process.get('identity_stable') is not True:
        return None
    identity_fields = ('uid', 'executable', 'argv_sha256', 'cgroup', 'unit',
                       'unit_control_group', 'unit_files', 'config_files')
    if any(key not in process for key in identity_fields):
        return None
    control_group = process['unit_control_group']
    if (not isinstance(control_group, str) or not control_group.startswith('/')
            or control_group == '/'
            or not (process['cgroup'] == control_group
                    or process['cgroup'].startswith(control_group + '/'))):
        return None
    for role in profile.get('roles', []):
        role_id = role['id']
        if used.get(role_id, 0) >= role.get('max_count', 1):
            continue
        if any(key not in role or process[key] != role[key]
               for key in identity_fields):
            continue
        main_pid = process.get('main_pid')
        if type(main_pid) is not int or main_pid <= 1:
            continue
        if role['kind'] == 'main':
            if process.get('pid') != main_pid:
                continue
        elif role['kind'] == 'child':
            if process.get('ppid') != main_pid:
                continue
            parent = parents.get(main_pid)
            if (not parent or parent.get('identity_stable') is not True
                    or parent.get('qualified_role') != role.get('parent_role')
                    or parent.get('pid') != main_pid
                    or parent.get('main_pid') != main_pid
                    or parent.get('unit') != process['unit']
                    or parent.get('unit_control_group') != control_group
                    or parent.get('cgroup') != process['cgroup']):
                continue
        else:
            continue
        used[role_id] = used.get(role_id, 0) + 1
        return role_id
    return None


# Read-only Linux process observations for reviewed infrastructure roles.
import hashlib
import stat
import subprocess
from pathlib import Path


def process_identity(path):
    text=(path/'stat').read_text()
    fields=text[text.rindex(')')+2:].split()
    return {'start':fields[19],'ppid':int(fields[1])}


def process_snapshot():
    result = set()
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            result.add((path.name, process_identity(path)['start']))
        except FileNotFoundError:
            if path.exists():
                raise ValueError('Live process identity could not be inspected')
    return result


def file_identity(path, cache):
    path=Path(path).resolve(strict=True)
    before=path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Infrastructure identity requires a regular file')
    key=(str(path),before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
    if key not in cache:
        digest=hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda:source.read(1048576),b''):digest.update(chunk)
        after=path.stat()
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ValueError('Infrastructure file changed during observation')
        cache[key]={'path':str(path),'sha256':digest.hexdigest(),'uid':before.st_uid,
                    'gid':before.st_gid,'mode':oct(before.st_mode&0o7777),'size':before.st_size}
    return cache[key]


def config_identity(path, cache):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Configuration symlinks require separate qualification')
    if not path.is_dir():
        return file_identity(path, cache)
    path = path.resolve(strict=True)
    before = sorted(path.rglob('*'))
    if len(before) > 4096:
        raise ValueError('Configuration tree exceeds inspection limit')
    directories = []
    files = []
    for entry in [path, *before]:
        if entry.is_symlink():
            raise ValueError('Configuration tree contains an unqualified symlink')
        if entry.is_dir():
            value = entry.stat()
            directories.append({'path':str(entry),'uid':value.st_uid,'gid':value.st_gid,
                                'mode':oct(value.st_mode & 0o7777)})
        elif entry.is_file():
            files.append(file_identity(entry, cache))
        else:
            raise ValueError('Configuration tree contains an unexpected file type')
    if before != sorted(path.rglob('*')):
        raise ValueError('Configuration tree changed during observation')
    return {'path':str(path),'kind':'directory','directories':directories,'files':files}


def observe_process(pid, services, files, config_paths=()):
    path=Path('/proc')/str(pid)
    before=process_identity(path)
    executable=(path/'exe').resolve(strict=True)
    argv=(path/'cmdline').read_bytes()
    groups=(path/'cgroup').read_text().splitlines()
    cgroup=next((line.split(':',2)[2] for line in groups if line.startswith('0:')),None)
    if cgroup is None:raise ValueError('Unified cgroup visibility is required for qualified roles')
    units=[part for part in cgroup.split('/') if part.endswith('.service')]
    unit=units[-1] if units else None
    properties={};unit_files=[]
    if unit:
        if unit not in services:
            output=subprocess.run(['systemctl','show',unit,'--property=MainPID,ControlGroup,FragmentPath,DropInPaths'],
                                  check=True,capture_output=True,text=True,timeout=5).stdout
            services[unit]=dict(line.split('=',1) for line in output.splitlines() if '=' in line)
        properties=services[unit]
        for name in [properties.get('FragmentPath',''),*properties.get('DropInPaths','').split()]:
            if name:unit_files.append(file_identity(name,files))
    status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines() if ':' in line)
    record={'pid':pid,**before,'uid':int(status['Uid'].split()[0]),'name':status['Name'].strip(),
            'executable':file_identity(executable,files),'argv_sha256':hashlib.sha256(argv).hexdigest(),
            'cgroup':cgroup,'unit':unit,'main_pid':int(properties.get('MainPID','0')),
            'unit_control_group':properties.get('ControlGroup'),
            'unit_files':sorted(unit_files,key=lambda v:v['path']),
            'config_files':[config_identity(name,files) for name in sorted(config_paths)]}
    final_identity=process_identity(path)
    final_status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines() if ':' in line)
    record['identity_stable']=(final_identity==before
        and (path/'exe').resolve(strict=True)==executable
        and (path/'cmdline').read_bytes()==argv
        and (path/'cgroup').read_text().splitlines()==groups
        and final_status['Uid'].split()==status['Uid'].split())
    return record


# Apply a shipped, reviewed role manifest to an otherwise blocking inventory.




def remaining_work(processes, profile, observe=observe_process):
    if profile.get('status') != 'qualified':
        return processes
    services, files, records = {}, {}, {}
    exited = set()
    def observe_live(pid, *args):
        try:
            return observe(pid, *args)
        except FileNotFoundError:
            if (Path('/proc') / str(pid)).exists():
                raise ValueError('Live process metadata could not be inspected')
            exited.add(pid)
            return None
    config_by_unit = {}
    for role in profile.get('roles', []):
        config_by_unit.setdefault(role['unit'], set()).update(
            item['path'] for item in role['config_files'])
    for process in processes:
        pid = process['pid']
        # First resolve the unit, then inspect its pinned configuration files.
        record = observe_live(pid, services, files)
        if record is None:
            continue
        paths = config_by_unit.get(record['unit'], set())
        if paths:
            checked = observe_live(pid, services, files, paths)
            if checked is None:
                continue
            if (checked['start'], checked['ppid']) != (record['start'], record['ppid']):
                raise ValueError('Process identity changed during activity inspection')
            record = checked
        records[pid] = record
    # Some verified OS MainPIDs were removed by the base inventory. Observe
    # those parents as well; parentage alone never exempts a child.
    for record in list(records.values()):
        parent = record['main_pid']
        if parent > 1 and parent not in records:
            observation = observe_live(parent, services, files)
            if observation is None:
                continue
            paths = config_by_unit.get(observation['unit'], set())
            if paths:
                checked = observe_live(parent, services, files, paths)
                if checked is None:
                    continue
                if checked['start'] != observation['start']:
                    raise ValueError('Parent identity changed during activity inspection')
                observation = checked
            records[parent] = observation
    used = {}
    ordered = sorted(records.values(), key=lambda item: item['pid'] != item['main_pid'])
    for record in ordered:
        role = qualified_role(record, profile, used, records)
        if role:
            record['qualified_role'] = role
    # A child may only rely on a parent that survived the whole sweep with the
    # same identity. Fresh caches also re-read systemd's current MainPID.
    final_services, final_files = {}, {}
    for record in ordered:
        if not record.get('qualified_role'):
            continue
        checked = observe_live(record['pid'], final_services, final_files,
                          config_by_unit.get(record['unit'], set()))
        if checked is None:
            # An exempted parent disappearing invalidates the sweep too.
            raise ValueError('Qualified process exited during activity inspection')
        expected = {key:value for key,value in record.items() if key != 'qualified_role'}
        if checked != expected or checked.get('identity_stable') is not True:
            raise ValueError('Qualified process changed during activity inspection')
    return [process for process in processes
            if process['pid'] not in exited and not records[process['pid']].get('qualified_role')]


# Positive activity checks required before infrastructure role exemptions.
import fcntl
import json
import os


def service_command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout


def check_task_state(name):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return
    with os.fdopen(descriptor, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 1048576:
            raise ValueError('Unexpected OSConfig task state file')
        value = source.read(1048577)
        after = os.fstat(source.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('OSConfig task state changed during observation')
        if len(value) > 1048576 or json.loads(value) != {}:
            raise ValueError('OSConfig task state requires reconciliation')


def check_service_activity(units):
    active = set()
    for unit in sorted(units):
        state = service_command(['systemctl', 'show', unit, '--property=ActiveState', '--value']).strip()
        if state == 'active':
            active.add(unit)
        elif state not in ('inactive', 'failed'):
            raise ValueError('Service state is transitional or unknown')
    units = active
    # Acquire package-manager locks without creating or changing their files.
    descriptors = []
    try:
        for path in ('/var/lib/dpkg/lock', '/var/lib/dpkg/lock-frontend',
                     '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock'):
            try:
                descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            except FileNotFoundError:
                continue
            descriptors.append(descriptor)
            fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if service_command(['dpkg', '--audit']).strip():
            raise ValueError('Package database requires attention')
        if 'packagekit.service' in units:
            output = service_command(['busctl', '--auto-start=no', 'call', 'org.freedesktop.PackageKit',
                              '/org/freedesktop/PackageKit', 'org.freedesktop.PackageKit',
                              'GetTransactionList']).strip()
            if output != 'ao 0':
                raise ValueError('PackageKit has active or unknown transactions')
        if 'snapd.service' in units:
            result = json.loads(service_command(['curl', '--silent', '--show-error', '--max-time', '10',
                                         '--unix-socket', '/run/snapd.socket',
                                         'http://localhost/v2/changes?select=in-progress']))
            if result.get('status-code') != 200 or result.get('result') != []:
                raise ValueError('Snap has active or unknown changes')
        if 'docker.service' in units and service_command(['docker', 'ps', '--quiet', '--no-trunc']).strip():
            raise ValueError('Running containers block managed stop')
        if 'containerd.service' in units:
            for namespace in service_command(['ctr', 'namespaces', 'list', '--quiet']).splitlines():
                if service_command(['ctr', '--namespace', namespace, 'tasks', 'list', '--quiet']).strip():
                    raise ValueError('Container tasks block managed stop')
        if 'google-osconfig-agent.service' in units:
            # OSConfig's agentconfig.TaskStateFile / OldTaskStateFile. Its
            # loader can resume either location; neither may conceal work.
            for name in ('/var/lib/google_osconfig_agent/osconfig_task.state',
                         '/etc/osconfig/osconfig_task.state'):
                check_task_state(name)
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


# REMOTE_ACTIVITY_HELPERS_END
# Conservative Linux activity evidence for a dedicated, single-user machine.
import shlex
import base64
import zlib

# Only MainPID of these operating-system services can be exempted. Their child
# processes, user services and arbitrary system services still count as work.
SYSTEM_SERVICES = {
    'systemd-journald.service': ['/usr/lib/systemd/systemd-journald', '/lib/systemd/systemd-journald'],
    'systemd-udevd.service': ['/usr/lib/systemd/systemd-udevd', '/lib/systemd/systemd-udevd'],
    'systemd-logind.service': ['/usr/lib/systemd/systemd-logind', '/lib/systemd/systemd-logind'],
    'systemd-networkd.service': ['/usr/lib/systemd/systemd-networkd', '/lib/systemd/systemd-networkd'],
    'systemd-resolved.service': ['/usr/lib/systemd/systemd-resolved', '/lib/systemd/systemd-resolved'],
    'dbus.service': ['/usr/bin/dbus-daemon', '/usr/bin/dbus-broker'],
    'ssh.service': ['/usr/sbin/sshd'],
    'sshd.service': ['/usr/sbin/sshd'],
    'rsyslog.service': ['/usr/sbin/rsyslogd'],
    'chrony.service': ['/usr/sbin/chronyd'],
    'systemd-timesyncd.service': ['/usr/lib/systemd/systemd-timesyncd', '/lib/systemd/systemd-timesyncd'],
    'nvidia-persistenced.service': ['/usr/bin/nvidia-persistenced'],
}

PROBE = r'''import fcntl,json,os,subprocess,sys,stat
from contextlib import ExitStack
from pathlib import Path
# Refuse namespace-limited or restricted inventories rather than inferring idle.
if os.geteuid()!=0:
    raise RuntimeError('Host-wide activity inspection requires root visibility')
container=subprocess.run(['systemd-detect-virt','--container','--quiet'],capture_output=True)
if container.returncode!=1:
    raise RuntimeError('Containerized or unverified host visibility blocks managed stop')
mounts=Path('/proc/mounts').read_text().splitlines()
proc=[line.split() for line in mounts if len(line.split())>=4 and line.split()[1]=='/proc']
if len(proc)!=1 or proc[0][2]!='proc' or any(option.startswith(('hidepid=','subset=')) and option not in ('hidepid=0',) for option in proc[0][3].split(',')):
    raise RuntimeError('Restricted process inventory blocks managed stop')
ancestors=set(); pid=os.getpid()
while pid>1 and pid not in ancestors:
    ancestors.add(pid)
    text=Path('/proc/%d/stat'%pid).read_text()
    pid=int(text[text.rfind(')')+2:].split()[1])
# Resolve only known OS daemon MainPIDs. A service name or process name alone
# never grants an exemption, and arbitrary workloads started by root still block.
services=SERVICES
baseline={}
for unit,executables in services.items():
    result=subprocess.run(['systemctl','show',unit,'--property=MainPID','--value'],capture_output=True,text=True,timeout=3)
    if result.returncode!=0:continue
    value=result.stdout.strip()
    if value.isdigit() and int(value)>1:baseline[int(value)]=(unit,executables)

def system_process(path,uid):
    pid=int(path.name)
    if uid>=1000:return False
    executable=(path/'exe').resolve(strict=True)
    metadata=executable.stat()
    if metadata.st_uid!=0 or metadata.st_mode & (stat.S_IWGRP|stat.S_IWOTH):return False
    if pid==1:
        return uid==0 and executable in [Path('/usr/lib/systemd/systemd').resolve(),Path('/lib/systemd/systemd').resolve()]
    match=baseline.get(pid)
    if not match:return False
    unit,allowed=match
    groups=(path/'cgroup').read_text().splitlines()
    if not any(line.split(':',2)[-1]=='/system.slice/'+unit for line in groups):return False
    return executable in [Path(item).resolve() for item in allowed]

busy=[]
for path in Path('/proc').iterdir():
    if not path.name.isdigit() or int(path.name) in ancestors:continue
    try:
        status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines() if ':' in line)
        uid=int(status['Uid'].split()[0])
        # Every userspace process counts, regardless of UID. Kernel threads
        # have no executable/cmdline; unknown executable access must fail closed.
        command=(path/'cmdline').read_bytes()
        if command or (path/'exe').exists():
            if system_process(path,uid):continue
            busy.append({'pid':int(path.name),'uid':uid,'name':status['Name'].strip()})
    except FileNotFoundError:
        # An unlinked executable is not evidence that its process exited.
        if path.exists():
            raise RuntimeError('Live process executable or metadata could not be inspected')
# Caller passes the executor user's path before sudo changes HOME. Reading an
# existing lock avoids creating a misleading root-owned alternative lock.
lockpath=Path(sys.argv[1])
with ExitStack() as stack:
    execution_locked=False
    try:
        descriptor=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:descriptor=None
    if descriptor is not None:
        lock=stack.enter_context(os.fdopen(descriptor,'r'))
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:execution_locked=True
    gpu=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True,timeout=15)
    print(json.dumps({'user_processes':busy,'gpu_processes':[line.strip() for line in gpu.splitlines() if line.strip()],'execution_locked':execution_locked,'host_visibility':'verified'}))
'''.replace('SERVICES', repr(SYSTEM_SERVICES))


def build_probe(profile=None):
    """Bundle reviewed helpers into the remote probe; no remote installation."""
    if not profile or profile.get('status') != 'qualified':
        return PROBE
    sources = [Path(__file__).read_text().split('# REMOTE_ACTIVITY_HELPERS_END', 1)[0]]
    encoded = base64.b64encode(zlib.compress(json.dumps(profile).encode())).decode()
    injected = ('\n'.join(sources) + '\nimport base64,zlib\nqualified_profile=json.loads('
                'zlib.decompress(base64.b64decode(' + repr(encoded) + ')))\n')
    probe = PROBE.replace('busy=[]', injected +
                          "\ninventory_started=process_snapshot()\nbusy=[]", 1)
    # Activity observations are mandatory before any additional exemption.
    probe = probe.replace('lockpath=Path(sys.argv[1])',
                         "check_service_activity({role['unit'] for role in qualified_profile['roles']})\n"
                         "busy=remaining_work(busy,qualified_profile)\n"
                         'lockpath=Path(sys.argv[1])', 1)
    return probe.replace("    print(json.dumps(",
                         "    appeared=process_snapshot()-inventory_started\n"
                         "    if appeared:raise RuntimeError('New processes appeared during activity inspection; check again')\n"
                         "    print(json.dumps(", 1)


def check_idle(backend, cfg):
    profile_path = Path(__file__).with_name('idle_profile.json')
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else None
    command=shlex.join(['sudo','-n','--','python3','-c',build_probe(profile)])+' "$HOME/.local/share/bionemo-rfd4/execution.lock"'
    result=json.loads(backend.target_exec(cfg,command,timeout=60))
    if set(result)!={'user_processes','gpu_processes','execution_locked','host_visibility'}:
        raise ValueError('Machine activity could not be established')
    if not isinstance(result['user_processes'],list) or not isinstance(result['gpu_processes'],list) or type(result['execution_locked']) is not bool:
        raise ValueError('Invalid machine activity evidence')
    if result['host_visibility']!='verified':
        raise ValueError('Host-wide process visibility could not be established')
    if result['user_processes'] or result['gpu_processes'] or result['execution_locked']:
        raise ValueError('Machine has active or unknown work; managed stop refused')
    return result
