"""Chat annotations must not reuse atom indices after a concurrent edit."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
from service import Service


class ChatAnnotationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = Service(temporary.name)
        self.atoms = ['ALA', 'TYR', 'GLY']
        self.revision = 7
        self.summary_override = None
        self.edit_at = None
        self.annotated = []
        self.mutations = []
        editor = patch.object(self.service, 'studio', side_effect=self.editor)
        editor.start()
        self.addCleanup(editor.stop)

    def delete_first_atom(self):
        self.atoms.pop(0)
        self.revision += 1

    def editor(self, method, path, **kwargs):
        if (method, path) == ('GET', 'sessions/session'):
            summary = self.summary_override or {'structure': {'revision': self.revision}}
            if self.edit_at == 'after_revision':
                self.delete_first_atom()
            return summary
        if (method, path) == ('POST', 'sessions/session/selections/query'):
            self.assertEqual(kwargs['json']['expression'], "res_name == 'TYR'")
            indices = [i for i, name in enumerate(self.atoms) if name == 'TYR']
            if self.edit_at == 'after_selection':
                self.delete_first_atom()
            return {'atom_indices': indices, 'count': len(indices)}
        if (method, path) == ('POST', 'sessions/session/conditions'):
            body = kwargs['json']
            self.mutations.append(body)
            expected = body.get('expected_revision')
            if expected is not None and expected != self.revision:
                response = httpx.Response(409, json={'detail': {'code': 'revision_conflict'}},
                    request=httpx.Request(method, 'http://localhost/api/v1/' + path))
                response.raise_for_status()
            self.annotated.extend(self.atoms[i] for i in body['atom_indices'])
            self.revision += 1
            return {'structure': {'revision': self.revision}}
        raise AssertionError(f'Unexpected editor request: {method} {path}')

    def annotate(self):
        return self.service.annotate('session', "res_name == 'TYR'", 'hotspot')

    def test_unchanged_structure_annotates_requested_residue(self):
        result = self.annotate()
        self.assertEqual(self.annotated, ['TYR'])
        self.assertEqual(self.mutations[0].get('expected_revision'), 7)
        self.assertEqual(result['structure']['revision'], 8)

    def test_edits_before_or_after_selection_reject_annotation(self):
        for edit_at in ('after_revision', 'after_selection'):
            with self.subTest(edit_at=edit_at):
                self.atoms = ['ALA', 'TYR', 'GLY']
                self.revision = 7
                self.edit_at = edit_at
                self.mutations.clear()
                with self.assertRaises(httpx.HTTPStatusError) as conflict:
                    self.annotate()
                self.assertEqual(conflict.exception.response.status_code, 409)
                self.assertEqual(self.atoms, ['TYR', 'GLY'])
                self.assertEqual(self.revision, 8)
                self.assertEqual(self.annotated, [])
                self.assertEqual(len(self.mutations), 1)

    def test_empty_selection_does_not_apply_annotation(self):
        self.atoms = ['ALA', 'GLY']
        with self.assertRaisesRegex(ValueError, 'Selection matched no atoms'):
            self.annotate()
        self.assertEqual(self.mutations, [])

    def test_invalid_revision_does_not_apply_annotation(self):
        for revision in (None, True, -1, '7'):
            with self.subTest(revision=revision):
                self.summary_override = {'structure': {'revision': revision}}
                with self.assertRaisesRegex(ValueError, 'revision'):
                    self.annotate()
                self.assertEqual(self.mutations, [])
                self.assertEqual(self.annotated, [])
