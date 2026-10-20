"""Small host compatibility fixes for the pinned AtomWorks Studio editor.

AtomWorks' default atomize annotation adds derived classification fields lazily.
When only one input needs that default, strict concatenation sees unequal fields.
Compute those fields consistently on copies; never drop mismatched annotations.
"""
import copy
import hashlib
import inspect

EXPECTED_SOURCE = {
    'studio_combine': '803146013549a4f265139cc3c8a2cab8a3a1a8a07d5cfc994dd0a56c0c643de9',
    'atomworks_concatenate': 'a7082201db5e41b9eaba46f3d8f1f00674ed632f464cafc41cfdd473da4a753b',
}


def verify_compatibility_sources(functions):
    actual = {name: hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()
              for name, fn in functions.items()}
    if actual != EXPECTED_SOURCE:
        raise ValueError('The editor dependency changed; qualify the Combine compatibility adapter before starting')
    return actual


def concatenate_with_classifications(arrays, **kwargs):
    from atomworks.io.utils.annotator import ensure_annotations
    from atomworks.io.utils.atom_array_plus import concatenate_atom_array_plus
    prepared = [copy.deepcopy(array) for array in arrays]
    if kwargs.get('fill_missing_standard_annotations'):
        for array in prepared:
            ensure_annotations(array, 'is_polymer', 'is_standard_aa', 'is_standard_dna', 'is_standard_rna')
    return concatenate_atom_array_plus(prepared, **kwargs)
