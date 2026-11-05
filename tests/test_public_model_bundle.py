import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/atomworks-studio/scripts'))
import public_model_bundle as bundle


class Response(io.BytesIO):
    status = 200
    headers = {}


class PublicModelBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'model-bundle'
        self.weights = b'portable model and embedded autoencoder tensors'
        self.config = json.dumps({'model_type': 'rfd4_proteina', 'format_version': 1,
            'weights_sha256': hashlib.sha256(self.weights).hexdigest(),
            'config': {'nn': {}, 'autoencoder_config': {'nn_ae': {}}}}).encode()
        self.data = {'config.json': self.config, 'model.safetensors': self.weights}
        self.files = tuple({'name': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                           for name, data in self.data.items())
        self.addCleanup(patch.stopall)
        patch.object(bundle, 'BUNDLE_FILES', self.files).start()
        self.calls = []

    def opener(self, request, timeout):
        self.calls.append(request)
        self.assertNotIn('Authorization', request.headers)
        self.assertIn('/resolve/' + bundle.MODEL_REVISION + '/', request.full_url)
        return Response(self.data[request.full_url.rsplit('/', 1)[-1]])

    def install(self):
        return bundle.download_bundle(self.root, opener=self.opener)

    def test_download_and_verify_pins_both_files_and_revision(self):
        self.assertEqual(self.install(), bundle.manifest())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(bundle.verify_bundle(self.root), bundle.manifest())

    def test_cancellation_between_files_publishes_no_receipt_and_resumes(self):
        def cancel():
            if self.calls: raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            bundle.download_bundle(self.root,opener=self.opener,check_cancel=cancel)
        self.assertTrue((self.root/'config.json').exists())
        self.assertFalse((self.root/'model.safetensors').exists())
        self.assertFalse((self.root/bundle.RECEIPT_NAME).exists())
        self.assertEqual(self.install(),bundle.manifest())

    def test_verified_files_reused_without_network(self):
        self.install(); self.calls.clear()
        self.install()
        self.assertEqual(self.calls, [])

    def test_wrong_revision_fails_readonly(self):
        self.install()
        with self.assertRaisesRegex(ValueError, 'revision'):
            bundle.verify_bundle(self.root, revision='main')

    def test_each_required_file_corruption_fails(self):
        self.install()
        for name in self.data:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes(); path.write_bytes(b'x' * len(original))
                with self.assertRaisesRegex(ValueError, 'corrupt'):
                    bundle.verify_bundle(self.root)
                with self.assertRaisesRegex(ValueError, 'overwrite'):
                    self.install()
                self.assertEqual(path.read_bytes(), b'x' * len(original))
                path.write_bytes(original)

    def test_missing_model_never_ready(self):
        self.install(); (self.root / 'model.safetensors').unlink()
        with self.assertRaisesRegex(ValueError, 'model.safetensors'):
            bundle.verify_bundle(self.root)

    def test_receipt_required_and_wrong_receipt_never_overwritten(self):
        self.install()
        receipt = self.root / bundle.RECEIPT_NAME
        receipt.unlink()
        with self.assertRaisesRegex(ValueError, 'receipt'):
            bundle.verify_bundle(self.root)
        receipt.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'revision'):
            self.install()
        self.assertEqual(receipt.read_text(), '{}')

    def test_symlink_root_files_and_lock_rejected(self):
        self.install()
        link = Path(self.temp.name).resolve() / 'link'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            bundle.verify_bundle(link)
        for name in ('model.safetensors', 'model.safetensors.lock', bundle.RECEIPT_NAME):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes() if path.exists() else None
                path.unlink(missing_ok=True); path.symlink_to(self.root / 'config.json')
                with self.assertRaises(ValueError): self.install()
                path.unlink()
                if original is not None: path.write_bytes(original)

    def test_corrupt_network_bytes_never_published_or_receipted(self):
        with self.assertRaises(ValueError):
            bundle.download_bundle(self.root, opener=lambda *a, **kw: Response(b'bad'))
        self.assertFalse((self.root / bundle.RECEIPT_NAME).exists())
        self.assertFalse((self.root / 'config.json').exists())

    def test_resume_partial_model_download(self):
        self.root.mkdir()
        prefix = self.weights[:7]
        (self.root / 'model.safetensors.part').write_bytes(prefix)
        def resumed(request, timeout):
            name = request.full_url.rsplit('/', 1)[-1]
            if name == 'config.json': return Response(self.config)
            self.assertEqual(request.headers['Range'], 'bytes=7-')
            response = Response(self.weights[7:]); response.status = 206
            response.headers = {'Content-Range': f'bytes 7-{len(self.weights)-1}/{len(self.weights)}'}
            return response
        bundle.download_bundle(self.root, opener=resumed)
        self.assertEqual((self.root / 'model.safetensors').read_bytes(), self.weights)

    def test_autoencoder_config_is_required_even_with_valid_file_hash(self):
        payload = json.loads(self.config); payload['config']['autoencoder_config'] = None
        data = json.dumps(payload).encode()
        self.data['config.json'] = data
        self.files[0].update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        with self.assertRaisesRegex(ValueError, 'autoencoder'):
            self.install()
        self.assertFalse((self.root / bundle.RECEIPT_NAME).exists())

    def test_executable_or_unresolved_configuration_rejected(self):
        for dangerous in ({'_target_': 'os.system'}, {'nn': '${env:SECRET}'}):
            with self.subTest(dangerous=dangerous):
                payload = json.loads(self.config); payload['config'].update(dangerous)
                data = json.dumps(payload).encode(); self.data['config.json'] = data
                self.files[0].update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
                (self.root / 'config.json').unlink(missing_ok=True)
                with self.assertRaisesRegex(ValueError, 'runtime targets'):
                    self.install()
                self.assertFalse((self.root / bundle.RECEIPT_NAME).exists())

    def test_embedded_readonly_source_requires_no_sibling_import(self):
        self.install()
        namespace = {'__name__': 'rfd4_bundle_verification'}
        exec(Path(bundle.__file__).read_text(), namespace)
        namespace['BUNDLE_FILES'] = self.files
        # The readonly probe is self contained; it does not import downloader or run CLI.
        self.assertEqual(namespace['verify_bundle'](self.root), bundle.manifest())


if __name__ == '__main__': unittest.main()
