"""Durable dispatch boundaries and real independent controller worker leases.

Transport/model effects are counted fixtures, not GPU acceptance.
"""
import json,multiprocessing,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Backend
from service import Service
from executor_ownership import checksum
from ownership_operation import OwnershipRequired
from worker import run_worker
from publication_test_support import publication_reply

class ControllerCrash(BaseException):pass


def concurrent_worker(root,job_id,entered,release,count):
    def execute(backend,cfg,command,timeout=60):
        publication=publication_reply(command)
        if publication is not None:return publication
        if 'mkdir -p' in command:
            entered.set()
            if not release.wait(15):raise TimeoutError('Fixture staging release missing')
        if ' launch-published ' in command:
            with count.get_lock():count.value+=1
            return json.dumps({'job_id':job_id,'state':'accepted'})
        return ''
    with patch.object(Backend,'require_executor_ownership',return_value={}),patch.object(Backend,'target_copy'),patch.object(Backend,'target_exec',execute):
        run_worker(root,job_id)


class WorkerDispatchGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Service(self.temp.name)
        identity=patch('registry.linux_machine_identity',return_value={'linux_machine_id_sha256':'c'*64});identity.start();self.addCleanup(identity.stop)
        self.s.register_compute('local','gpu','/srv/rfd4','http://127.0.0.1:18769',session_id='s');self.machine=self.s.config('s')['target_id']
        owner=self.s.ownership_identity(self.machine)
        with self.s.managed.transaction() as data:data['machines'][self.machine]['executor_ownership']={'owner':owner,'owner_checksum':checksum(owner),'brev':None,'operation_id':'prior'}
        observed=patch.object(self.s,'ownership_status',return_value={'state':'owned','owner':owner,'owner_checksum':checksum(owner)});observed.start();self.addCleanup(observed.stop)
        with patch.object(self.s,'studio',return_value={'cif':'data_fixture\n_atom_site.id 1\n','revision':1,'issues':[]}):self.plan=self.s.prepare('s')
        with patch.object(self.s,'check_compute',return_value={'state':'ready'}),patch('service.subprocess.Popen'):
            self.job=self.s.execute(self.plan['snapshot_id'],self.plan['plan_checksum'])
        self.id=self.job['job_id'];self.directory=self.s.state/self.id

    def test_input_rejection_releases_only_original_run_reservation(self):
        (self.directory/'input.cif').write_text('changed')
        with patch.object(Backend,'target_exec') as command,patch.object(Backend,'target_copy') as copy:
            result=run_worker(self.s.root,self.id)
        command.assert_not_called();copy.assert_not_called()
        self.assertEqual(result['status'],'failed');self.assertTrue(result['dispatch_not_started']);self.assertFalse(result['remote_dispatch_started'])
        self.assertEqual(self.s.managed.snapshot()['reservations'],{})
        self.s.managed.reserve(self.machine,'new-run','run')
        Backend(self.s.root).status(self.id)
        self.assertEqual(self.s.managed.snapshot()['reservations'][self.machine]['owner_id'],'new-run')

    def test_ownership_rejection_has_no_staging_and_frees_undispatched_lease(self):
        with patch.object(Backend,'require_executor_ownership',side_effect=OwnershipRequired('foreign controller')),patch.object(Backend,'target_exec') as command,patch.object(Backend,'target_copy') as copy:
            result=run_worker(self.s.root,self.id)
        command.assert_not_called();copy.assert_not_called();self.assertTrue(result['dispatch_not_started'])
        self.assertEqual(self.s.managed.snapshot()['reservations'],{})

    def test_missing_or_foreign_reservation_is_never_recreated_or_released(self):
        with self.s.managed.transaction() as data:del data['reservations'][self.machine]
        with patch.object(Backend,'target_exec') as command:
            result=run_worker(self.s.root,self.id)
        self.assertEqual(result['status'],'failed');command.assert_not_called()
        self.assertEqual(self.s.managed.snapshot()['reservations'],{})
        self.s.save_job(dict(self.job));self.s.managed.reserve(self.machine,'new-run','run')
        with patch.object(Backend,'target_exec') as command:
            result=run_worker(self.s.root,self.id)
        self.assertEqual(result['status'],'failed');command.assert_not_called()
        self.assertEqual(self.s.managed.snapshot()['reservations'][self.machine]['owner_id'],'new-run')

    def test_restart_after_failure_persistence_reconciles_without_remote_contact(self):
        with patch.object(Backend,'require_executor_ownership',side_effect=OwnershipRequired('foreign controller')),patch.object(Backend,'status',side_effect=ControllerCrash):
            with self.assertRaises(ControllerCrash):run_worker(self.s.root,self.id)
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
        with patch.object(Backend,'target_exec') as command:
            result=Backend(self.s.root).status(self.id)
        command.assert_not_called();self.assertEqual(result['status'],'failed')
        self.assertEqual(self.s.managed.snapshot()['reservations'],{})

    def test_crashes_immediately_before_and_after_launch_never_repeat_or_release(self):
        for after_effect in (False,True):
            with self.subTest(after_effect=after_effect):
                # Restore only this isolated fixture's previously accepted queued
                # record between variants; no real model/provider exists.
                self.s.save_job(dict(self.job));calls=[]
                def execute(backend,cfg,command,timeout=60):
                    publication=publication_reply(command)
                    if publication is not None:return publication
                    if ' launch-published ' in command:
                        saved=backend.read(self.id,'job.json')
                        self.assertEqual(saved['status'],'submitting');self.assertTrue(saved['remote_dispatch_started'])
                        self.assertNotIn('dispatch_not_started',saved)
                        if after_effect:calls.append('remote launch')
                        raise ControllerCrash()
                    return ''
                with patch.object(Backend,'require_executor_ownership',return_value=self.job['executor_ownership']),patch.object(Backend,'target_copy'),patch.object(Backend,'target_exec',execute):
                    with self.assertRaises(ControllerCrash):run_worker(self.s.root,self.id)
                    before=list(calls);result=run_worker(self.s.root,self.id);self.assertEqual(calls,before)
                self.assertEqual(result['status'],'submitting')
                self.assertEqual(len(calls),int(after_effect));self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_independent_worker_process_cannot_duplicate_staging_or_dispatch(self):
        context=multiprocessing.get_context('fork');entered=context.Event();release=context.Event();count=context.Value('i',0)
        process=context.Process(target=concurrent_worker,args=(str(self.s.root),self.id,entered,release,count));process.start()
        try:
            self.assertTrue(entered.wait(10),'Original worker never reached staging')
            result=run_worker(self.s.root,self.id);self.assertEqual(result['worker'],'already_running')
            self.assertEqual(count.value,0)
            release.set();process.join(10);self.assertEqual(process.exitcode,0)
            self.assertEqual(count.value,1)
            self.assertEqual(run_worker(self.s.root,self.id)['status'],'submitted')
            self.assertEqual(count.value,1)
        finally:
            release.set()
            if process.is_alive():process.terminate();process.join(5)

    def test_new_worker_spawn_failure_records_durable_no_dispatch_evidence(self):
        # Another approved plan, after ending this fixture's undispatched lease.
        record=self.s.read(self.id,'job.json');self.s.fail_undispatched(record,'fixture ended');self.s.status(self.id)
        with patch.object(self.s,'studio',return_value={'cif':'data_new\n_atom_site.id 1\n','revision':1,'issues':[]}):plan=self.s.prepare('s')
        with patch.object(self.s,'check_compute',return_value={'state':'ready'}),patch('service.subprocess.Popen',side_effect=OSError('spawn refused')):
            with self.assertRaisesRegex(OSError,'spawn refused'):self.s.execute(plan['snapshot_id'],plan['plan_checksum'])
        failed=self.s.read(plan['snapshot_id'],'job.json')
        self.assertTrue(failed['dispatch_not_started']);self.assertFalse(failed['remote_dispatch_started'])
        self.assertEqual(self.s.managed.snapshot()['reservations'],{})

    def test_explicit_queued_recovery_keeps_original_job_and_uploads_new_attempt_after_crash(self):
        attempts=[];launches=[]
        def execute(backend,cfg,command,timeout=60):
            if 'mkdir -p' in command:attempts.append(command)
            publication=publication_reply(command)
            if publication is not None:
                if len(attempts)==1:raise ControllerCrash('publication acknowledgment lost before dispatch')
                return publication
            if ' launch-published ' in command:
                launches.append(command);return json.dumps({'job_id':self.id,'state':'accepted'})
            return ''
        with patch.object(Backend,'require_executor_ownership',return_value=self.job['executor_ownership']),patch.object(Backend,'target_copy'),patch.object(Backend,'target_exec',execute):
            with self.assertRaises(ControllerCrash):self.s.recover_queued_job(self.id,self.job['plan_checksum'])
            queued=self.s.read(self.id,'job.json')
            self.assertEqual(queued['status'],'queued');self.assertFalse(queued['remote_dispatch_started'])
            self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])
            result=self.s.recover_queued_job(self.id,self.job['plan_checksum'])
            self.assertEqual(result['job_id'],self.id);self.assertEqual(result['status'],'submitted')
            self.assertEqual(len(launches),1);self.assertEqual(len(attempts),2);self.assertNotEqual(*attempts)
            self.assertEqual(self.s.recover_queued_job(self.id,self.job['plan_checksum'])['status'],'submitted')
            self.assertEqual(len(launches),1)

    def test_recovery_wrong_checksum_cannot_modify_job_or_contact_target(self):
        before=(self.directory/'job.json').read_bytes()
        with patch.object(Backend,'target_exec') as remote,patch.object(Backend,'target_copy') as copy:
            with self.assertRaisesRegex(ValueError,'Recovery checksum'):
                self.s.recover_queued_job(self.id,'0'*64)
        remote.assert_not_called();copy.assert_not_called();self.assertEqual((self.directory/'job.json').read_bytes(),before)

    def test_legacy_queued_record_is_unresolved_never_assumed_undispatched(self):
        legacy=dict(self.job);legacy.pop('execution_payload');legacy.pop('remote_dispatch_started')
        self.s.save_job(legacy)
        with patch.object(Backend,'target_exec') as remote,patch.object(Backend,'target_copy') as copy:
            result=self.s.recover_queued_job(self.id,self.job['plan_checksum'])
            self.assertEqual(result['status'],'submission_unknown')
            self.assertNotIn('dispatch_not_started',result)
            self.assertIn('No durable remote dispatch path',self.s.status(self.id)['detail'])
        remote.assert_not_called();copy.assert_not_called()
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_queued_status_and_workspace_explain_recovery_without_exposing_code_or_dispatching(self):
        before=(self.directory/'job.json').read_bytes()
        with patch.object(Backend,'target_exec') as remote,patch.object(Backend,'target_copy') as copy:
            status=self.s.public_job(self.s.status(self.id))
            workspace=self.s.overview()
        remote.assert_not_called();copy.assert_not_called()
        self.assertEqual(status['recovery_action'],'recover_queued_rfd4_job')
        self.assertIn('do not submit another design',status['detail'])
        self.assertEqual(status['machine_name'],'gpu');self.assertEqual(status['machine_id'],self.machine)
        for value in (status,workspace['jobs'][0]):
            self.assertNotIn('execution_payload',value);self.assertNotIn('published_payload',value);self.assertNotIn('target',value)
            self.assertEqual(value['plan_checksum'],self.job['plan_checksum'])
        self.assertNotIn('execution_payload',workspace['plans'][0])
        self.assertEqual((self.directory/'job.json').read_bytes(),before)

    def transport_timeout(self,stage):
        initialized=Backend.__init__;commands=[]
        def run(args,**kwargs):
            command=args[-1];commands.append(command)
            publication=publication_reply(command)
            if publication is not None:
                if stage=='publication':raise subprocess.TimeoutExpired(args,kwargs['timeout'],output='private output',stderr='private stderr')
                return subprocess.CompletedProcess(args,0,publication,'')
            if ' launch-published ' in command:
                raise subprocess.TimeoutExpired(args,kwargs['timeout'],output='private output',stderr='private stderr')
            return subprocess.CompletedProcess(args,0,'','')
        def initialize(backend,*args,**kwargs):
            initialized(backend,*args,**kwargs);backend.runner=run
        with patch.object(Backend,'__init__',initialize),patch.object(Backend,'require_executor_ownership',return_value=self.job['executor_ownership']),patch.object(Backend,'target_copy'):
            result=run_worker(self.s.root,self.id)
        self.assertLess(len(result['error']),250)
        self.assertIn('timed out',result['error'])
        self.assertNotIn('private',result['error']);self.assertNotIn('sources',result['error'])
        self.assertNotIn('BOOTSTRAP',result['error'])
        public=self.s.public_job(result)
        self.assertLess(len(public['error']),250)
        self.assertNotIn('publication_bundle',json.dumps(public))
        return result,commands

    def test_real_publication_timeout_exception_cannot_leak_encoded_source_or_launch(self):
        result,commands=self.transport_timeout('publication')
        self.assertTrue(any(publication_reply(command) is not None for command in commands))
        self.assertFalse(any(' launch-published ' in command for command in commands))
        self.assertEqual(result['status'],'failed');self.assertTrue(result['dispatch_not_started'])
        self.assertEqual(self.s.managed.snapshot()['reservations'],{})

    def test_normalized_launch_timeout_retains_uncertainty_and_original_reservation(self):
        result,commands=self.transport_timeout('launch')
        self.assertTrue(any(' launch-published ' in command for command in commands))
        self.assertEqual(result['status'],'submission_unknown');self.assertTrue(result['remote_dispatch_started'])
        self.assertNotIn('dispatch_not_started',result)
        self.assertIn(self.machine,self.s.managed.snapshot()['reservations'])

    def test_historical_timeout_is_bounded_in_public_view_without_rewriting_record(self):
        legacy=dict(self.job,status='submission_unknown',error=str(subprocess.TimeoutExpired(['ssh','ENCODED-SOURCE-'*10000],180)))
        before=json.dumps(legacy)
        public=self.s.public_job(legacy)
        self.assertLess(len(public['error']),250);self.assertNotIn('ENCODED-SOURCE',public['error'])
        self.assertEqual(json.dumps(legacy),before)

if __name__=='__main__':unittest.main()
