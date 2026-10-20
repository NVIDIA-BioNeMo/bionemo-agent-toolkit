import copy
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from activity import PROBE, build_probe
from idle_inventory import remaining_work
from idle_services import check_service_activity, check_task_state


class IdleInventoryTests(unittest.TestCase):
    def test_candidate_profile_does_not_observe_or_exempt(self):
        observe=Mock(side_effect=AssertionError('must not run'))
        work=[{'pid':100}]
        self.assertEqual(remaining_work(work,{'status':'candidate'},observe),work)
        self.assertEqual(build_probe({'status':'candidate'}),PROBE)

    def test_exit_is_distinct_from_unreadable_live_process(self):
        observe=Mock(side_effect=FileNotFoundError)
        path=Mock();path.__truediv__=Mock(return_value=path)
        profile={'status':'qualified','roles':[]}
        with patch('idle_inventory.Path',return_value=path):
            path.exists.return_value=False
            self.assertEqual(remaining_work([{'pid':123}],profile,observe),[])
            path.exists.return_value=True
            with self.assertRaisesRegex(ValueError,'Live process'):
                remaining_work([{'pid':123}],profile,observe)

    def test_qualified_profile_is_bundled_without_remote_module_dependency(self):
        probe=build_probe({'status':'qualified','roles':[]})
        compile(probe,'remote-probe','exec')
        self.assertNotIn('from idle_observation import',probe)
        self.assertIn('busy=remaining_work(busy,qualified_profile)',probe)
        self.assertLess(probe.index('check_service_activity({role'),probe.index('busy=remaining_work'))

    def test_exact_role_exempt_but_extra_process_stays_busy(self):
        identity={'pid':100,'ppid':1,'start':'1','main_pid':100,'uid':0,
                  'executable':{'path':'/agent','sha256':'a'*64},'argv_sha256':'b'*64,
                  'cgroup':'/system.slice/a.service','unit':'a.service',
                  'unit_control_group':'/system.slice/a.service','unit_files':[],
                  'config_files':[],'identity_stable':True}
        role={k:v for k,v in identity.items() if k not in ('pid','ppid','start','main_pid','identity_stable')}
        profile={'status':'qualified','roles':[dict(role,id='agent',kind='main')]}
        def observe(pid,*args):
            return dict(identity,pid=pid,ppid=100 if pid==101 else 1)
        self.assertEqual(remaining_work([{'pid':101},{'pid':100}],profile,observe),[{'pid':101}])
        calls=[]
        def restart(pid,*args):
            calls.append(pid)
            return dict(identity,start='2' if len(calls)>1 else '1')
        with self.assertRaisesRegex(ValueError,'changed'):
            remaining_work([{'pid':100}],profile,restart)

    def test_unknown_service_activity_blocks(self):
        with patch('idle_services.os.open',side_effect=FileNotFoundError), patch('idle_services.service_command',return_value='unknown'):
            with self.assertRaises(ValueError):check_service_activity({'packagekit.service'})

    def test_package_container_and_snap_work_blocks(self):
        cases=[({'packagekit.service'},['','ao 1 /transaction']),
               ({'snapd.service'},['','{"status-code":200,"result":[{}]}']),
               ({'docker.service'},['','container-id']),
               ({'containerd.service'},['','moby','task-id'])]
        for units,outputs in cases:
            with self.subTest(units=units), patch('idle_services.os.open',side_effect=FileNotFoundError), patch('idle_services.service_command',side_effect=['active',*outputs]):
                with self.assertRaises(ValueError):check_service_activity(units)

    def test_observation_failure_is_not_idle(self):
        with patch('idle_services.os.open',side_effect=FileNotFoundError), patch('idle_services.service_command',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):check_service_activity(set())

    def test_inactive_service_is_not_activated_for_observation(self):
        with patch('idle_services.os.open',side_effect=FileNotFoundError), patch('idle_services.service_command',side_effect=['inactive','']) as run:
            check_service_activity({'packagekit.service'})
        self.assertEqual(run.call_count,2)
        self.assertFalse(any('busctl' in call.args[0] for call in run.call_args_list))

    def test_osconfig_empty_malformed_and_nonempty_state_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'task.state'
            check_task_state(state)
            for contents in ('', '{', 'null', '{"PatchTask":{}}'):
                with self.subTest(contents=contents):
                    state.write_text(contents)
                    with self.assertRaises(ValueError):check_task_state(state)
            state.write_text('{}')
            check_task_state(state)
            state.unlink()
            state.symlink_to(Path(directory)/'missing')
            with self.assertRaises(OSError):check_task_state(state)
