"""Compute-free requests preserve exact reviewed inputs and reject tampering."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service


class DesignRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = Service(self.temp.name)
        self.editor = patch.object(self.service, 'studio', return_value={
            'cif': 'data_test\n# annotated input\n', 'revision': 4, 'issues': []})
        self.editor.start()
        self.addCleanup(self.editor.stop)

    def test_prepare_without_compute_and_read_exact_request(self):
        with patch.object(self.service, 'check_named_target', side_effect=AssertionError('compute queried')):
            request = self.service.prepare_design_request('session', 'my note', samples=2, seed=99)
            self.assertEqual(self.service.get_design_request(request['request_id']), request)
        self.assertEqual(request['note'], 'my note')
        self.assertEqual(request['samples'], 2)
        self.assertNotIn('target', request)
        self.assertEqual(request['generation']['thinking'], 'medium')
        self.assertFalse((self.service.root / 'managed-compute.json').exists())

    def test_repeated_preparation_does_not_mutate_prior_request(self):
        first = self.service.prepare_design_request('session', 'first')
        second = self.service.prepare_design_request('session', 'second')
        self.assertNotEqual(first['request_id'], second['request_id'])
        self.assertEqual(self.service.get_design_request(first['request_id']), first)

    def test_modified_input_or_settings_rejected(self):
        for filename in ('input.cif', 'request.json'):
            request = self.service.prepare_design_request('session')
            path = self.service.state / request['request_id'] / filename
            if filename.endswith('.json'):
                record = json.loads(path.read_text()); record['seed'] += 1
                path.write_text(json.dumps(record))
            else:
                path.write_text('modified')
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.service.get_design_request(request['request_id'])

    def test_invalid_settings_do_not_export_editor(self):
        for kw in ({'samples': 0}, {'samples': True}, {'seed': -1}, {'generation': {'thinking': 'invalid'}}):
            with self.assertRaises(ValueError): self.service.prepare_design_request('session', **kw)
        self.service.studio.assert_not_called()

    def test_validation_error_prevents_request(self):
        self.service.studio.return_value['issues'] = [{'severity':'error', 'message':'bad structure'}]
        with self.assertRaisesRegex(ValueError, 'validation failed'):
            self.service.prepare_design_request('session')
        self.assertEqual(list(self.service.state.glob('*/request.json')), [])

    def test_warning_preserved_for_review(self):
        self.service.studio.return_value['issues'] = [{'check':'missing_atoms','severity':'error','message':'missing atoms'}]
        request = self.service.prepare_design_request('session')
        self.assertEqual(request['issues'][0]['severity'], 'warning')

    def test_request_path_traversal_rejected(self):
        with self.assertRaises(ValueError): self.service.get_design_request('../state')
