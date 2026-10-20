"""Read-only platform review for pinned public wheels; not GPU readiness."""
import hashlib
import json
import platform
from pathlib import Path
import re
import subprocess

PROFILE = {'schema': 1, 'kind': 'public_wheels', 'platform': 'Linux',
           'architecture': 'x86_64', 'libc': 'glibc', 'minimum_glibc': [2, 28],
           'bootstrap_python': 'cpython-3.12-linux-x86_64-gnu',
           'minimum_driver_major': 580}


def profile():
    return json.loads(json.dumps(PROFILE))


def profile_sha(value=None):
    value = profile() if value is None else value
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _validate_profile(value):
    if type(value) is not dict or profile_sha(value) != profile_sha():
        raise ValueError('Unsupported public-wheel prerequisite profile')


def _validate_observation(observation):
    if type(observation) is not dict or set(observation) != {'platform', 'architecture', 'libc', 'libc_version', 'driver_versions'}:
        raise ValueError('Malformed public-wheel platform observation')
    if any(observation.get(key) != PROFILE[key] for key in ('platform', 'architecture', 'libc')):
        raise ValueError('Public wheels require Linux x86_64 with glibc')
    version = observation['libc_version']
    if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)*', version) or tuple(map(int, version.split('.')[:2])) < (2, 28):
        raise ValueError('Public wheels require glibc 2.28 or newer')
    drivers = observation['driver_versions']
    if not isinstance(drivers, list) or not drivers or any(not isinstance(v, str) or not re.fullmatch(r'\d+(?:\.\d+)+', v) or int(v.split('.')[0]) < 580 for v in drivers):
        raise ValueError('CUDA 13 wheels require a preliminary NVIDIA driver check of 580 or newer')
    if drivers != sorted(set(drivers)):
        raise ValueError('Noncanonical NVIDIA driver observation')


def review(value=None):
    _validate_profile(profile() if value is None else value)
    libc, version = platform.libc_ver()
    observation = {'platform': platform.system(), 'architecture': platform.machine(),
                   'libc': libc, 'libc_version': version, 'driver_versions': ['580.0']}
    # Refuse incompatible bootstrap platforms before invoking any external program.
    _validate_observation(observation)
    result = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                            check=True, capture_output=True, text=True, timeout=30)
    observation['driver_versions'] = sorted(set(line.strip() for line in result.stdout.splitlines() if line.strip()))
    _validate_observation(observation)
    return {'kind': 'public_wheels', 'status': 'ready', 'profile_sha256': profile_sha(),
            'installation_authorized': False, 'changes': {}, 'download_bytes': 0,
            'observation': observation}


def helper_hashes(scripts=None):
    scripts = Path(scripts) if scripts is not None else Path(__file__).parent
    return {'public_prerequisite.py': hashlib.sha256((scripts/'public_prerequisite.py').read_bytes()).hexdigest()}


def bind_review(result, scripts=None):
    required = {'kind', 'status', 'profile_sha256', 'installation_authorized', 'changes', 'download_bytes', 'observation'}
    if type(result) is not dict or set(result) not in (required, required | {'helper_hashes'}):
        raise ValueError('Malformed public-wheel prerequisite review')
    if result['kind'] != 'public_wheels' or result['status'] != 'ready' or result['profile_sha256'] != profile_sha():
        raise ValueError('Public-wheel prerequisite profile mismatch')
    if result['installation_authorized'] is not False or type(result['changes']) is not dict or result['changes'] or type(result['download_bytes']) is not int or result['download_bytes'] != 0:
        raise ValueError('Public-wheel prerequisite review cannot authorize package mutations or downloads')
    _validate_observation(result['observation'])
    hashes = helper_hashes(scripts)
    if 'helper_hashes' in result and result['helper_hashes'] != hashes:
        raise ValueError('Public-wheel prerequisite helper changed')
    return dict(result, helper_hashes=hashes)


def probe_script():
    source = Path(__file__).read_text()
    return 'import json\n' + source + '\nprint(json.dumps(review()))\n'
