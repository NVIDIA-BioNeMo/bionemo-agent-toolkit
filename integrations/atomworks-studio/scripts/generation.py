"""Adapter mapping for upstream RFD4GenerationProvider's sampling controls.

Source: atomworks-studio/providers/rfd4/atomworks_studio_rfd4/generation.py.
Hydra keys: RFD4-Proteina/skills/rfd4-proteina-generate/SKILL.md.
Molecular interpretation and inference remain in those upstream packages.
"""
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
    from runtime_recipe import RECIPE
    path = PurePosixPath(root)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Runtime root must be an absolute path without parent traversal')
    return ['inference_backend=native', 'hf_ckpt_path=' + str(path / 'model-bundle'),
            'hf_ckpt_revision=' + RECIPE['model_bundle']['revision'], '~metrics']
