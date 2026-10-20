import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from idle_baseline import qualified_role

class IdleBaselineTests(unittest.TestCase):
    def setUp(self):
        self.main={'uid':0,'executable':{'path':'/usr/bin/agent','sha256':'a'*64},'argv_sha256':'b'*64,
                   'cgroup':'/system.slice/agent.service','unit':'agent.service',
                   'unit_control_group':'/system.slice/agent.service','config_files':[],
                   'unit_files':[{'path':'/usr/lib/systemd/system/agent.service','sha256':'c'*64}],
                   'pid':100,'ppid':1,'main_pid':100,'identity_stable':True}
        keys=('uid','executable','argv_sha256','cgroup','unit','unit_files','unit_control_group','config_files')
        main_role={k:self.main[k] for k in keys}|{'id':'agent','kind':'main','max_count':1}
        self.child=dict(self.main,pid=101,ppid=100,uid=10,executable={'path':'/usr/bin/helper','sha256':'d'*64})
        child_role={k:self.child[k] for k in keys}|{'id':'helper','kind':'child','parent_role':'agent','max_count':1}
        self.profile={'status':'qualified','roles':[main_role,child_role]}

    def test_restart_resolves_new_main_pid(self):
        for pid in (100,999):
            self.assertEqual(qualified_role(dict(self.main,pid=pid,main_pid=pid),self.profile,{},{}),'agent')

    def test_candidate_and_changed_identity_cannot_exempt(self):
        self.assertIsNone(qualified_role(self.main,dict(self.profile,status='candidate'),{},{}))
        self.assertIsNone(qualified_role(dict(self.main,identity_stable=False),self.profile,{},{}))
        for key,value in [('uid',1),('executable',{'path':'/usr/bin/agent','sha256':'e'*64}),
                          ('argv_sha256','f'*64),('cgroup','/other'),('unit','other.service'),('unit_files',[])]:
            with self.subTest(key=key):self.assertIsNone(qualified_role(dict(self.main,**{key:value}),self.profile,{},{}))

    def test_child_requires_exact_role_and_verified_parent(self):
        self.assertIsNone(qualified_role(self.child,self.profile,{},{}))
        parent=dict(self.main,qualified_role='agent')
        self.assertEqual(qualified_role(self.child,self.profile,{}, {100:parent}),'helper')
        for changed in (dict(self.child,ppid=900),dict(self.child,executable={'path':'/bin/bash','sha256':'d'*64})):
            self.assertIsNone(qualified_role(changed,self.profile,{}, {100:parent}))
        self.assertIsNone(qualified_role(self.child,self.profile,{}, {100:dict(parent,identity_stable=False)}))

    def test_duplicate_role_and_unknown_process_remain_busy(self):
        used={}
        self.assertEqual(qualified_role(self.main,self.profile,used,{}),'agent')
        self.assertIsNone(qualified_role(self.main,self.profile,used,{}))
        self.assertIsNone(qualified_role(dict(self.main,pid=200),self.profile,{},{}))

    def test_missing_or_changed_configuration_cannot_exempt(self):
        for field in ('unit_control_group', 'config_files', 'unit_files', 'argv_sha256'):
            process = dict(self.main)
            del process[field]
            profile = copy.deepcopy(self.profile)
            del profile['roles'][0][field]
            self.assertIsNone(qualified_role(process, profile, {}, {}))
        changed = dict(self.main, config_files=[{'path':'/etc/agent', 'sha256':'changed'}])
        self.assertIsNone(qualified_role(changed, self.profile, {}, {}))

    def test_matching_profile_does_not_authorize_wrong_control_group(self):
        for group in ('/', '/system.slice/other.service'):
            process = dict(self.main, unit_control_group=group)
            profile = copy.deepcopy(self.profile)
            profile['roles'][0]['unit_control_group'] = group
            self.assertIsNone(qualified_role(process, profile, {}, {}))

    def test_child_cannot_use_parent_with_reused_or_mismatched_pid(self):
        parent = dict(self.main, qualified_role='agent', pid=999)
        self.assertIsNone(qualified_role(self.child, self.profile, {}, {100:parent}))
