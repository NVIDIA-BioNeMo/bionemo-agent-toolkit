"""Staging rejects changed source and preserves the local transport layout."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import base64,shlex
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from setup_operation import setup_payload
from service import Service
import ownership_adapter

class SetupPayloadTests(unittest.TestCase):
    def test_exact_snapshot_and_local_copy_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);sources=root/'source';sources.mkdir()
            content=b'print("reviewed")\n';(sources/'helper.py').write_bytes(content)
            scripts=Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'
            for name in ('toolchain_paths.py','executor_ownership.py'):(sources/name).write_bytes((scripts/name).read_bytes())
            owner={'protocol':1,'executor_id':'a'*32,'controller_root_sha256':'b'*64,'linux_machine_id_sha256':'c'*64,'brev':None}
            review={'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.iterdir()},'operation_id':'example','remote_root':str(root/'runtime'),'executor_ownership':{'owner':owner},'ownership_guard_files':ownership_adapter.manifest(sources)}
            payload=root/'example';setup_payload(sources,payload,review,str(root/'remote/example'),'checksum')
            (sources/'helper.py').write_text('changed after snapshot')
            remote=root/'remote';remote.mkdir()
            Service(root/'state').target_copy({'kind':'local'},payload,str(remote))
            self.assertEqual((remote/'example/helper.py').read_bytes(),content)
            self.assertEqual(json.loads((remote/'example/setup-review.json').read_text()),review)
            self.assertEqual({p.name for p in (remote/'example').iterdir()},{'helper.py','toolchain_paths.py','executor_ownership.py','run.sh','setup-review.json'})

    def guard_fixture(self,root):
        source=root/'source';source.mkdir()
        scripts=Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'
        for name in ('toolchain_paths.py','executor_ownership.py'):(source/name).write_bytes((scripts/name).read_bytes())
        owner={'protocol':1,'executor_id':'a'*32,'controller_root_sha256':'b'*64,'linux_machine_id_sha256':'c'*64,'brev':None}
        review={'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()},'operation_id':'example','remote_root':'/srv/rfd4','executor_ownership':{'owner':owner},'ownership_guard_files':ownership_adapter.manifest(source)}
        return source,review

    def test_guard_uses_verified_snapshot_when_original_changes_after_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,review=self.guard_fixture(root);destination=root/'payload'
            original=(source/'executor_ownership.py').read_text();command=ownership_adapter.command;guards=[]
            def race(*args,**kwargs):
                (source/'executor_ownership.py').write_text('changed during package update')
                self.assertEqual(kwargs['scripts'],destination)
                result=command(*args,**kwargs);guards.append(result);return result
            with patch.object(ownership_adapter,'command',side_effect=race):setup_payload(source,destination,review,'/remote','checksum')
            guard=guards[0];self.assertIn(guard,(destination/'run.sh').read_text())
            payload=json.loads(base64.b64decode(shlex.split(guard)[-1]))
            self.assertEqual(payload['sources']['executor_ownership'],original)

    def test_changed_bootstrap_cannot_enter_reviewed_setup_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,review=self.guard_fixture(root)
            with patch.object(ownership_adapter,'BOOTSTRAP','raise RuntimeError("changed")'):
                with self.assertRaisesRegex(ValueError,'helper changed'):setup_payload(source,root/'payload',review,'/remote','checksum')
            self.assertFalse((root/'payload/run.sh').exists())

    def test_changed_source_cannot_be_staged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'helper.py').write_text('changed')
            review={'files':{'helper.py':hashlib.sha256(b'reviewed').hexdigest()}}
            with self.assertRaisesRegex(ValueError,'changed while staging'):
                setup_payload(root,root/'payload',review,'/remote','checksum')
            self.assertFalse((root/'payload/helper.py').exists())

    def test_symlink_source_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'original').write_bytes(b'content');(root/'helper.py').symlink_to(root/'original')
            review={'files':{'helper.py':hashlib.sha256(b'content').hexdigest()}}
            with self.assertRaisesRegex(ValueError,'symlink'):
                setup_payload(root,root/'payload',review,'/remote','checksum')
