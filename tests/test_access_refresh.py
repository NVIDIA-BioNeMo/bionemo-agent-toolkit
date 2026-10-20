from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import nullcontext
import subprocess
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service


class AccessRefreshTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.s=Service(tmp.name)
        self.s.register_compute('brev','saved','/srv/rfd4','http://127.0.0.1',instance_id='fixed',organization_id='org',session_id='session')
        self.machine=self.s.config('session')['target_id']
        self.op=self.s.begin_setup('session',self.machine)['id']
        self.before=self.s.managed.snapshot()
        self.access={'alias':'saved','host':'trusted-endpoint','user':'ubuntu','port':22}
        self.commands=[]
        self.row={'id':'fixed','name':'saved','status':'RUNNING'}
        self.provider=patch('access_refresh.Brev');self.p=self.provider.start().return_value;self.addCleanup(self.provider.stop)
        self.p.current_org.return_value='org';self.p.check_context.side_effect=lambda *a: dict(self.row)
        self.resolver=patch('registry.effective_access',side_effect=lambda *a: dict(self.access));self.resolver.start();self.addCleanup(self.resolver.stop)
        self.runner=patch.object(self.s,'run',side_effect=self.remote);self.runner.start();self.addCleanup(self.runner.stop)

    def remote(self,args,timeout=60,**kwargs):
        self.commands.append(args)
        if args==['brev','refresh']:return 'refreshed'
        if args[0]=='ssh':return '1'*32
        raise AssertionError(args)

    def execute(self):return self.s.refresh_compute_access(self.op,self.machine)

    def test_refresh_accepts_same_trusted_snapshot_and_invalidates_readiness(self):
        before_cfg=self.s.config('session')
        result=self.execute()
        self.assertEqual(result['state'],'succeeded')
        cfg=self.s.config('session')
        self.assertEqual(cfg['ssh_access'],self.access)
        self.assertGreater(cfg['machine_revision'],before_cfg['machine_revision'])
        # Refreshing transport does not establish a machine ownership claim.
        self.assertEqual(self.s.compute_status('session')['state'],'ownership_required')
        self.assertEqual(self.s.managed.selection('session'),self.before['sessions']['session'])
        self.assertEqual(self.commands[0],['brev','refresh'])
        self.assertEqual([c[0] for c in self.commands],['brev','ssh'])
        self.assertIn('StrictHostKeyChecking=accept-new',self.commands[1])
        self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
        self.execute()
        self.assertEqual(len(self.commands),2)

    def test_stopped_or_renamed_machine_cannot_refresh_or_start(self):
        for change in ({'status':'STOPPED'},{'name':'different'}):
            self.row.update(change)
            with self.assertRaisesRegex(ValueError,'running with its verified name'):self.execute()
            self.assertEqual(self.commands,[])
            self.row={'id':'fixed','name':'saved','status':'RUNNING'}

    def test_selected_machine_refresh_reuses_the_existing_reserved_access_flow(self):
        result=self.s.refresh_selected_compute_access('session',self.s.managed.selection('session')['revision'])
        self.assertEqual(result['id'],self.op)
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual([c[0] for c in self.commands],['brev','ssh'])

    def test_selected_machine_refresh_rejects_a_stale_session_before_any_command(self):
        with self.assertRaisesRegex(ValueError,'selection changed'):
            self.s.refresh_selected_compute_access('session',0)
        self.assertEqual(self.commands,[])

    def test_wrong_organization_does_not_switch_context(self):
        self.p.current_org.return_value='another'
        with self.assertRaisesRegex(ValueError,'saved Brev organization'):self.execute()
        self.assertEqual(self.commands,[])

    def test_rejected_changed_key_preserves_config_and_never_replaces_key(self):
        def reject(args,timeout=60,**kwargs):
            self.commands.append(args)
            if args[0]=='ssh':raise RuntimeError('Host key verification failed')
            return ''
        self.s.run.side_effect=reject
        with self.assertRaisesRegex(RuntimeError,'Host key verification failed'):self.execute()
        after=self.s.managed.snapshot()
        self.assertEqual(after['machines'],self.before['machines'])
        self.assertEqual(after['sessions'],self.before['sessions'])
        self.assertEqual(after['operations'][self.op]['state'],'failed')
        self.assertEqual(after['reservations'],{})
        self.assertEqual([c[0] for c in self.commands],['brev','ssh'])

    def test_physical_identity_change_is_not_accepted(self):
        self.s.managed.bind_physical_identity(self.machine,{'linux_machine_id_sha256':'original'})
        cfg=self.s.config('session')
        with self.assertRaisesRegex(ValueError,'Physical machine identity changed'):self.execute()
        self.assertEqual(self.s.config('session'),cfg)

    def test_changed_alias_after_probe_cannot_be_stored(self):
        count=0
        def resolve(*args):
            nonlocal count
            count+=1
            return dict(self.access,host='changed') if count>=3 else dict(self.access)
        with patch('registry.effective_access',side_effect=resolve):
            with self.assertRaisesRegex(ValueError,'SSH identity changed'):self.execute()
        self.assertEqual(self.s.managed.snapshot()['machines'],self.before['machines'])

    def test_selection_change_during_refresh_cannot_commit(self):
        def race(args,timeout=60,**kwargs):
            if args==['brev','refresh']:
                self.s.disconnect_compute('session',1)
                return ''
            return '1'*32
        self.s.run.side_effect=race
        with self.assertRaisesRegex(ValueError,'changed or was cancelled'):self.execute()
        self.assertEqual(self.s.managed.snapshot()['machines'],self.before['machines'])
        self.assertIsNone(self.s.managed.selection('session')['machine_id'])

    def test_pending_run_blocks_refresh_without_any_remote_command(self):
        with patch.object(self.s,'machine_jobs',return_value={'active_jobs':['job'],'unresolved_active_jobs':[]}):
            with self.assertRaisesRegex(ValueError,'active or unknown'):self.execute()
        self.assertEqual(self.commands,[])

    def test_crash_boundaries_recover_without_repeating_refresh(self):
        for boundary in ('before_refresh','after_refresh','before_commit'):
            with self.subTest(boundary=boundary):
                # Each crash belongs to a fresh durable operation.
                if self.s.managed.operation(self.op)['state'] in ('failed','succeeded'):
                    self.op=self.s.begin_setup('session',self.machine)['id']
                def crash(args,timeout=60,**kwargs):
                    if args==['brev','refresh']:
                        if boundary=='before_refresh':raise SystemExit('controller died before CLI')
                        self.commands.append(args)
                        if boundary=='after_refresh':raise SystemExit('controller died after CLI')
                        return ''
                    return self.remote(args,timeout)
                self.s.run.side_effect=crash
                commit=patch.object(type(self.s.managed),'accept_access',side_effect=SystemExit('before commit')) if boundary=='before_commit' else nullcontext()
                with commit:
                    with self.assertRaises(SystemExit):self.execute()
                self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
                commands=list(self.commands)
                with self.assertRaisesRegex(ValueError,'Recover the original'):self.execute()
                result=self.s.recover_compute_access(self.op)
                self.assertEqual(result['state'],'failed')
                self.assertEqual(self.commands,commands)
                self.assertEqual(self.s.managed.snapshot()['machines'],self.before['machines'])
                self.assertNotIn(self.machine,self.s.managed.snapshot()['reservations'])
                self.assertEqual(self.s.recover_compute_access(self.op),result)

    def test_recovery_refuses_while_original_controller_holds_lease(self):
        from access_refresh import lease
        with lease(self.s,self.op):
            with self.assertRaisesRegex(ValueError,'still running'):
                self.s.recover_compute_access(self.op)
        self.assertEqual(self.commands,[])

    def test_cancellation_after_cli_prevents_ssh_and_access_commit(self):
        def cancel(args,timeout=60,**kwargs):
            self.commands.append(args)
            if args==['brev','refresh']:
                self.s.managed.cancel(self.op)
                return ''
            raise AssertionError('No SSH after cancellation')
        self.s.run.side_effect=cancel
        with self.assertRaisesRegex(ValueError,'cancelled'):self.execute()
        self.assertEqual(self.commands,[['brev','refresh']])
        self.assertEqual(self.s.managed.snapshot()['machines'],self.before['machines'])

    def test_cli_child_inherits_lease_after_controller_handle_closes(self):
        from access_refresh import lease
        with lease(self.s,self.op) as handle:
            child=subprocess.Popen([sys.executable,'-c','import sys; print("ready",flush=True); sys.stdin.read()'],
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,pass_fds=(handle.fileno(),))
            self.assertEqual(child.stdout.readline().strip(),'ready')
        try:
            with self.assertRaisesRegex(ValueError,'still running'):
                self.s.recover_compute_access(self.op)
        finally:
            child.communicate('',timeout=5)
        # The original was never dispatched; observing a free lease cannot
        # invent a completed refresh or accept new access.
        with self.assertRaisesRegex(ValueError,'has not started'):
            self.s.recover_compute_access(self.op)


if __name__=='__main__':unittest.main()
