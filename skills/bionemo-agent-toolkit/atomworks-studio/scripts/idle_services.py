"""Positive activity checks required before infrastructure role exemptions."""
import fcntl
import json
import os
import stat
import subprocess
from pathlib import Path


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
