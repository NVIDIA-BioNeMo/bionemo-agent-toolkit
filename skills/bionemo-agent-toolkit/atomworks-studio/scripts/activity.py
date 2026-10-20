"""Conservative Linux activity evidence for a dedicated, single-user machine."""
import json
import shlex
import base64
import zlib
from pathlib import Path

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
    root = Path(__file__).parent
    sources = []
    for name in ('idle_baseline.py', 'idle_observation.py', 'idle_services.py', 'idle_inventory.py'):
        source = (root / name).read_text()
        source = '\n'.join(line for line in source.splitlines()
                           if not line.startswith(('from idle_baseline import ', 'from idle_observation import ')))
        sources.append(source)
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
