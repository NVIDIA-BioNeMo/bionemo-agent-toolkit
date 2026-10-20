"""Verify the exact package archives required by a reviewed transaction.

A privileged installer must perform this check in its private staging directory
immediately before use; validation of user-writable files is not a TOCTOU guard.
"""
import hashlib
import json
from pathlib import Path
import stat


def verify_archives(profile, transaction, archives):
    expected_profile=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if transaction.get('profile_sha256')!=expected_profile:
        raise ValueError('Package transaction does not match the reviewed profile')
    needed={name:change for name,change in transaction['changes'].items() if 'Inst' in change['actions']}
    if set(archives)!=set(needed):
        raise ValueError('Staged archives do not exactly match the reviewed installations')
    verified={}
    for name,change in needed.items():
        expected=profile['packages'][name]
        if change['version']!=expected['Version'] or change['sha256']!=expected['SHA256']:
            raise ValueError('Package transaction artifact identity mismatch: '+name)
        path=Path(archives[name])
        # Reject symlinks and nonregular files before opening (e.g. FIFO/device).
        metadata=path.lstat()
        if not stat.S_ISREG(metadata.st_mode):raise ValueError('Package archive must be a regular file: '+name)
        if metadata.st_size!=int(expected['Size']):raise ValueError('Package archive size mismatch: '+name)
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for block in iter(lambda:handle.read(4*1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=expected['SHA256']:raise ValueError('Package archive checksum mismatch: '+name)
        verified[name]={'path':str(path.resolve()),'sha256':digest.hexdigest(),'size':metadata.st_size,'version':expected['Version']}
    return verified
