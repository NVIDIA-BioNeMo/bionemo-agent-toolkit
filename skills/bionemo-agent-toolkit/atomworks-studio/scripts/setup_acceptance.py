"""Validate setup evidence against the immutable reviewed recipe."""
import hashlib
import json
from pathlib import PurePosixPath
import re

REQUIRED={'platform','python','revision','source','dependencies','entrypoint','weights','cuda','gpu'}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate(review, receipt):
    recipe=review.get('recipe')
    if not isinstance(recipe,dict) or digest(recipe)!=review.get('recipe_checksum'):
        raise ValueError('Reviewed setup recipe is missing or changed')
    if receipt.get('operation_id')!=review['operation_id'] or receipt.get('recipe_checksum')!=review['recipe_checksum'] or receipt.get('recipe_id')!=recipe['id'] or receipt.get('stage')!='accepted' or receipt.get('ready') is not True:
        raise ValueError('Setup receipt does not match the reviewed recipe and operation')
    evidence=receipt.get('evidence',{})
    checks=evidence.get('checks',{})
    if evidence.get('recipe_id')!=recipe['id'] or set(checks)!=REQUIRED or any(value is not True for value in checks.values()):
        raise ValueError('Setup receipt lacks successful runtime verification')
    post=receipt.get('post_smoke_evidence',{})
    if post.get('recipe_id')!=recipe['id'] or set(post.get('checks',{}))!=REQUIRED or any(value is not True for value in post['checks'].values()):
        raise ValueError('Setup receipt lacks successful post-inference runtime verification')
    root=PurePosixPath(review['remote_root'])
    expected=([str(root/'model-bundle'/w['name']) for w in recipe['model_bundle']['files']]
              if recipe.get('model_bundle') else [str(root/'model/data_path'/w['directory']/w['name']) for w in recipe['weights']])
    if receipt.get('weight_paths')!=expected:
        raise ValueError('Verified checkpoint paths differ from the reviewed recipe')
    smoke=receipt.get('smoke',{})
    output=PurePosixPath(smoke.get('output_dir',''))
    if smoke.get('operation_id')!=review['operation_id'] or smoke.get('recipe_checksum')!=review['recipe_checksum'] or smoke.get('example')!='monomer-short' or '..' in output.parts or output.parent!=root/'setup-smoke':
        raise ValueError('Smoke evidence has the wrong operation or output identity')
    structures=smoke.get('structures')
    if not isinstance(structures,list) or not structures:
        raise ValueError('Smoke evidence lacks validated structures')
    seen=set()
    for entry in structures:
        if not isinstance(entry,dict):raise ValueError('Malformed smoke structure evidence')
        path=PurePosixPath(entry.get('path',''))
        if path.is_absolute() or '..' in path.parts or path.suffix!='.cif' or str(path) in seen:
            raise ValueError('Invalid smoke artifact path')
        seen.add(str(path))
        if type(entry.get('atoms')) is not int or entry['atoms']<1 or type(entry.get('size')) is not int or entry['size']<1 or not re.fullmatch('[0-9a-f]{64}',entry.get('sha256','')):
            raise ValueError('Invalid smoke artifact integrity evidence')
    return expected
