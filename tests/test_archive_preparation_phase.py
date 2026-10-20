import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from prerequisite_review import profile,bind_review
from runtime_setup import setup,SetupCancelled
from runtime_recipe import RECIPE
LEGACY_RECIPE={key:value for key,value in RECIPE.items() if key!='install_mode'}


class PreparationPhaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.operation='prepare-test'
        self.profile=profile();self.name=sorted(self.profile['packages'])[0]
        self.request={'status':'preparation_required','packages':[self.name],
            'download_bytes':int(self.profile['packages'][self.name]['Size']),
            'installation_authorized':False,
            'profile_sha256':hashlib.sha256(json.dumps(self.profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
        self.review={'phase':'prepare_archives','prerequisites':bind_review(self.request)}
        self.run=Mock(side_effect=AssertionError('No model or package process allowed'))
    def execute(self):
        return setup(self.root,recipe=LEGACY_RECIPE,operation_id=self.operation,reviewed=self.review,
                     lock_path=self.root/'execution.lock',run=self.run)
    def test_preparation_never_installs_or_claims_ready(self):
        with patch('toolchain_download.prepare_archives') as fetch:
            result=self.execute()
        self.assertEqual(result['stage'],'archives_prepared')
        self.assertFalse(result['ready'])
        self.assertEqual(result['prepared_packages'],[self.name])
        fetch.assert_called_once();self.run.assert_not_called()
        self.assertFalse((self.root/'model').exists())
    def test_cancelled_preparation_does_not_fetch(self):
        cancel=self.root/'setup-operations'/self.operation/'cancel-requested'
        cancel.parent.mkdir(parents=True);cancel.touch()
        with patch('toolchain_download.prepare_archives') as fetch:
            with self.assertRaises(SetupCancelled):self.execute()
        fetch.assert_not_called()
        self.assertEqual(json.loads((self.root/'runtime-setup.json').read_text())['stage'],'cancelled')
    def test_failed_fetch_retains_unready_journal(self):
        with patch('toolchain_download.prepare_archives',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):self.execute()
        journal=json.loads((self.root/'runtime-setup.json').read_text())
        self.assertEqual(journal['stage'],'needs_attention')
        self.assertFalse(journal['ready'])
        self.run.assert_not_called()
    def test_request_cannot_smuggle_install_changes_or_wrong_size(self):
        for change in ({'changes':{}},{'download_bytes':True},{'download_bytes':0},
                       {'packages':[self.name,self.name]},{'packages':['unreviewed']}):
            with self.assertRaises(ValueError):bind_review(dict(self.request,**change))


if __name__=='__main__':unittest.main()
