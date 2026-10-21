from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from service import Service
from brev_provider import creation_payload

SPEC={'type':'available-a100','cloudCredId':'cloud-ref','provider':None,'location':None,'subLocation':None,'basePrice':{'currency':'USD','amount':'2.0'},'supportedStorage':[],'supportedGpus':[{'name':'A100','count':1,'memoryBytes':{'value':'80','unit':'GB'}}],'supportedArchitectures':['x86_64'],'stoppable':True}

class Provider:
    def __init__(self):self.calls=0;self.observed=None;self.lose=False
    def organization_name(self,org):return 'reviewed-org'
    def catalog(self,org):return [SPEC.copy()]
    def inventory(self,org):return [{'id':'existing','name':'existing'}]
    def preflight_creation(self,org,name,kind):
        return {'organization_id':org,'organization_name':'reviewed-org','name':name,'instance_type':kind,'specification':SPEC.copy(),'request_payload':creation_payload(name,SPEC)}
    def dispatch_creation(self,prepared):
        org=prepared['organization_id'];name=prepared['name'];kind=prepared['instance_type']
        self.calls+=1
        self.observed={'state':'observed','organization_id':org,'instance_id':'created','name':name,'instance_type':kind,'specification':SPEC.copy(),'request_payload':creation_payload(name,SPEC)}
        if self.lose:raise TimeoutError('receipt lost')
        return self.observed
    def verify_created_allocation(self,*args):return {'status':'verified'}
    def observe_creation(self,*args):return self.observed or {'state':'unknown'}

class CreationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.s=Service(self.temp.name);self.provider=Provider()
        patcher=patch('lifecycle.Brev',return_value=self.provider);patcher.start();self.addCleanup(patcher.stop)
        self.op=self.s.begin_setup('demo')['id']
        self.review=self.s.prepare_compute_creation(self.op,'org','available-a100')
    def execute(self):return self.s.execute_compute_creation(self.op,self.review['review_checksum'])
    def test_create_once_without_selecting_or_running(self):
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.execute()['state'],'succeeded')
        self.assertEqual(self.provider.calls,1)
        self.assertIsNone(self.s.managed.selection('demo')['machine_id'])
        self.assertNotIn('create:'+self.op,self.s.managed.snapshot()['reservations'])
    def test_lost_response_reconciles_same_machine(self):
        self.provider.lose=True
        with self.assertRaises(TimeoutError):self.execute()
        self.assertEqual(self.execute()['state'],'succeeded');self.assertEqual(self.provider.calls,1)
    def test_unknown_outcome_never_creates_again(self):
        with patch.object(self.provider,'dispatch_creation',side_effect=TimeoutError('unknown')) as create:
            with self.assertRaises(TimeoutError):self.execute()
            self.assertEqual(self.execute()['state'],'needs_attention');create.assert_called_once()
        self.assertIn('create:'+self.op,self.s.managed.snapshot()['reservations'])
    def test_cancellation_before_dispatch_creates_nothing(self):
        self.s.managed.cancel(self.op)
        self.assertEqual(self.execute()['state'],'cancelled');self.assertEqual(self.provider.calls,0)
    def test_existing_instance_cannot_be_claimed_as_new(self):
        self.provider.lose=True
        with self.assertRaises(TimeoutError):self.execute()
        self.provider.observed['instance_id']='existing'
        with self.assertRaisesRegex(ValueError,'predates'):self.execute()
        self.assertEqual(self.provider.calls,1)

    def test_known_preflight_failure_is_terminal_without_dispatch(self):
        with patch.object(self.provider,'preflight_creation',side_effect=ValueError('unsupported CLI')):
            with self.assertRaisesRegex(ValueError,'unsupported CLI'):self.execute()
        op=self.s.managed.operation(self.op)
        self.assertEqual(op['state'],'failed');self.assertFalse(op['dispatched'])
        self.assertEqual(self.provider.calls,0)
        self.assertNotIn('create:'+self.op,self.s.managed.snapshot()['reservations'])

    def test_changed_price_requires_new_review_without_dispatch(self):
        original=self.provider.preflight_creation
        def changed(*args):
            result=original(*args)
            result['specification']=dict(SPEC,basePrice={'currency':'USD','amount':'9.0'})
            return result
        with patch.object(self.provider,'preflight_creation',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'price changed'):self.execute()
        self.assertEqual(self.provider.calls,0)
        self.assertFalse(self.s.managed.operation(self.op)['dispatched'])

    def test_changed_request_defaults_block_pending_review(self):
        original=self.provider.preflight_creation
        def changed(*args):
            result=original(*args)
            result['request_payload']['vmBuild']={'forceJupyterInstall':True}
            return result
        with patch.object(self.provider,'preflight_creation',side_effect=changed):
            with self.assertRaises(ValueError):self.execute()
        self.assertEqual(self.provider.calls,0)

    def test_wrong_allocation_retains_reservation_without_replacement(self):
        with patch.object(self.provider,'verify_created_allocation',return_value={'status':'mismatch'}):
            result=self.execute()
            self.assertEqual(result['state'],'needs_attention')
            self.assertEqual(self.execute()['state'],'needs_attention')
        self.assertEqual(self.provider.calls,1)
        self.assertIn('create:'+self.op,self.s.managed.snapshot()['reservations'])
