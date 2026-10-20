"""Immutable machine-wide controller binding, separate from run reservations.

The claim entry point is privileged and has a fixed destination. Inspection is
read-only. Controller integration must explicitly review an initial claim; this
helper never infers approval from a request to connect or check readiness.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from toolchain_paths import protected_directory, read_record, write_record

BASE = Path('/var/lib/bionemo-rfd4')
RECORD = 'executor-owner.json'
COMMITTED = 'executor-owner-committed.json'
PROTOCOL = 1


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(value):
    if not isinstance(value, dict) or set(value) != {'protocol', 'executor_id', 'controller_root_sha256', 'linux_machine_id_sha256', 'brev'}:
        raise ValueError('Unsupported executor ownership record; preserve it and reconcile with the owning controller')
    if type(value['protocol']) is not int or value['protocol'] != PROTOCOL:
        raise ValueError('Unsupported executor ownership protocol')
    if not isinstance(value['executor_id'], str) or not re.fullmatch(r'[0-9a-f]{32}', value['executor_id']):
        raise ValueError('Invalid owning executor ID')
    for key in ('controller_root_sha256', 'linux_machine_id_sha256'):
        if not isinstance(value[key], str) or not re.fullmatch(r'[0-9a-f]{64}', value[key]):
            raise ValueError('Invalid executor ownership identity digest')
    provider = value['brev']
    if provider is not None:
        if not isinstance(provider, dict) or set(provider) != {'organization_id', 'instance_id'}:
            raise ValueError('Invalid immutable Brev ownership identity')
        if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', v) for v in provider.values()):
            raise ValueError('Invalid immutable Brev ownership identity')
    return value


def physical_identity():
    value = Path('/etc/machine-id').read_text().strip().lower()
    if not re.fullmatch(r'[0-9a-f]{32}', value) or value == '0' * 32:
        raise ValueError('Cannot verify Linux machine identity for executor ownership')
    return hashlib.sha256(value.encode()).hexdigest()


def _read(directory, *, owner_uid=0):
    try:
        return validate(read_record(directory, RECORD, owner_uid=owner_uid))
    except FileNotFoundError:
        return None


def _matching(current, expected):
    if current != expected:
        raise ValueError('This machine belongs to a different executor or controller state directory. Use the owning installation; ownership transfer is not supported.')


def _commit_marker(directory, current, *, owner_uid=0):
    expected = {'protocol': PROTOCOL, 'owner_checksum': checksum(current)}
    try:
        saved = read_record(directory, COMMITTED, owner_uid=owner_uid)
    except FileNotFoundError:
        saved = None
    if saved is not None and saved != expected:
        raise ValueError('Executor ownership commit marker changed or uses an unsupported protocol; preserve it')
    return expected, saved


def _flush_readable_owner(directory, *, owner_uid=0):
    """Complete publication even when a previous rename acknowledgment was lost."""
    descriptor = os.open(RECORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != owner_uid or metadata.st_mode & 0o022:
            raise ValueError('Executor ownership receipt is not protected')
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
        os.fchmod(directory, 0o755)
        os.fsync(directory)
    finally:
        os.close(descriptor)


def inspect(expected):
    """No sudo, directory creation, lock-file creation or record writes."""
    validate(expected)
    if physical_identity() != expected['linux_machine_id_sha256']:
        raise ValueError('Machine identity changed before executor ownership inspection')
    committed = None
    try:
        with protected_directory(BASE) as directory:
            current = _read(directory)
            try:
                committed = read_record(directory, COMMITTED)
            except FileNotFoundError:
                committed = None
    except FileNotFoundError:
        current = None
    if current is None:
        if committed is not None:
            raise ValueError('Previously committed ownership receipt is missing; no replacement claim is allowed')
        return {'state': 'unclaimed', 'detail': 'A reviewed administrator claim is required before compute mutations.'}
    _matching(current, expected)
    marker = {'protocol': PROTOCOL, 'owner_checksum': checksum(current)}
    if committed is not None and committed != marker:
        raise ValueError('Executor ownership commit marker changed or uses an unsupported protocol; preserve it')
    if committed is None:
        return {'state': 'pending', 'owner': current, 'owner_checksum': checksum(current),
                'detail': 'The owner record exists but durable publication is unconfirmed. Explicitly confirm the same reviewed owner; no replacement claim is allowed.'}
    return {'state': 'owned', 'owner': current, 'owner_checksum': checksum(current)}


def require_execution_scope(proof):
    """Verify an owned historical contract or an explicit dedicated-user binding.

    Dedicated Brev execution never claims a machine-wide controller lock. It
    verifies physical identity and refuses any existing/pending protected owner;
    concurrency within this controller remains governed by run reservations.
    """
    if not isinstance(proof,dict):raise ValueError('Missing execution scope binding')
    owner=validate(proof['owner'])
    if proof.get('owner_checksum')!=checksum(owner):
        raise ValueError('Execution scope identity checksum differs')
    scope=proof.get('scope','machine_owner')
    if scope not in ('machine_owner','dedicated_brev_user'):
        raise ValueError('Unsupported execution scope')
    if scope=='dedicated_brev_user':
        provider=proof.get('brev')
        if not isinstance(provider,dict) or set(provider)!={'organization_id','instance_id'} or any(
                not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',v) for v in provider.values()):
            raise ValueError('Dedicated-user execution requires an immutable Brev identity')
    observed=inspect(owner)
    required='unclaimed' if scope=='dedicated_brev_user' else 'owned'
    if observed.get('state')!=required:
        raise ValueError('Dedicated-user execution cannot replace an existing ownership contract' if scope=='dedicated_brev_user'
                         else 'Protected executor ownership is not committed')
    return observed


def _claim_directory(directory, expected, *, allow_initial, owner_uid=0):
    """Short local filesystem transaction; no network or slow process work."""
    descriptor = os.open('executor-owner.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644, dir_fd=directory)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != owner_uid or metadata.st_mode & 0o022:
            raise ValueError('Executor ownership lock is not protected')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another executor claim is in progress; inspect ownership before retrying') from None
        current = _read(directory, owner_uid=owner_uid)
        if current is not None:
            _matching(current, expected)
            marker, _ = _commit_marker(directory, current, owner_uid=owner_uid)
            _flush_readable_owner(directory, owner_uid=owner_uid)
            write_record(directory, COMMITTED, marker, owner_uid=owner_uid)
            return {'state': 'owned', 'reused': True, 'owner': current, 'owner_checksum': checksum(current)}
        if allow_initial is not True:
            raise ValueError('Previously established machine ownership is missing; no replacement claim was written')
        try:
            read_record(directory, COMMITTED, owner_uid=owner_uid)
        except FileNotFoundError:
            pass
        else:
            raise ValueError('Previously committed ownership receipt is missing; no replacement claim is allowed')
        write_record(directory, RECORD, expected, owner_uid=owner_uid)
        _flush_readable_owner(directory, owner_uid=owner_uid)
        # Presence proves the ownership receipt and its directory were synced
        # first, even if the final helper acknowledgment is lost. Missing marker
        # remains pending and cannot authorize a compute mutation.
        write_record(directory, COMMITTED, {'protocol': PROTOCOL, 'owner_checksum': checksum(expected)}, owner_uid=owner_uid)
        return {'state': 'owned', 'reused': False, 'owner': expected, 'owner_checksum': checksum(expected)}
    finally:
        os.close(descriptor)


def claim(expected, review_checksum, *, allow_initial=False):
    """Explicit reviewed root helper. No caller-selected filesystem location."""
    if os.geteuid() != 0:
        raise ValueError('Initial machine ownership requires an administrator; ordinary inspection never requires sudo')
    validate(expected)
    review = {'action': 'claim_executor', 'owner': expected, 'allow_initial': allow_initial}
    if type(allow_initial) is not bool or checksum(review) != review_checksum:
        raise ValueError('Executor ownership review changed')
    if physical_identity() != expected['linux_machine_id_sha256']:
        raise ValueError('Machine identity changed before executor ownership claim')
    # Validate every ancestor and create only the one fixed protected directory.
    with protected_directory(BASE.parent) as parent:
        try:
            os.mkdir(BASE.name, 0o755, dir_fd=parent)
        except FileExistsError:
            pass
        # A prior mkdir may have succeeded before its fsync acknowledgment was
        # lost. Retry the parent barrier even when reusing the directory.
        os.fsync(parent)
    with protected_directory(BASE) as directory:
        return _claim_directory(directory, expected, allow_initial=allow_initial)
