"""Exact, reviewed infrastructure roles; never learn exemptions at stop time."""


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
