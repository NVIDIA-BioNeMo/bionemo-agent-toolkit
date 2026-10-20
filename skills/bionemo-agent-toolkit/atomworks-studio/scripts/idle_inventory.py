"""Apply a shipped, reviewed role manifest to an otherwise blocking inventory."""
from idle_baseline import qualified_role
from idle_observation import observe_process
from pathlib import Path


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
