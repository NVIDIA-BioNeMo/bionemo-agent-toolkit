import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from source_stage import stage

class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.upstream=self.root/'upstream';self.upstream.mkdir()
        self.git('init','-q');(self.upstream/'model.py').write_text('pinned=True\n')
        self.git('add','model.py');self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','source')
        self.revision=self.git('rev-parse','HEAD').strip()
        self.recipe={'model_revision':self.revision,'model_repository':'https://github.com/example/model.git'}
        self.destination=self.root/'runtime';self.calls=[]
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.upstream),*args],text=True)
    def runner(self,args,**kwargs):
        self.calls.append(args)
        # Use a real local Git transport for fetch/checkout fault tests.
        if 'fetch' in args:
            args=[str(self.upstream) if arg=='origin' else arg for arg in args]
        return subprocess.run(args,**kwargs)
    def test_stage_and_repeat_preserve_exact_source(self):
        model=stage(self.destination,self.recipe,run=self.runner)
        self.assertEqual((model/'model.py').read_text(),'pinned=True\n')
        count=len([args for args in self.calls if 'fetch' in args])
        self.assertEqual(stage(self.destination,self.recipe,run=self.runner),model)
        self.assertEqual(len([args for args in self.calls if 'fetch' in args]),count)
    def test_failed_fetch_publishes_no_partial_model_and_can_retry(self):
        def failed(args,**kwargs):
            if 'fetch' in args:raise subprocess.CalledProcessError(128,args,stderr='secret credential detail')
            return self.runner(args,**kwargs)
        with self.assertRaisesRegex(ValueError,'repository access') as error:stage(self.destination,self.recipe,run=failed)
        self.assertNotIn('secret',str(error.exception))
        self.assertFalse((self.destination/'model').exists())
        self.assertEqual(list(self.destination.glob('.source-stage-*')),[])
        self.assertTrue(stage(self.destination,self.recipe,run=self.runner).is_dir())
    def test_modified_existing_checkout_is_preserved(self):
        model=stage(self.destination,self.recipe,run=self.runner);(model/'model.py').write_text('user edit\n')
        with self.assertRaisesRegex(ValueError,'differs'):stage(self.destination,self.recipe,run=self.runner)
        self.assertEqual((model/'model.py').read_text(),'user edit\n')
    def test_symlink_checkout_refused(self):
        self.destination.mkdir();(self.destination/'model').symlink_to(self.upstream,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symbolic'):stage(self.destination,self.recipe,run=self.runner)
        self.assertEqual(self.calls,[])
    def test_repository_credentials_never_enter_command(self):
        recipe=dict(self.recipe,model_repository='https://secret@github.com/example/model.git')
        with self.assertRaisesRegex(ValueError,'credential-free'):stage(self.destination,recipe,run=self.runner)
        self.assertEqual(self.calls,[])
    def test_wrong_revision_never_publishes(self):
        recipe=dict(self.recipe,model_revision='f'*40)
        with self.assertRaises(ValueError):stage(self.destination,recipe,run=self.runner)
        self.assertFalse((self.destination/'model').exists())
    def test_empty_destination_created_at_publication_is_not_replaced(self):
        from unittest.mock import patch
        from source_stage import publish
        def competing(source,destination):
            destination.mkdir()
            return publish(source,destination)
        with patch('source_stage.publish',side_effect=competing):
            with self.assertRaises(FileExistsError):stage(self.destination,self.recipe,run=self.runner)
        self.assertEqual(list((self.destination/'model').iterdir()),[])
