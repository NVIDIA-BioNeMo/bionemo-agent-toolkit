import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from prerequisite_setup import resolve, download_archives, prepare_archives

class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'cache';self.data=b'package'
        self.digest=hashlib.sha256(self.data).hexdigest()
        self.item={'Version':'11','Size':str(len(self.data)),'SHA256':self.digest,'Filename':'pool/gcc.deb','URL':'https://repo.example/pool/gcc.deb'}
        self.profile={'packages':{'gcc':self.item},'download_origins':['https://repo.example']}
        self.tx={'profile_sha256':hashlib.sha256(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                 'changes':{'gcc':{'version':'11','sha256':self.digest,'actions':['Inst','Conf']}}}
        self.run=Mock(return_value=SimpleNamespace(stdout="'https://repo.example/pool/gcc.deb' gcc.deb 7 SHA512:metadata"))
        def fetch(url,path,expected):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(self.data)
        self.download=Mock(side_effect=fetch)
    def go(self,**kwargs):return download_archives(self.profile,self.tx,self.root,run=self.run,download=self.download,**kwargs)
    def test_download_verifies_then_reuses_without_repository(self):
        first=self.go();self.assertEqual(Path(first['gcc']).read_bytes(),self.data)
        self.run.reset_mock();self.download.reset_mock()
        self.assertEqual(self.go(),first);self.run.assert_not_called();self.download.assert_not_called()
    def test_unreviewed_origin_or_path_is_refused(self):
        for url in ('https://other.example/pool/gcc.deb','https://repo.example/other.deb',
                    'https://user:password@repo.example/pool/gcc.deb',
                    'https://repo.example/pool/gcc.deb?token=x',
                    'https://repo.example/pool/gcc.deb#x',
                    'https://repo.example/%2e%2e/pool/gcc.deb'):
            item=dict(self.item,URL=url)
            with self.assertRaises(ValueError):resolve('gcc',item,self.profile['download_origins'],run=self.run)
        self.run.assert_not_called()
    def test_corrupt_download_not_accepted(self):
        self.data=b'corrupt'
        with self.assertRaisesRegex(ValueError,'checksum'):self.go()
    def test_changed_profile_cannot_resolve_or_download(self):
        self.profile['changed']=True
        with self.assertRaisesRegex(ValueError,'profile changed'):self.go()
        self.run.assert_not_called();self.download.assert_not_called()
    def test_cancel_before_download_preserves_no_changes(self):
        cancel=Mock(side_effect=[None,RuntimeError('cancelled')])
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.go(check_cancel=cancel)
        self.download.assert_not_called();self.assertFalse(self.root.exists())
    def test_missing_locator_refused_without_repository_fallback(self):
        item=dict(self.item);del item['URL']
        with self.assertRaisesRegex(ValueError,'pinned package URL'):
            resolve('gcc',item,self.profile['download_origins'],run=self.run)
        self.run.assert_not_called()
    def test_repository_is_never_consulted_on_first_download(self):
        self.run.side_effect=AssertionError('Host has no APT indexes')
        self.go()
        self.run.assert_not_called()
        self.download.assert_called_once()
    def test_preparation_fetches_without_fabricated_install_transaction(self):
        result=prepare_archives(self.profile,['gcc'],self.root,download=self.download)
        self.assertEqual(Path(result['gcc']).read_bytes(),self.data)
        self.assertEqual(self.tx['changes']['gcc']['actions'],['Inst','Conf'])
    def test_empty_preparation_does_not_create_cache(self):
        self.assertEqual(prepare_archives(self.profile,[],self.root,download=self.download),{})
        self.assertFalse(self.root.exists())
        self.download.assert_not_called()
    def test_all_urls_checked_before_any_download(self):
        self.profile['packages']['zzz']=dict(self.item,URL='https://unreviewed.example/pool/gcc.deb')
        with self.assertRaises(ValueError):
            prepare_archives(self.profile,['gcc','zzz'],self.root,download=self.download)
        self.download.assert_not_called()
    def test_cached_archive_does_not_bypass_url_validation(self):
        self.go();self.download.reset_mock()
        self.profile['packages']['gcc']['URL']='file:///pool/gcc.deb'
        with self.assertRaises(ValueError):
            prepare_archives(self.profile,['gcc'],self.root,download=self.download)
        self.download.assert_not_called()
    def test_checksum_valid_symlink_is_not_accepted_as_prepared_archive(self):
        self.root.mkdir()
        target=self.root/'target';target.write_bytes(self.data)
        (self.root/(self.digest+'.deb')).symlink_to(target)
        # A no-op fetch cannot turn a rejected symlink into a valid archive.
        with self.assertRaisesRegex(ValueError,'checksum'):
            prepare_archives(self.profile,['gcc'],self.root,download=lambda *args:None)
    def test_malformed_pinned_urls_are_rejected(self):
        for url in ('',' https://repo.example/pool/gcc.deb',
                    'https://repo.example/pool/gcc.deb\n','ftp://repo.example/pool/gcc.deb'):
            with self.assertRaises(ValueError):
                resolve('gcc',dict(self.item,URL=url),self.profile['download_origins'])
    def test_cancellation_between_archives_preserves_verified_progress(self):
        other=b'other-package'
        self.profile['packages']['zzz']=dict(self.item,Size=len(other),
            SHA256=hashlib.sha256(other).hexdigest())
        cancel=Mock(side_effect=[None,None,None,RuntimeError('cancelled')])
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            prepare_archives(self.profile,['gcc','zzz'],self.root,
                             download=self.download,check_cancel=cancel)
        self.assertEqual((self.root/(self.digest+'.deb')).read_bytes(),self.data)
        self.assertFalse((self.root/(hashlib.sha256(other).hexdigest()+'.deb')).exists())
        def remaining(url,path,expected):
            self.assertEqual(expected['sha256'],hashlib.sha256(other).hexdigest())
            path.write_bytes(other)
        resumed=Mock(side_effect=remaining)
        result=prepare_archives(self.profile,['gcc','zzz'],self.root,download=resumed)
        resumed.assert_called_once()
        self.assertEqual(Path(result['gcc']).read_bytes(),self.data)
        self.assertEqual(Path(result['zzz']).read_bytes(),other)
    def test_interrupted_fetch_cannot_become_prepared(self):
        def interrupted(url,path,expected):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.with_name(path.name+'.part').write_bytes(b'par')
            raise ConnectionError('connection lost')
        with self.assertRaisesRegex(ConnectionError,'connection lost'):
            prepare_archives(self.profile,['gcc'],self.root,download=interrupted)
        self.assertFalse((self.root/(self.digest+'.deb')).exists())
        result=prepare_archives(self.profile,['gcc'],self.root,download=self.download)
        self.assertEqual(Path(result['gcc']).read_bytes(),self.data)

import hashlib,json,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from prerequisite_setup import bind_review, profile, helper_hashes, probe_script

class PrerequisiteReviewTests(unittest.TestCase):
    def result(self):
        return {'profile_sha256':hashlib.sha256(json.dumps(profile(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'installation_authorized':False,'changes':{},'download_bytes':0}
    def test_review_bound_to_profile_and_exact_helpers(self):
        self.assertEqual(bind_review(self.result())['helper_hashes'],helper_hashes())
    def test_wrong_profile_or_false_authorization_rejected(self):
        for changed in ({'profile_sha256':'other'},{'installation_authorized':True},{'download_bytes':True},{'changes':[]}):
            with self.assertRaises(ValueError):bind_review(dict(self.result(),**changed))
    def test_probe_is_self_contained_python(self):
        compile(probe_script(),'<probe>','exec')
        self.assertLess(len(probe_script().encode()),120000)

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

if __name__ == "__main__": unittest.main()
