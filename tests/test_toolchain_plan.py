import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from toolchain_plan import validate_plan

class ToolchainPlanTests(unittest.TestCase):
    def test_exact_install_and_configure(self):
        result=validate_plan('Inst g++ [old] (11.4 Ubuntu [amd64])\nConf g++ (11.4 Ubuntu [amd64])',{'g++':'11.4'})
        self.assertEqual(result,{'g++':{'version':'11.4','actions':['Inst','Conf']}})
    def test_already_installed_is_no_effect(self):
        self.assertEqual(validate_plan('0 upgraded, 0 newly installed, 0 to remove.',{'g++':'11.4'}),{})
    def test_unreviewed_effects_refused(self):
        for output in ('Remv old (1)', 'Purg old (1)', 'Inst driver (1 repo)', 'Inst g++ (12 repo)', 'Inst g++ malformed', 'Inst g++:arm64 (11.4 repo)', 'Conf extra (1 repo)'):
            with self.subTest(output=output),self.assertRaises(ValueError):
                validate_plan(output,{'g++':'11.4'})
    def test_duplicate_effect_refused(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            validate_plan('Inst g++ (11.4 repo)\nInst g++ (11.4 repo)',{'g++':'11.4'})
    def test_revised_plan_can_pass_after_rejected_proposal(self):
        with self.assertRaises(ValueError):validate_plan('Inst driver (1 repo)',{'g++':'11.4'})
        self.assertEqual(list(validate_plan('Inst g++ (11.4 repo)',{'g++':'11.4'})),['g++'])
