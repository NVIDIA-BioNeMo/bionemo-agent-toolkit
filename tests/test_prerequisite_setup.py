import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from prerequisite_setup import install_prerequisites

class PrerequisiteCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.profile={'status':'qualified','packages':{}}
        self.tx={'profile_sha256':self.digest(self.profile),'helper_hashes':{},'changes':{'gcc':{'version':'11'}}}
        self.receipt={'job_id':'job','transaction_sha256':self.digest(self.tx),'state':'succeeded'}
        self.actions=[];self.cancel=Mock();self.downloader=Mock(return_value={});self.journal=Mock();self.sleep=Mock()
    def digest(self,v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def invoke(self,privileged=None,**options):
        def adapter(action,*args):self.actions.append(action);return self.receipt
        with patch('prerequisite_setup.Path.read_text',return_value=json.dumps(self.profile)):
            return install_prerequisites(self.tmp.name,'job',{'prerequisites':self.tx},privileged=privileged or adapter,journal=self.journal,check_cancel=self.cancel,download=self.downloader,review=lambda p:{k:v for k,v in self.tx.items() if k!='helper_hashes'},sleep=self.sleep,**options)
    def test_normal_stage_dispatches_once_then_returns_verified_receipt(self):
        self.assertEqual(self.invoke(),self.receipt)
        self.assertEqual(self.actions,['publish','launch','observe'])
    def test_conforming_host_never_uses_privileged_adapter(self):
        self.tx['changes']={}
        self.assertEqual(self.invoke()['state'],'not_needed');self.assertFalse(self.actions)
        self.downloader.assert_not_called()
    def test_unqualified_profile_cannot_mutate_packages(self):
        self.profile['status']='candidate_not_qualified';self.tx['profile_sha256']=self.digest(self.profile)
        with self.assertRaisesRegex(ValueError,'qualification'):self.invoke()
        self.assertFalse(self.actions);self.downloader.assert_not_called()
    def test_lost_launch_acknowledgment_is_not_retried_or_fenced(self):
        def adapter(action,*args):
            self.actions.append(action)
            if action=='launch':raise TimeoutError('ack lost')
        with self.assertRaises(TimeoutError):self.invoke(adapter)
        self.assertEqual(self.actions,['publish','launch'])
    def test_cancel_after_publication_fences_without_launch(self):
        self.cancel.side_effect=[None,None,RuntimeError('cancelled')]
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.invoke()
        self.assertEqual(self.actions,['publish','fence'])
    def test_active_stage_finishes_before_cancellation_is_applied(self):
        self.cancel.side_effect=[None,None,None,RuntimeError('cancelled')]
        count=0
        def adapter(action,*args):
            nonlocal count
            self.actions.append(action)
            if action=='observe':
                count+=1
                return dict(self.receipt,state='running' if count==1 else 'succeeded')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.invoke(adapter)
        self.assertEqual(self.actions,['publish','launch','observe','observe']);self.sleep.assert_called_once_with(2)
    def test_wrong_receipt_or_failed_stage_cannot_continue_runtime(self):
        self.receipt['job_id']='other'
        with self.assertRaisesRegex(ValueError,'identity'):self.invoke()
        self.receipt.update(job_id='job',state='failed')
        with self.assertRaisesRegex(ValueError,'installation failed'):self.invoke()

    def test_missing_worker_receipt_is_bounded_without_redispatch(self):
        self.receipt['state']='pending'
        with self.assertRaisesRegex(TimeoutError,'unconfirmed'):self.invoke()
        self.assertEqual(self.actions.count('launch'),1)
        self.assertEqual(self.actions.count('observe'),60)
        self.assertNotIn('fence',self.actions)

    def test_local_intent_precedes_uncertain_root_publication(self):
        events=[]
        def adapter(action,*args):
            events.append(action)
            if action=='publish':raise TimeoutError('publication acknowledgement lost')
        with self.assertRaises(TimeoutError):
            self.invoke(adapter,publication_started=lambda:events.append('local_intent'))
        self.assertEqual(events,['local_intent','publish'])

    def test_local_receipt_failure_does_not_repeat_installation(self):
        recorder=Mock(side_effect=OSError('local receipt disk error'))
        with self.assertRaises(OSError):self.invoke(record_terminal=recorder)
        self.assertEqual(self.actions,['publish','launch','observe'])
        recorder.assert_called_once_with(self.receipt)
