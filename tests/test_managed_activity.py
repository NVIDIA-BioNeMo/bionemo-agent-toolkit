import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from activity import qualified_role

class IdleBaselineTests(unittest.TestCase):
    def setUp(self):
        self.main={'uid':0,'executable':{'path':'/usr/bin/agent','sha256':'a'*64},'argv_sha256':'b'*64,
                   'cgroup':'/system.slice/agent.service','unit':'agent.service',
                   'unit_control_group':'/system.slice/agent.service','config_files':[],
                   'unit_files':[{'path':'/usr/lib/systemd/system/agent.service','sha256':'c'*64}],
                   'pid':100,'ppid':1,'main_pid':100,'identity_stable':True}
        keys=('uid','executable','argv_sha256','cgroup','unit','unit_files','unit_control_group','config_files')
        main_role={k:self.main[k] for k in keys}|{'id':'agent','kind':'main','max_count':1}
        self.child=dict(self.main,pid=101,ppid=100,uid=10,executable={'path':'/usr/bin/helper','sha256':'d'*64})
        child_role={k:self.child[k] for k in keys}|{'id':'helper','kind':'child','parent_role':'agent','max_count':1}
        self.profile={'status':'qualified','roles':[main_role,child_role]}

    def test_restart_resolves_new_main_pid(self):
        for pid in (100,999):
            self.assertEqual(qualified_role(dict(self.main,pid=pid,main_pid=pid),self.profile,{},{}),'agent')

    def test_candidate_and_changed_identity_cannot_exempt(self):
        self.assertIsNone(qualified_role(self.main,dict(self.profile,status='candidate'),{},{}))
        self.assertIsNone(qualified_role(dict(self.main,identity_stable=False),self.profile,{},{}))
        for key,value in [('uid',1),('executable',{'path':'/usr/bin/agent','sha256':'e'*64}),
                          ('argv_sha256','f'*64),('cgroup','/other'),('unit','other.service'),('unit_files',[])]:
            with self.subTest(key=key):self.assertIsNone(qualified_role(dict(self.main,**{key:value}),self.profile,{},{}))

    def test_child_requires_exact_role_and_verified_parent(self):
        self.assertIsNone(qualified_role(self.child,self.profile,{},{}))
        parent=dict(self.main,qualified_role='agent')
        self.assertEqual(qualified_role(self.child,self.profile,{}, {100:parent}),'helper')
        for changed in (dict(self.child,ppid=900),dict(self.child,executable={'path':'/bin/bash','sha256':'d'*64})):
            self.assertIsNone(qualified_role(changed,self.profile,{}, {100:parent}))
        self.assertIsNone(qualified_role(self.child,self.profile,{}, {100:dict(parent,identity_stable=False)}))

    def test_duplicate_role_and_unknown_process_remain_busy(self):
        used={}
        self.assertEqual(qualified_role(self.main,self.profile,used,{}),'agent')
        self.assertIsNone(qualified_role(self.main,self.profile,used,{}))
        self.assertIsNone(qualified_role(dict(self.main,pid=200),self.profile,{},{}))

    def test_missing_or_changed_configuration_cannot_exempt(self):
        for field in ('unit_control_group', 'config_files', 'unit_files', 'argv_sha256'):
            process = dict(self.main)
            del process[field]
            profile = copy.deepcopy(self.profile)
            del profile['roles'][0][field]
            self.assertIsNone(qualified_role(process, profile, {}, {}))
        changed = dict(self.main, config_files=[{'path':'/etc/agent', 'sha256':'changed'}])
        self.assertIsNone(qualified_role(changed, self.profile, {}, {}))

    def test_matching_profile_does_not_authorize_wrong_control_group(self):
        for group in ('/', '/system.slice/other.service'):
            process = dict(self.main, unit_control_group=group)
            profile = copy.deepcopy(self.profile)
            profile['roles'][0]['unit_control_group'] = group
            self.assertIsNone(qualified_role(process, profile, {}, {}))

    def test_child_cannot_use_parent_with_reused_or_mismatched_pid(self):
        parent = dict(self.main, qualified_role='agent', pid=999)
        self.assertIsNone(qualified_role(self.child, self.profile, {}, {100:parent}))

import hashlib
import os
import tempfile
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] /
                      'integrations/atomworks-studio/scripts'))
from activity import file_identity, process_identity, observe_process, config_identity


