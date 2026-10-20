import hashlib
import sys
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_review import local_archive_proposal


class LocalProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.archive=Path(self.tmp.name)/'test.deb';self.archive.write_bytes(b'fixture')
        self.profile={'packages':{'test':{'Package':'test','Version':'1','Architecture':'all',
            'Size':7,'SHA256':hashlib.sha256(b'fixture').hexdigest()}}}
        self.control='Package: test\nVersion: 1\nArchitecture: all\n'
        self.output='Inst test (1 local [all])\nConf test (1 local [all])'
        self.calls=[]
    def run_command(self,args,**kwargs):
        self.calls.append(args)
        if args[0]=='dpkg-deb':return SimpleNamespace(stdout=self.control)
        self.assertEqual(args[0],'apt-get')
        self.assertIn('--simulate',args)
        self.assertNotIn('update',args)
        self.assertNotIn('-y',args)
        config=Path(kwargs['env']['APT_CONFIG'])
        self.assertIn('Dir::Etc::parts',config.read_text())
        self.assertIn('Dir::Etc::main',config.read_text())
        self.assertEqual((config.parent/'sources.list').read_text(),'')
        self.assertEqual(list((config.parent/'sources').iterdir()),[])
        self.assertEqual(list((config.parent/'lists').iterdir()),[])
        return SimpleNamespace(stdout=self.output+'\nDiagnostic path: '+str(config.parent))
    def proposal(self):
        return local_archive_proposal(self.profile,{'test':self.archive},run=self.run_command)
    def test_exact_archives_and_isolated_simulation(self):
        result=self.proposal()
        self.assertEqual(result['effects']['test'],{'version':'1','actions':['Inst','Conf']})
        self.assertEqual(len(self.calls),2)
    def test_bad_bytes_refused_before_subprocess(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'checksum'):self.proposal()
        self.assertEqual(self.calls,[])
    def test_wrong_control_identity_refused_before_solver(self):
        self.control=self.control.replace('Version: 1','Version: 2')
        with self.assertRaisesRegex(ValueError,'control identity'):self.proposal()
        self.assertEqual(len(self.calls),1)
    def test_unreviewed_solver_effect_refused(self):
        self.output='Inst other (2 local [all])'
        with self.assertRaisesRegex(ValueError,'Unreviewed'):self.proposal()
    def test_different_temporary_paths_preserve_canonical_effects(self):
        first=self.proposal();second=self.proposal()
        self.assertEqual(first['effects'],second['effects'])
        self.assertNotEqual(first['diagnostic_sha256'],second['diagnostic_sha256'])
    def test_removal_and_purge_are_rejected(self):
        for action in ('Remv','Purg'):
            self.output=action+' other [1]'
            with self.assertRaisesRegex(ValueError,'must not remove'):self.proposal()
    def test_wrong_or_malformed_control_fields_are_rejected(self):
        for control in ('Package: other\nVersion: 1\nArchitecture: all\n',
                        'Package: test\nVersion: 1\nArchitecture: arm64\n',
                        self.control+'Package: test\n','not a control field'):
            self.control=control
            with self.assertRaises(ValueError):self.proposal()
    def test_symlink_archive_rejected_before_commands(self):
        original=self.archive
        self.archive=original.with_name('link.deb');self.archive.symlink_to(original)
        with self.assertRaisesRegex(ValueError,'regular file'):self.proposal()
        self.assertEqual(self.calls,[])
    def test_caller_environment_is_not_inherited(self):
        original=self.run_command
        def check(args,**kwargs):
            self.assertNotIn('LD_PRELOAD',kwargs['env'])
            self.assertNotEqual(kwargs['env'].get('APT_CONFIG'),'/tmp/injected')
            return original(args,**kwargs)
        with patch.dict(os.environ,{'APT_CONFIG':'/tmp/injected','LD_PRELOAD':'/tmp/injected.so'}):
            local_archive_proposal(self.profile,{'test':self.archive},run=check)


if __name__=='__main__':unittest.main()
