import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import registry as ssh_transport


class SSHTransportTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'kind': 'brev', 'instance': 'saved-machine',
                    'ssh_access': {'alias': 'saved-machine', 'host': 'verified-endpoint'}}
        self.run = Mock(return_value='ok')
        self.verify = patch('registry.verify_access')
        self.verifier = self.verify.start()
        self.addCleanup(self.verify.stop)

    def assert_secure(self, args):
        for option in ('StrictHostKeyChecking=yes', 'ForwardAgent=no', 'ControlMaster=no', 'ControlPath=none'):
            self.assertIn(option, args)
        self.assertIn('UserKnownHostsFile=' + str(Path.home() / '.ssh/known_hosts'), args)
        self.assertNotIn('brev', args)

    def test_execution_is_direct_and_cannot_start_via_cli_fallback(self):
        self.assertEqual(ssh_transport.execute(self.cfg, 'true', self.run, 15), 'ok')
        self.verifier.assert_called_once_with(self.cfg['ssh_access'], self.run)
        args, timeout = self.run.call_args.args
        self.assertEqual(timeout, 15)
        self.assertEqual(args[0], 'ssh')
        self.assertEqual(args[-3:], ['--', 'saved-machine', 'true'])
        self.assert_secure(args)

    def test_upload_and_download_use_same_safe_transport(self):
        for download, expected in ((False, ['/tmp/payload', 'saved-machine:/srv/parent']),
                                   (True, ['saved-machine:/tmp/payload', '/srv/parent'])):
            with self.subTest(download=download):
                self.run.reset_mock()
                ssh_transport.copy(self.cfg, '/tmp/payload', '/srv/parent', download, self.run, 60)
                args = self.run.call_args.args[0]
                self.assertEqual(args[:2], ['scp', '-r'])
                self.assertEqual(args[-2:], expected)
                self.assert_secure(args)
                self.assertEqual(self.run.call_count, 1)

    def test_unverified_legacy_brev_access_requires_explicit_refresh(self):
        for access in (None,):
            cfg = dict(self.cfg, ssh_access=access)
            with self.assertRaisesRegex(ValueError, 'Refresh and verify'):
                ssh_transport.execute(cfg, 'true', self.run, 15)
            self.run.assert_not_called()

    def test_alias_mismatch_blocks_both_transports_before_execution_or_copy(self):
        for kind in ('ssh', 'brev'):
            cfg = dict(self.cfg, kind=kind, ssh_host='saved-machine', ssh_access={'alias': 'other'})
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, 'different alias'):
                    ssh_transport.execute(cfg, 'true', self.run, 15)
                with self.assertRaisesRegex(ValueError, 'different alias'):
                    ssh_transport.copy(cfg, '/tmp/a', '/srv', False, self.run, 15)
                self.run.assert_not_called()
                self.verifier.assert_not_called()

    def test_identity_drift_prevents_any_remote_command(self):
        self.verifier.side_effect = ValueError('SSH identity changed')
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            ssh_transport.copy(self.cfg, '/tmp/x', '/srv', False, self.run, 60)
        self.run.assert_not_called()

    def test_connection_failure_has_no_refresh_start_or_retry(self):
        for error in (TimeoutError('unreachable'), RuntimeError('Host key verification failed')):
            with self.subTest(error=error):
                self.run.reset_mock()
                self.run.side_effect = error
                with self.assertRaises(type(error)):
                    ssh_transport.execute(self.cfg, 'true', self.run, 15)
                self.assertEqual(self.run.call_count, 1)
                self.assertEqual(self.run.call_args.args[0][0], 'ssh')

    def test_existing_ssh_also_requires_host_verification_without_mux_reuse(self):
        ssh_transport.execute({'kind': 'ssh', 'ssh_host': 'my-host'}, 'true', self.run, 15)
        args = self.run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('ControlPath=none', args)

    def test_only_explicit_brev_refresh_can_remember_a_first_use_key(self):
        ssh_transport.execute(self.cfg,'true',self.run,15,trust_on_first_use=True)
        args=self.run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=accept-new',args)
        self.assertIn('UserKnownHostsFile='+str(Path.home()/'.ssh/known_hosts'),args)
        self.assertNotIn('StrictHostKeyChecking=no',args)
        self.run.reset_mock()
        with self.assertRaisesRegex(ValueError,'only during Brev'):
            ssh_transport.execute({'kind':'ssh','ssh_host':'my-host'},'true',self.run,15,trust_on_first_use=True)
        self.run.assert_not_called()

