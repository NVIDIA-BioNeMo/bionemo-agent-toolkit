import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
import public_prerequisite as public
from setup_operation import SetupOperation

class PublicPrerequisiteTests(unittest.TestCase):
    def review(self):
        with patch.object(public.platform,'system',return_value='Linux'), patch.object(public.platform,'machine',return_value='x86_64'), patch.object(public.platform,'libc_ver',return_value=('glibc','2.35')), patch.object(public.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'595.91.07\n')) as run:
            result=public.review()
        self.assertEqual(run.call_args.args[0],['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader'])
        self.assertEqual(run.call_count,1)
        return result

    def test_read_only_review_never_plans_apt_sudo_or_download(self):
        result=public.bind_review(self.review())
        self.assertEqual(result['changes'],{})
        self.assertEqual(result['download_bytes'],0)
        self.assertIs(result['installation_authorized'],False)
        self.assertEqual(result['helper_hashes'],public.helper_hashes())
        self.assertEqual(public.bind_review(result),result)

    def test_malformed_profile_refused_before_any_command(self):
        for value in ({},dict(public.profile(),minimum_driver_major=1),dict(public.profile(),schema=True)):
            with patch.object(public.subprocess,'run') as run, self.assertRaises(ValueError):public.review(value)
            run.assert_not_called()

    def test_changed_or_mutating_review_refused(self):
        good=self.review()
        for changes in ({'profile_sha256':'old-apt-profile'},{'changes':{'package':'1'}},{'download_bytes':True},{'installation_authorized':True},{'helper_hashes':{}},{'kind':'native'}):
            with self.assertRaises(ValueError):public.bind_review(dict(good,**changes))

    def test_incompatible_platform_driver_rejected(self):
        good=self.review()
        for changes in ({'libc_version':'2.27'},{'libc':'musl'},{'architecture':'aarch64'},{'driver_versions':['579.99']},{'driver_versions':[]},{'driver_versions':['garbage']}):
            with self.assertRaises(ValueError):public.bind_review(dict(good,observation=dict(good['observation'],**changes)))

    def test_probe_self_contained_and_no_package_commands(self):
        compile(public.probe_script(),'<public-probe>','exec')
        self.assertNotIn('apt-get',public.probe_script())
        self.assertNotIn('sudo',public.probe_script())

    def test_controller_routes_public_recipe_without_legacy_probe(self):
        result=self.review()
        class Controller(SetupOperation):
            def verify_target(self,cfg):pass
            def target_exec(self,cfg,command,timeout):
                self.command=command
                return json.dumps(result)
        controller=Controller()
        with patch('setup_operation.RECIPE',{'id':'rfd4-public-c7c6cac-wheels-v1'}), patch('prerequisite_review.probe_script',side_effect=AssertionError('APT probe forbidden')):
            bound=controller.review_prerequisites({'id':'machine','config':{}})
        self.assertEqual(bound['kind'],'public_wheels')
        self.assertNotIn('sudo',controller.command)
        self.assertNotIn('apt-get',controller.command)

if __name__=='__main__':unittest.main()