class IdleObservationTests(unittest.TestCase):
    def test_top_level_configuration_fifo_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fifo'
            os.mkfifo(path)
            with self.assertRaisesRegex(ValueError,'regular file'):
                config_identity(path,{})

    def test_config_directory_additions_and_content_changes_are_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache={}
            empty=config_identity(root,cache)
            (root/'extra.conf').write_text('workload')
            added=config_identity(root,cache)
            self.assertNotEqual(empty,added)
            (root/'extra.conf').write_text('modified')
            self.assertNotEqual(added,config_identity(root,cache))
            (root/'linked.conf').symlink_to(root/'extra.conf')
            with self.assertRaisesRegex(ValueError,'symlink'):config_identity(root,cache)

    def test_changed_content_and_permissions_invalidate_cached_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'agent'
            path.write_bytes(b'first')
            cache = {}
            first = file_identity(path, cache)
            path.write_bytes(b'other')
            second = file_identity(path, cache)
            self.assertNotEqual(first['sha256'], second['sha256'])
            self.assertEqual(second['sha256'], hashlib.sha256(b'other').hexdigest())
            path.chmod(0o600)
            third = file_identity(path, cache)
            self.assertEqual(third['mode'], '0o600')

    def test_missing_file_is_not_observed_as_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                file_identity(Path(directory) / 'missing', {})

    def test_proc_command_parentheses_do_not_shift_start_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            fields = ['S', '42'] + ['0'] * 17 + ['987654']
            (path / 'stat').write_text('123 (name (with) spaces) ' + ' '.join(fields))
            self.assertEqual(process_identity(path), {'start': '987654', 'ppid': 42})

    def test_live_identity_changes_are_not_stable(self):
        for changed_file, changed_value in (
            ('cmdline', 'agent\x00changed'),
            ('cgroup', '0::/system.slice/other.service\n'),
            ('status', 'Uid:\t1\t1\t1\t1\nName:\tagent\n'),
        ):
            with self.subTest(changed_file=changed_file), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                proc = root / '123'
                proc.mkdir()
                binary = root / 'agent'
                binary.write_bytes(b'fake executable')
                (proc / 'exe').symlink_to(binary)
                (proc / 'cmdline').write_bytes(b'agent\x00')
                (proc / 'cgroup').write_text('0::/system.slice/agent.service\n')
                (proc / 'status').write_text('Uid:\t0\t0\t0\t0\nName:\tagent\n')
                reads = []

                def identity(path):
                    reads.append(path)
                    if len(reads) == 2:
                        (proc / changed_file).write_text(changed_value)
                    return {'start':'999', 'ppid':1}

                def paths(value):
                    return root if value == '/proc' else Path(value)

                result = Mock(stdout='MainPID=123\nControlGroup=/system.slice/agent.service\n')
                with patch('activity.Path', side_effect=paths), \
                     patch('activity.process_identity', side_effect=identity), \
                     patch('activity.subprocess.run', return_value=result):
                    self.assertFalse(observe_process(123, {}, {})['identity_stable'])

from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from activity import PROBE, build_probe
from activity import remaining_work
from activity import check_service_activity, check_task_state


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
        with patch('activity.Path',return_value=path):
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
        with patch('activity.os.open',side_effect=FileNotFoundError), patch('activity.service_command',return_value='unknown'):
            with self.assertRaises(ValueError):check_service_activity({'packagekit.service'})

    def test_package_container_and_snap_work_blocks(self):
        cases=[({'packagekit.service'},['','ao 1 /transaction']),
               ({'snapd.service'},['','{"status-code":200,"result":[{}]}']),
               ({'docker.service'},['','container-id']),
               ({'containerd.service'},['','moby','task-id'])]
        for units,outputs in cases:
            with self.subTest(units=units), patch('activity.os.open',side_effect=FileNotFoundError), patch('activity.service_command',side_effect=['active',*outputs]):
                with self.assertRaises(ValueError):check_service_activity(units)

    def test_observation_failure_is_not_idle(self):
        with patch('activity.os.open',side_effect=FileNotFoundError), patch('activity.service_command',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):check_service_activity(set())

    def test_inactive_service_is_not_activated_for_observation(self):
        with patch('activity.os.open',side_effect=FileNotFoundError), patch('activity.service_command',side_effect=['inactive','']) as run:
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

import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from activity import check_idle, PROBE

