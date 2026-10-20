import sys,tempfile,unittest
import os,hashlib
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_review import review, package_configuration, PreparationRequired

class ToolchainReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.os=Path(self.tmp.name)/'os-release';self.os.write_text('ID=ubuntu\nVERSION_ID="22.04"\n')
        self.archive=Path(self.tmp.name)/'gcc.deb';self.archive.write_bytes(b'0123456789')
        self.item={'Package':'gcc','Version':'11','Architecture':'amd64','Size':'10','SHA256':hashlib.sha256(self.archive.read_bytes()).hexdigest()}
        self.profile={'packages':{'gcc':self.item},'qualified_package_configuration':{'fixture':'configuration'}}
        self.calls=[];self.environments=[];self.audit='';self.inventory='';self.proposal='Inst gcc (11 Ubuntu [amd64])\nConf gcc (11 Ubuntu [amd64])'
        self.metadata='\n'.join(k+': '+self.item[k] for k in ('Package','Version','Architecture'));self.comparison=1
    def fake_run(self,args,**kwargs):
        self.calls.append(args)
        self.environments.append(kwargs['env'])
        if args[:2]==['dpkg','--print-architecture']:out='amd64'
        elif args[:2]==['dpkg','--audit']:out=self.audit
        elif args[0]=='dpkg-query':out=self.inventory
        elif args[:2]==['dpkg','--compare-versions']:return SimpleNamespace(returncode=self.comparison,stdout='')
        elif args[0]=='apt-get':
            self.assertIn('--simulate',args);out=self.proposal
        elif args[0]=='dpkg-deb':out=self.metadata
        else:raise AssertionError(args)
        return SimpleNamespace(stdout=out,returncode=0)
    def check(self):return review(self.profile,run=self.fake_run,os_release=self.os,configuration=lambda:{'fixture':'configuration'},archives={} if self.inventory=='gcc\tinstall ok installed\t11' else {'gcc':self.archive})
    def test_missing_package_review_is_nonmutating(self):
        result=self.check();self.assertEqual(result['download_bytes'],10)
        self.assertIsNone(result['changes']['gcc']['previous_version'])
        self.assertFalse(result['installation_authorized'])
        self.assertEqual(result['package_configuration'],{'fixture':'configuration'})
        self.assertFalse(any(a[0]=='sudo' for a in self.calls))
    def test_conforming_machine_is_noop(self):
        self.inventory='gcc\tinstall ok installed\t11';self.proposal='0 upgraded, 0 newly installed, 0 to remove.'
        self.assertEqual(self.check()['changes'],{})
        self.assertFalse(any(args[0] in ('apt-get','apt-cache','dpkg-deb') for args in self.calls))
    def test_missing_cache_requires_preparation_without_solver_or_download(self):
        with patch('toolchain_review.Path.home',return_value=Path(self.tmp.name)):
            with self.assertRaises(PreparationRequired) as caught:
                review(self.profile,run=self.fake_run,os_release=self.os,
                       configuration=lambda:{'fixture':'configuration'})
        self.assertEqual(caught.exception.packages,['gcc'])
        self.assertEqual(caught.exception.download_bytes,10)
        self.assertFalse(any(args[0] in ('apt-get','apt-cache','dpkg-deb') for args in self.calls))
    def test_prepared_set_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Prepared package set differs'):
            review(self.profile,run=self.fake_run,os_release=self.os,
                   configuration=lambda:{'fixture':'configuration'},archives={})
    def test_corrupt_cache_requires_preparation_then_valid_cache_reviews(self):
        cache=Path(self.tmp.name)/'.cache/bionemo-rfd4/packages'
        cache.mkdir(parents=True)
        archive=cache/(self.item['SHA256']+'.deb')
        archive.write_bytes(b'bad bytes!')
        with patch('toolchain_review.Path.home',return_value=Path(self.tmp.name)):
            with self.assertRaises(PreparationRequired):
                review(self.profile,run=self.fake_run,os_release=self.os,
                       configuration=lambda:{'fixture':'configuration'})
            archive.write_bytes(self.archive.read_bytes())
            result=review(self.profile,run=self.fake_run,os_release=self.os,
                          configuration=lambda:{'fixture':'configuration'})
        self.assertEqual(result['changes']['gcc']['actions'],['Inst','Conf'])
    def test_unchanged_but_unqualified_configuration_is_refused(self):
        self.profile['qualified_package_configuration']={'other':'configuration'}
        with self.assertRaisesRegex(ValueError,'not qualified'):self.check()
        self.assertEqual(self.calls,[])
    def test_review_ignores_caller_package_configuration(self):
        with patch.dict(os.environ,{'APT_CONFIG':'/tmp/injected.conf','PATH':'/tmp/bin',
                                   'LD_LIBRARY_PATH':'/tmp/lib'}):
            self.check()
        self.assertTrue(self.environments)
        for env in self.environments:
            self.assertEqual(env['PATH'],'/usr/sbin:/usr/bin:/sbin:/bin')
            if 'APT_CONFIG' in env:self.assertIn('rfd4-package-proposal-',env['APT_CONFIG'])
            self.assertNotIn('LD_LIBRARY_PATH',env)
    def test_dirty_package_state_prevents_solver(self):
        self.audit='gcc requires configuration'
        with self.assertRaisesRegex(ValueError,'needs repair'):self.check()
        self.assertFalse(any(a[0]=='apt-get' for a in self.calls))
    def test_downgrade_refused_before_solver(self):
        self.inventory='gcc\tinstall ok installed\t12';self.comparison=0
        with self.assertRaisesRegex(ValueError,'downgrade'):self.check()
        self.assertFalse(any(a[0]=='apt-get' for a in self.calls))
    def test_changed_artifact_rejected_then_recovery(self):
        self.metadata=self.metadata.replace('Version: 11','Version: 12')
        with self.assertRaisesRegex(ValueError,'control identity differs'):self.check()
        self.metadata=self.metadata.replace('Version: 12','Version: 11')
        self.assertEqual(self.check()['download_bytes'],10)
    def test_wrong_os_makes_no_commands(self):
        self.os.write_text('ID=debian\nVERSION_ID="12"\n')
        with self.assertRaisesRegex(ValueError,'Ubuntu'):self.check()
        self.assertEqual(self.calls,[])

    def test_solver_cannot_omit_missing_required_package(self):
        self.proposal='0 upgraded, 0 newly installed, 0 to remove.'
        with self.assertRaisesRegex(ValueError,'omitted required'):self.check()

    def test_configuration_only_cannot_replace_required_installation(self):
        self.proposal='Conf gcc (11 Ubuntu [amd64])'
        with self.assertRaisesRegex(ValueError,'omitted required'):self.check()


class PackageConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for path in ('etc/dpkg/dpkg.cfg.d','usr/lib/needrestart'):
            (self.root/path).mkdir(parents=True)
        self.config=self.root/'etc/dpkg/dpkg.cfg'
        self.config.write_text('no-debsig\n')
    def snapshot(self):
        return package_configuration(self.root,owner=os.getuid())
    def test_inventory_and_content_drift_changes_snapshot(self):
        before=self.snapshot()
        fragment=self.root/'etc/dpkg/dpkg.cfg.d/hook'
        fragment.write_text('status-logger=other\n')
        self.assertNotEqual(before,self.snapshot())
        fragment.unlink()
        self.assertEqual(before,self.snapshot())
        self.config.write_text('force-unsafe-io\n')
        self.assertNotEqual(before,self.snapshot())
    def test_logger_creation_and_change_are_bound(self):
        before=self.snapshot()
        logger=self.root/'usr/lib/needrestart/dpkg-status'
        logger.write_text('#!/bin/sh\n')
        created=self.snapshot()
        self.assertNotEqual(before,created)
        logger.write_text('#!/bin/sh\nexit 1\n')
        self.assertNotEqual(created,self.snapshot())
    def test_symlinks_and_writable_configuration_are_rejected(self):
        self.config.chmod(0o666)
        with self.assertRaises(ValueError):self.snapshot()
        self.config.chmod(0o644)
        self.config.unlink();self.config.symlink_to('/missing')
        with self.assertRaises(ValueError):self.snapshot()
    def test_writable_directory_is_rejected(self):
        (self.root/'etc/dpkg/dpkg.cfg.d').chmod(0o777)
        with self.assertRaises(ValueError):self.snapshot()
