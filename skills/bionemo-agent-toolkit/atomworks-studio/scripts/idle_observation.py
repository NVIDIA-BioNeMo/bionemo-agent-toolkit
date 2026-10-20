"""Read-only Linux process observations for reviewed infrastructure roles."""
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
