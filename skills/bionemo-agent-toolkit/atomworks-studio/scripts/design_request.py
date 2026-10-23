"""Immutable editor requests, independent of machines and compute registration."""
import hashlib
import json
import re

from runtime_recipe import options


def checksum(value):
    return hashlib.sha256(json.dumps(
        {k: v for k, v in value.items() if k != 'request_checksum'},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class DesignRequests:
    def prepare_design_request(self, session_id, note='', samples=1, seed=42,
                               image_base64=None, generation=None):
        if type(samples) is not int or not 1 <= samples <= 16:
            raise ValueError('Use 1–16 designs')
        if type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError('Use a nonnegative 31-bit seed')
        generation = options(generation)
        snapshot = self.snapshot(session_id, note,
                                 {'image_base64': image_base64} if image_base64 else None)
        request = dict(snapshot, protocol=1, request_id=snapshot['snapshot_id'],
                       session_id=session_id, samples=samples, seed=seed,
                       generation=generation)
        request['request_checksum'] = checksum(request)
        path = self.state / request['request_id'] / 'request.json'
        # A new request gets a new identity. Existing reviewed requests are never rewritten.
        with path.open('x') as handle:
            json.dump(request, handle, indent=2, allow_nan=False)
        return request

    def get_design_request(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
            raise ValueError('Invalid design request ID')
        directory = self.state / request_id
        request = json.loads((directory / 'request.json').read_text())
        if (request.get('protocol') != 1 or request.get('request_id') != request_id
                or request.get('snapshot_id') != request_id
                or checksum(request) != request.get('request_checksum')):
            raise ValueError('Saved design request changed; review the design again')
        if hashlib.sha256((directory / 'input.cif').read_bytes()).hexdigest() != request['sha256']:
            raise ValueError('Saved design input changed; review the design again')
        if request.get('image_sha256'):
            if hashlib.sha256((directory / 'annotation.png').read_bytes()).hexdigest() != request['image_sha256']:
                raise ValueError('Saved image note changed; review the design again')
        return request
