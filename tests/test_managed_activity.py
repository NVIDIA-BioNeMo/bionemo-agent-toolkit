import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
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
