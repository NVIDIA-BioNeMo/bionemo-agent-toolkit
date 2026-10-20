"""Read-only observations of qualified systemd package scopes.

An empty observation alone never releases ownership: recovery must also fence
late dispatch and verify the protected transaction and installed package state.
"""
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
