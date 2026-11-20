# Strict verification of the one supported native RFD4 recipe.
import hashlib
import json
from pathlib import Path
import shlex

RECIPE = json.loads(Path(__file__).with_suffix('.json').read_text())

BUNDLE_SOURCE = Path(__file__).with_name('public_model_bundle.py').read_text()
PROBE = Path(__file__).with_name('source_integrity.py').read_text() + '\nPUBLIC_BUNDLE_SOURCE = ' + repr(BUNDLE_SOURCE) + '\n' + '''import hashlib,importlib.metadata,json,os,platform,subprocess,sys
from pathlib import Path
cfg=json.loads(sys.argv[1]); recipe=json.loads(sys.argv[2]); root=Path(cfg['remote_root'])/'model'
checks={}; details=[]
checks['platform']=platform.system()==recipe['platform'] and platform.machine()==recipe['architecture']
checks['python']=platform.python_version()==recipe['python_version']
revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
checks['revision']=revision==recipe['model_revision']
try:
    checks['source']=verify_source(root,recipe['model_revision'],recipe.get('generated_source_hashes'))
except (ValueError,OSError):
    checks['source']=False
try:
    checks['dependencies']=all(importlib.metadata.version(name)==version for name,version in recipe['packages'].items())
except importlib.metadata.PackageNotFoundError:
    checks['dependencies']=False
    details.append('Required runtime dependency is missing')
entrypoint=root/'.venv/bin/rfd4-generate'
checks['entrypoint']=entrypoint.is_file() and os.access(entrypoint,os.X_OK)
if recipe.get('model_bundle'):
    expected=[str(Path(cfg['remote_root'])/'model-bundle'/item['name']) for item in recipe['model_bundle']['files']]
    checks['weights']=cfg.get('weight_paths')==expected
    try:
        namespace={'__name__':'rfd4_bundle_verification'}
        exec(compile(PUBLIC_BUNDLE_SOURCE,'public_model_bundle.py','exec'),namespace)
        checks['weights']=checks['weights'] and namespace['manifest']()==recipe['model_bundle']
        checks['weights']=checks['weights'] and namespace['verify_bundle'](Path(cfg['remote_root'])/'model-bundle')==recipe['model_bundle']
    except (ValueError,OSError,KeyError):
        checks['weights']=False
    if not checks['weights']:details.append('Missing, corrupt or mismatched public model bundle')
else:
    paths={Path(p).name:Path(p) for p in cfg.get('weight_paths',[])}
    checks['weights']=len(paths)==len(recipe['weights'])
    for expected in recipe['weights']:
        path=paths.get(expected['name'])
        valid=path is not None and path.is_file() and not path.is_symlink() and path.stat().st_size==expected['size']
        if valid:
            digest=hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda:f.read(4*1024*1024),b''):digest.update(chunk)
            valid=digest.hexdigest()==expected['sha256']
        checks['weights']=checks['weights'] and valid
        if not valid:details.append('Missing, incomplete or incorrect checkpoint: '+expected['name'])
try:
    import torch
    checks['cuda']=torch.cuda.is_available()
except (ImportError,OSError):
    checks['cuda']=False
    details.append('PyTorch or its native libraries are unavailable')
gpus=[]
if checks['cuda']:
    for i in range(torch.cuda.device_count()):
        p=torch.cuda.get_device_properties(i)
        gpus.append(dict(name=p.name,memory=p.total_memory,capability=list(torch.cuda.get_device_capability(i))))
checks['gpu']=bool(gpus) and gpus[0]['memory']>=recipe['minimum_gpu_memory_bytes'] and gpus[0]['capability']>=recipe['minimum_compute_capability']
print(json.dumps(dict(recipe_id=recipe['id'],checks=checks,gpus=gpus,details=details)))
'''


def inspect(backend, cfg):
    command = shlex.join([cfg['remote_root'] + '/model/.venv/bin/python', '-B', '-c', PROBE,
                          json.dumps(cfg), json.dumps(RECIPE)])
    result = json.loads(backend.target_exec(cfg, command, timeout=300))
    required = {'platform','python','revision','source','dependencies','entrypoint','weights','cuda','gpu'}
    if result.get('recipe_id') != RECIPE['id'] or set(result.get('checks', {})) != required:
        raise ValueError('Runtime returned an incomplete recipe verification')
    if any(type(value) is not bool for value in result['checks'].values()):
        raise ValueError('Runtime returned invalid readiness evidence')
    return result


# Adapter mapping for upstream RFD4GenerationProvider's sampling controls.
#
# Source: atomworks-studio/providers/rfd4/atomworks_studio_rfd4/generation.py.
# Hydra keys: RFD4-Proteina/skills/rfd4-proteina-generate/SKILL.md.
# Molecular interpretation and inference remain in those upstream packages.
#
import math

DEFAULTS = dict(thinking='medium', backbone_noise=0.3, latent_noise=0.1)

def options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - DEFAULTS.keys():
        raise ValueError('Unsupported generation options')
    result = DEFAULTS | value
    if result['thinking'] not in ('low', 'medium', 'high'):
        raise ValueError('Thinking must be low, medium or high')
    for key in ('backbone_noise', 'latent_noise'):
        n = result[key]
        if type(n) not in (int, float) or not math.isfinite(n) or not 0 < n <= 1:
            raise ValueError(f'{key} must be greater than zero and at most one')
    return result

def overrides(value=None):
    v = options(value)
    return [f'recycle_strategy=thinking_{v["thinking"]}',
            f'generation.model.bb_ca.simulation_step_params.sc_scale_noise={v["backbone_noise"]}',
            f'generation.model.local_latents.simulation_step_params.sc_scale_noise={v["latent_noise"]}']


def runtime_overrides(root):
    """Resolve only the locally verified public bundle; never follow Hub main."""
    from pathlib import PurePosixPath
    pass
    path = PurePosixPath(root)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Runtime root must be an absolute path without parent traversal')
    return ['inference_backend=native', 'hf_ckpt_path=' + str(path / 'model-bundle'),
            'hf_ckpt_revision=' + RECIPE['model_bundle']['revision'], '~metrics']