import tempfile
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
        self.provider=patch('registry.Brev');self.p=self.provider.start().return_value;self.addCleanup(self.provider.stop)
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
        self.assertEqual(self.s.compute_status('session')['state'],'registered')
        self.assertEqual(self.s.local_execution_scope(cfg)['scope'],'dedicated_brev_user')
        self.assertNotIn('executor_ownership',self.s.managed.machine(self.machine))
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
        from registry import lease
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
        from registry import lease
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

"""Standalone registry, isolated selection, durable drafts and safe recovery."""
import json
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import registry

TARGET = {'target_id':'gpu.example','title':'Shared GPU','provider':'ngs-compute',
          'controller_transport':'ssh','executor':'local_process','workspace_access':'remote_filesystem',
          'description':'Existing machine','config_hash':'sha256:'+'a'*64,'host_access':{'alias':'gpu'},
          'workspace_root':'/srv','executor_configuration':{}}

class RegistryContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=Service(self.tmp.name)
        from ownership_test_support import assume_owned
        assume_owned(self,self.s,skip_transport_identity=False)
        recipe=patch('runtime_recipe.inspect',side_effect=lambda backend,cfg: {'checks':dict.fromkeys(['platform','python','revision','source','dependencies','entrypoint','cuda','gpu'],True)|{'weights':bool(cfg['weight_paths'])},'gpus':[{'name':'A100','memory':80*1024**3}], 'details':[]})
        recipe.start();self.addCleanup(recipe.stop)
        machine_identity=patch('registry.linux_machine_identity', side_effect=lambda cfg, run: {'linux_machine_id_sha256': cfg.get('ssh_host', 'local-test-host')})
        machine_identity.start(); self.addCleanup(machine_identity.stop)
        identity=patch('registry.effective_access',side_effect=lambda alias,run: {'alias':alias,'host':alias})
        identity.start();self.addCleanup(identity.stop)
    def register(self, session=None, name='gpu'):
        return self.s.register_compute('ssh',name,'/srv/rfd4','http://127.0.0.1:18765',ssh_host=name,weight_paths=['/weights/model.ckpt'],session_id=session)
    def activate_legacy(self):
        from upgrade_state import upgrade
        old=self.s.root
        destination=tempfile.TemporaryDirectory();self.addCleanup(destination.cleanup)
        def writable():
            for path in [old,*old.rglob('*')]:
                path.chmod(0o700 if path.is_dir() else 0o600)
        self.addCleanup(writable)
        new=Path(destination.name)/'activated'
        upgrade(old,new,old_installation_disabled=True,scan=lambda root:[])
        self.s=Service(new)
    def test_owns_registry_and_selection_without_external_plugin(self):
        self.register()
        self.assertTrue(self.s.available_compute()['available'])
        target_id = self.s.available_compute()['targets'][0]['target_id']
        self.assertNotEqual(target_id, 'gpu')
        with patch.object(self.s,'target_exec',side_effect=AssertionError('no remote execution')):
            self.s.register_registry_compute(target_id,session_id='one')
        self.assertEqual(self.s.compute_status('one')['source'],'BioNeMo')
        self.assertEqual(self.s.config('one')['ssh_host'],'gpu')
    def test_changed_catalog_record_requires_reselection(self):
        self.register('one');cfg=self.s.config('one')
        self.s.register_compute('ssh','gpu','/other','http://127.0.0.1',ssh_host='gpu')
        self.assertNotEqual(cfg['machine_revision'], self.s.config('one')['machine_revision'])
    def test_changed_ssh_alias_rejected_for_old_job(self):
        with patch('registry.effective_access',return_value={'alias':'gpu','host':'different'}):
            with self.assertRaisesRegex(ValueError,'SSH identity changed'):
                self.s.verify_target({'kind':'ssh','registry_target':{'host_access':{'alias':'gpu','host':'original'}}})
    def test_empty_catalog_needs_no_external_environment(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.s.available_compute(),{'available':True,'targets':[],'unresolved':[]})
    def test_migrates_only_owned_config_and_preserves_immutable_job(self):
        cfg={'kind':'ssh','instance':'gpu','remote_root':'/srv/rfd4','studio_url':'http://127.0.0.1',
             'ssh_host':'gpu','registry_target':dict(TARGET,host_access={'alias':'gpu','host':'gpu'})}
        path=self.s.root/'config.json';path.write_text(json.dumps(cfg))
        jobdir=self.s.state/'old';jobdir.mkdir();job=jobdir/'job.json';job.write_text(json.dumps({'job_id':'old','status':'completed','target':cfg}))
        before=job.read_bytes()
        with self.assertRaisesRegex(ValueError,'requires offline upgrade'):self.s.available_compute()
        self.activate_legacy()
        available=self.s.available_compute()
        self.assertEqual(len(available['targets']), 1)
        self.assertEqual(job.read_bytes(),before)
        self.assertTrue((self.s.managed.root/'legacy-backup/config.json').exists())
        self.assertEqual(self.s.compute_status()['state'],'unregistered')
        self.s.register_registry_compute(available['targets'][0]['target_id'])
        self.assertEqual(self.s.config()['registry_target']['host_access'], cfg['registry_target']['host_access'])
    def test_legacy_scheduler_target_cannot_migrate(self):
        cfg={'instance':'gpu','registry_target':dict(TARGET,executor='slurm')}
        (self.s.root/'config.json').write_text(json.dumps(cfg))
        self.activate_legacy()
        self.assertIn('scheduler', self.s.available_compute()['unresolved'][0]['reason'])
    def test_migration_preserves_distinct_session_targets_with_same_name(self):
        for name,host in [('a','host-a'),('b','host-b')]:
            cfg={'kind':'ssh','instance':'gpu','remote_root':'/srv','studio_url':'http://127.0.0.1','ssh_host':host,'ssh_access':{'alias':host,'host':host}}
            self.s.compute_config_path(name).write_text(json.dumps(cfg))
        self.activate_legacy()
        self.s.available_compute()
        self.assertNotEqual(self.s.managed.selection('a')['previous_machine_id'], self.s.managed.selection('b')['previous_machine_id'])
        self.assertIsNone(self.s.managed.selection('a')['machine_id'])
    def test_missing_editor_has_actionable_error(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'CPU editor is not configured'): self.s.studio_url()
    def test_inspection_is_connection_only(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='') as execute:
            self.assertTrue(self.s.inspect_compute_target(self.s.config()['target_id'])['connected'])
            self.assertEqual(execute.call_args.args[1],'true')
        with patch.object(self.s,'target_exec',side_effect=RuntimeError('offline')):
            self.assertFalse(self.s.inspect_compute_target(self.s.config()['target_id'])['connected'])
    def test_session_selection_isolated_from_global_default(self):
        self.register('one')
        first=self.s.config('one')
        self.register(name='different')
        self.assertEqual(self.s.config('one'),first)
        self.assertEqual(self.s.compute_status('two')['state'],'unregistered')
    def test_failed_connection_not_model_setup(self):
        self.register()
        with patch.object(self.s,'target_exec',side_effect=RuntimeError('Connection refused')):
            self.assertEqual(self.s.check_compute()['state'],'disconnected')
        with patch.object(self.s,'target_exec',return_value=''), patch('runtime_recipe.inspect',side_effect=RuntimeError('Runtime missing')):
            self.assertEqual(self.s.check_compute()['state'],'needs_setup')
    def test_gpu_readiness_independent_of_editor(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='A100'),patch.object(self.s,'studio',side_effect=AssertionError('editor must be separate')):
            self.assertEqual(self.s.check_compute()['state'],'ready')
    def test_old_check_cannot_show_ready_forever(self):
        self.register()
        with patch.object(self.s,'target_exec',return_value='A100'): self.s.check_compute()
        p=next(self.s.root.glob('compute-check-*.json'))
        value=json.loads(p.read_text());value['checked_at']='2000-01-01T00:00:00+00:00';p.write_text(json.dumps(value))
        self.assertEqual(self.s.compute_status()['state'],'registered')
    def test_cpu_editor_and_incomplete_draft_work_without_compute(self):
        with patch.dict(os.environ,{'RFD4_EDITOR_URL':'http://127.0.0.1:18765'}):
            self.assertEqual(self.s.studio_url(),'http://127.0.0.1:18765')
        export={'cif':'data_draft\n_atom_site.id 1','revision':3,'issues':[{'severity':'error'}]}
        with patch.object(self.s,'studio',return_value=export):
            draft=self.s.save_draft('draft','Keep these hotspots',settings={'seed':42})
        # Recreate backend as after process restart.
        other=Service(self.tmp.name)
        self.assertEqual(other.list_drafts()['drafts'][0]['revision'],3)
        with patch.object(other,'import_cif',return_value={'session_id':'restored'}) as imp:
            result=other.restore_draft(draft['draft_id'])
        imp.assert_called_once_with(export['cif'])
        self.assertEqual(result['note'],'Keep these hotspots')
        self.assertEqual(result['settings']['seed'],42)
    def test_poll_original_job_after_target_switch(self):
        self.register();cfg=self.s.config()
        directory=self.s.state/'job';directory.mkdir()
        self.s.save_job({'job_id':'job','instance':'gpu','target':cfg,'status':'submitted','remote_dir':'/srv/runs/job'})
        self.register(name='different')
        with patch.object(self.s,'target_exec',return_value='RUNNING') as execute:
            self.assertEqual(self.s.status('job')['status'],'running')
        self.assertEqual(execute.call_args.args[0],cfg)
    def test_setup_requests_are_idempotent_and_cannot_claim_readiness(self):
        first=self.s.begin_setup('one')
        self.assertEqual(first,self.s.begin_setup('one'))
        self.assertEqual(self.s.compute_operation(first['id'])['operation']['state'], 'requested')
        self.assertEqual(self.s.compute_status('one')['state'],'unregistered')
        self.s.managed.cancel(first['id'])
        second=self.s.begin_setup('one')
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(second['state'],'requested')
    def test_submission_rechecks_readiness_and_retries_existing_job(self):
        self.register('one')
        exported={'cif':'data_draft\n_atom_site.id 1','revision':3,'issues':[]}
        with patch.object(self.s,'studio',return_value=exported): plan=self.s.prepare('one')
        with patch.object(self.s,'check_compute',return_value={'state':'disconnected','detail':'offline'}),patch('service.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'not ready'): self.s.execute(plan['snapshot_id'],plan['plan_checksum'])
            spawn.assert_not_called()
        with patch.object(self.s,'check_compute',return_value={'state':'ready'}),patch('service.subprocess.Popen') as spawn:
            job=self.s.execute(plan['snapshot_id'],plan['plan_checksum'])
        self.register('one',name='different')
        with patch.object(self.s,'check_compute',side_effect=AssertionError('Do not recheck or resubmit an existing job')):
            self.assertEqual(self.s.execute(plan['snapshot_id'],plan['plan_checksum']),job)

class SSHIdentityContract(unittest.TestCase):
    def test_resolution_is_local_and_tracks_transport_changes(self):
        from unittest.mock import Mock
        output='hostname gpu.example\nuser ubuntu\nport 22\nstricthostkeychecking true\nidentityfile /keys/one\n'
        run=Mock(return_value=output)
        first=registry.effective_access('gpu',run)
        self.assertEqual(run.call_args.args[0],['ssh','-G','-o','BatchMode=yes','--','gpu'])
        run.return_value=output.replace('/keys/one','/keys/two')
        with self.assertRaisesRegex(ValueError,'SSH identity changed'): registry.verify_access(first,run)

if __name__ == "__main__": unittest.main()