class ActivityTests(unittest.TestCase):
    def test_probe_refuses_unprivileged_visibility(self):
        with patch('os.geteuid',return_value=1000):
            with self.assertRaisesRegex(RuntimeError,'root visibility'):
                exec(PROBE,{})

    def test_probe_refuses_container_or_unknown_container_check(self):
        for code in (0,2):
            with self.subTest(code=code), patch('os.geteuid',return_value=0), patch('subprocess.run',return_value=Mock(returncode=code)):
                with self.assertRaisesRegex(RuntimeError,'unverified host visibility'):
                    exec(PROBE,{})

    def test_idle_evidence(self):
        evidence={'user_processes':[],'gpu_processes':[],'execution_locked':False,'host_visibility':'verified'}
        backend=Mock();backend.target_exec.return_value=json.dumps(evidence)
        self.assertEqual(check_idle(backend,{}),evidence)

    def test_active_or_incomplete_evidence_refuses(self):
        cases=[{'user_processes':[{'pid':123}],'gpu_processes':[],'execution_locked':False,'host_visibility':'verified'},
               {'user_processes':[],'gpu_processes':['123'],'execution_locked':False,'host_visibility':'verified'},
               {'user_processes':[],'gpu_processes':[],'execution_locked':True,'host_visibility':'verified'},
               {'user_processes':[],'gpu_processes':[]},
               {'user_processes':[],'gpu_processes':[],'execution_locked':0,'host_visibility':'verified'}]
        for evidence in cases:
            with self.subTest(evidence=evidence):
                backend=Mock();backend.target_exec.return_value=json.dumps(evidence)
                with self.assertRaises(ValueError):check_idle(backend,{})

    def test_unavailable_activity_then_recovery(self):
        backend=Mock();backend.target_exec.side_effect=[TimeoutError('unreachable'),json.dumps({'user_processes':[],'gpu_processes':[],'execution_locked':False,'host_visibility':'verified'})]
        with self.assertRaises(TimeoutError):check_idle(backend,{})
        self.assertFalse(check_idle(backend,{})['execution_locked'])

    def test_root_and_service_account_work_blocks_stop(self):
        for uid in (0,33,999,1000,65534):
            with self.subTest(uid=uid):
                backend=Mock();backend.target_exec.return_value=json.dumps({'user_processes':[{'pid':123,'uid':uid,'name':'work'}],'gpu_processes':[],'execution_locked':False,'host_visibility':'verified'})
                with self.assertRaisesRegex(ValueError,'active or unknown'):
                    check_idle(backend,{})

    def test_restricted_visibility_blocks_even_empty_inventory(self):
        backend=Mock();backend.target_exec.return_value=json.dumps({'user_processes':[],'gpu_processes':[],'execution_locked':False,'host_visibility':'restricted'})
        with self.assertRaisesRegex(ValueError,'visibility'):
            check_idle(backend,{})

    def test_privileged_probe_uses_original_executor_home(self):
        backend=Mock();backend.target_exec.return_value=json.dumps({'user_processes':[],'gpu_processes':[],'execution_locked':False,'host_visibility':'verified'})
        check_idle(backend,{})
        command=backend.target_exec.call_args.args[1]
        self.assertTrue(command.startswith('sudo -n -- python3 -c '))
        self.assertTrue(command.endswith('"$HOME/.local/share/bionemo-rfd4/execution.lock"'))
        self.assertNotIn('Path.home()',PROBE)

    def test_only_verified_system_service_main_process_is_exempt(self):
        import ast, stat
        tree=ast.parse(PROBE)
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='system_process')
        executable=Mock();executable.stat.return_value=Mock(st_uid=0,st_mode=0o100755)
        path=Mock();path.name='42'
        exe=Mock();exe.resolve.return_value=executable
        group=Mock();group.read_text.return_value='0::/system.slice/ssh.service\n'
        path.__truediv__=Mock(side_effect=lambda key:exe if key=='exe' else group)
        resolver=Mock();resolver.resolve.return_value=executable
        namespace={'Path':Mock(return_value=resolver),'stat':stat,'baseline':{42:('ssh.service',['/usr/sbin/sshd'])}}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'activity-probe','exec'),namespace)
        classify=namespace['system_process']
        self.assertTrue(classify(path,0))
        self.assertFalse(classify(path,1000))
        path.name='43';self.assertFalse(classify(path,0));path.name='42'
        group.read_text.return_value='0::/system.slice/research.service\n'
        self.assertFalse(classify(path,0))
        group.read_text.return_value='0::/system.slice/ssh.service\n'
        executable.stat.return_value=Mock(st_uid=0,st_mode=0o100777)
        self.assertFalse(classify(path,0))
        executable.stat.return_value=Mock(st_uid=1000,st_mode=0o100755)
        self.assertFalse(classify(path,0))

    def test_unlinked_executable_is_not_mistaken_for_exited_process(self):
        import ast
        from unittest.mock import MagicMock
        tree=ast.parse(PROBE)
        scan=next(node for node in tree.body if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='path')
        proc=MagicMock();proc.name='123';proc.exists.return_value=True
        status=Mock();status.read_text.return_value='Uid:\t0\t0\t0\t0\nName:\twork\n'
        command=Mock();command.read_bytes.return_value=b'python\x00work.py\x00'
        proc.__truediv__.side_effect=lambda key:status if key=='status' else command
        root=Mock();root.iterdir.return_value=[proc]
        namespace={'Path':Mock(return_value=root),'ancestors':set(),'busy':[],
                   'system_process':Mock(side_effect=FileNotFoundError('deleted executable'))}
        code=compile(ast.Module(body=[scan],type_ignores=[]),'activity-probe','exec')
        with self.assertRaisesRegex(RuntimeError,'Live process'):exec(code,namespace)
        proc.exists.return_value=False
        exec(code,namespace)

if __name__ == "__main__": unittest.main()
