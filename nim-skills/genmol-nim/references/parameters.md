# GenMol Parameter Guidance

GenMol uses one `/generate` endpoint. The `smiles` field name is misleading:
it expects SAFE notation, not ordinary SMILES, for conditioned generation.

## SAFE Patterns

- De novo: `[*{20-30}]`
- Scaffold decoration: `<scaffold_safe>.[*{10-15}]`
- Motif extension: `[*{5-10}].<core_safe>.[*{5-10}]`
- Lead optimization: encode the hit molecule, then replace one fragment with
  `[*{5-12}]`

Wider mask ranges increase diversity. Tight mask ranges keep analog size more
controlled.

## Request Parameters

- `num_molecules`: 1-1000. Request more than the desired display count when
  filtering may reduce the output count.
- `temperature`: string, not float. Use `"1.0"` for baseline; increase for more
  diversity.
- `noise`: string, not float. Use `"1.0"` for baseline; increase for more
  stochastic output.
- `step_size`: 1-10. Keep at `1` in examples unless the user asks to tune speed.
- `scoring`: `"QED"` for drug-likeness or `"LogP"` for lipophilicity.
- `unique`: set `True` when the user asks for non-duplicate analogs.

## SAFE Conversion

Use `safe-mol` for SMILES-to-SAFE conversion:

```python
import safe as sf

try:
    safe_str = sf.encode(scaffold_smiles)
except sf.SAFEFragmentationError:
    safe_str = scaffold_smiles
```

Mention that `safe-mol` is not needed for pure de novo generation.
