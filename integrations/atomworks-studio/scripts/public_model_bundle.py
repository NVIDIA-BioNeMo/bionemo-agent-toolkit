"""Pinned public RFD4 bundle, including AE tensors; no Hub credentials required.

Only these two files are consumed by upstream ``load_pretrained_bundle``.
The revision receipt is published after every byte and the format are verified.
"""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request


MODEL_REPO = 'nvidia/RFD4-Proteina'
MODEL_REVISION = 'a06e2509c7033b010fc43614e9fd840303588502'
BUNDLE_FILES = (
    {'name': 'config.json', 'size': 7270,
     'sha256': '154ea927ab8005b7eac2d047a792147fb4606ab4878e496aa8414b6b40dad368'},
    {'name': 'model.safetensors', 'size': 1742660596,
     'sha256': '5b549dd61adb2f6c6b5cb95bda13f40f5e31556b4e6c755edc0ca6f011c68fb0'},
)
RECEIPT_NAME = '.rfd4-public-bundle.json'


def manifest():
    return {'repo_id': MODEL_REPO, 'revision': MODEL_REVISION,
            'files': [dict(item) for item in BUNDLE_FILES]}


def valid(path, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected["sha256"]


def _safe_root(root):
    root = Path(root).expanduser().absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError('Refusing symlink model bundle paths')
    if root.exists() and not root.is_dir():
        raise ValueError('Model bundle root must be a directory')
    return root


def _config_valid(root):
    payload = json.loads((root / 'config.json').read_text())
    cfg = payload.get('config', {})
    if (payload.get('model_type') != 'rfd4_proteina' or payload.get('format_version') != 1
            or not isinstance(cfg, dict) or not cfg.get('autoencoder_config')):
        raise ValueError('Public model bundle must include resolved model and autoencoder configuration')
    allowed = {'nn', 'product_flowmatcher', 'loss', 'training', 'opt',
               'autoencoder_config', 'path_length_search_cutoffs'}
    if set(cfg) - allowed or '${' in json.dumps(cfg) or '"_target_"' in json.dumps(cfg):
        raise ValueError('Model bundle configuration contains unresolved or executable runtime targets')
    expected_weights = next(item['sha256'] for item in BUNDLE_FILES if item['name'] == 'model.safetensors')
    if payload.get('weights_sha256') != expected_weights:
        raise ValueError('Model configuration does not identify the pinned weights')


def verify_bundle(root, *, revision=MODEL_REVISION):
    """Return the pinned manifest or raise; readonly, hashes all required files."""
    root = _safe_root(root)
    if revision != MODEL_REVISION:
        raise ValueError('Unsupported public model revision')
    for item in BUNDLE_FILES:
        if not valid(root / item['name'], item):
            raise ValueError('Missing or corrupt public model bundle file: ' + item['name'])
    _config_valid(root)
    receipt = root / RECEIPT_NAME
    if receipt.is_symlink() or not receipt.is_file() or json.loads(receipt.read_text()) != manifest():
        raise ValueError('Missing or mismatched public model bundle revision receipt')
    return manifest()


def download_bundle(root, *, opener=urllib.request.urlopen, check_cancel=lambda: None):
    """Resume verified downloads; never overwrite another bundle or user file."""
    from runtime_download import fetch
    root = _safe_root(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = root / RECEIPT_NAME
    if receipt.is_symlink() or (receipt.exists() and json.loads(receipt.read_text()) != manifest()):
        raise ValueError('Refusing to replace a different model bundle revision')
    for item in BUNDLE_FILES:
        check_cancel()
        destination = root / item['name']
        if destination.is_symlink() or (destination.exists() and not valid(destination, item)):
            raise ValueError('Refusing to overwrite existing model bundle file: ' + item['name'])
        for suffix in ('.part', '.lock'):
            if destination.with_name(destination.name + suffix).is_symlink():
                raise ValueError('Refusing symlink model download paths')
        url = f'https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{item["name"]}'
        fetch(url, destination, item, opener=opener)
    check_cancel()
    _config_valid(root)
    if not receipt.exists():
        fd, temporary = tempfile.mkstemp(prefix='.bundle-receipt-', dir=root)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(manifest(), handle, sort_keys=True)
                handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
            os.link(temporary, receipt)
        finally:
            os.unlink(temporary)
    directory_fd = os.open(str(root), os.O_RDONLY)
    try: os.fsync(directory_fd)
    finally: os.close(directory_fd)
    return verify_bundle(root)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = verify_bundle(args.directory) if args.check else download_bundle(args.directory)
    print(json.dumps(result, sort_keys=True))
