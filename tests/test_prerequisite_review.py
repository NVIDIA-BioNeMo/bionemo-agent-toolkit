import hashlib,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from prerequisite_review import bind_review,profile,helper_hashes,probe_script

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
