---
name: nvmolkit-usage
description: "Write code that calls the installed nvMolKit Python API for GPU-accelerated, batched RDKit-style operations - Morgan fingerprints, Tanimoto/cosine similarity, ETKDG conformer embedding, MMFF/UFF optimization, TFD, conformer RMSD, Butina clustering, and substructure search. Use when the user is importing `nvmolkit.*`, debugging an `nvmolkit` call, choosing between nvMolKit and RDKit for a batched cheminformatics workflow, or wiring nvMolKit results into a torch/numpy pipeline. Out of scope: building nvMolKit from source."
license: Apache-2.0 OR CC-BY-4.0
compatibility: Requires an NVIDIA GPU with CUDA 12.6+, torch with CUDA support, and nvmolkit installed.
allowed-tools: Bash, Read, Write
metadata:
  owner: Kevin Boyd (@scal444)
  classification: library-skill
  risk_tier: skill
---

# nvMolKit usage

## What nvMolKit is

GPU-accelerated, batched implementations of common RDKit operations. APIs mirror RDKit where possible but are batch-oriented: they take lists of `rdkit.Chem.Mol` (or lists of fingerprints) and process them in parallel on one or more GPUs. nvMolKit links against RDKit at build time; inputs and outputs are real RDKit `Mol` objects.

## Where nvMolKit does well

Reach for nvMolKit when:

- The workload is **a large batch of molecules** processed together (typically thousands or more).
- The metric is **throughput / total wall time across the batch**, not per-molecule latency.
- The same operation is **repeated identically** across the batch (fingerprinting a library, embedding/minimizing many conformers, bulk pairwise similarity), so the GPU stays saturated.

Plain RDKit is usually the better choice for single-molecule one-offs or workflows that can't be expressed as a batch. nvMolKit is not meant to replace RDKit for those cases.

## Runtime requirements

- An NVIDIA GPU with compute capability 7.0 (V100) or higher
- A CUDA driver compatible with CUDA 12.6+.
- A working `torch` install with CUDA support (nvMolKit returns GPU tensors via `torch`'s CUDA array interface).

If CUDA is unavailable, nvMolKit calls raise. There is no CPU fallback - if the user needs one, use RDKit directly for that path.

## Verify the install before writing real code

Run this once to confirm nvMolKit is importable and a GPU op works end to end:

```python
import nvmolkit
import torch
from rdkit import Chem
from nvmolkit.fingerprints import MorganFingerprintGenerator

print("nvmolkit:", nvmolkit.__version__)
print("cuda available:", torch.cuda.is_available())
print("device count:", torch.cuda.device_count())

mols = [Chem.MolFromSmiles(smi) for smi in ["CCO", "c1ccccc1", "CC(=O)O"]]
fpgen = MorganFingerprintGenerator(radius=2, fpSize=1024)
result = fpgen.GetFingerprints(mols)
torch.cuda.synchronize()
fps = result.torch()
print("fps shape:", tuple(fps.shape), "dtype:", fps.dtype)
# Expected: shape (3, 32), dtype torch.int32  (1024 bits packed into 32 int32s per row)
```

If this fails, point the user at the install guide on the docs site rather than guessing - see "Going deeper" below.

## Entry points

| Task | Module | Primary entry point |
|---|---|---|
| Morgan fingerprints | `nvmolkit.fingerprints` | `MorganFingerprintGenerator(radius, fpSize).GetFingerprints(mols)` |
| Bulk Tanimoto / cosine similarity | `nvmolkit.similarity` | `crossTanimotoSimilarity(...)`, `crossCosineSimilarity(...)`, plus `*MemoryConstrained` variants for results too large to fit in GPU memory |
| ETKDG conformer embedding | `nvmolkit.embedMolecules` | `EmbedMolecules(molecules, params, confsPerMolecule, ...)` |
| MMFF94 optimization (one-shot) | `nvmolkit.mmffOptimization` | `MMFFOptimizeMoleculesConfs(molecules, ...)` |
| UFF optimization (one-shot) | `nvmolkit.uffOptimization` | `UFFOptimizeMoleculesConfs(molecules, ...)` |
| Forcefield with custom options + constraints | `nvmolkit.batchedForcefield` | `MMFFBatchedForcefield(mols, properties=..., nonBondedThreshold=..., ignoreInterfragInteractions=..., hardwareOptions=...)`, `UFFBatchedForcefield(mols, vdwThreshold=..., ...)`. Per-molecule view `ff[i]` exposes `add_distance_constraint`, `add_position_constraint`, `add_angle_constraint`, `add_torsion_constraint`. Methods: `.compute_energy()`, `.compute_gradients()`, `.minimize(maxIters, forceTol)` |
| Pairwise conformer RMSD | `nvmolkit.conformerRmsd` | `GetConformerRMSMatrix(mol)`, `GetConformerRMSMatrixBatch(mols)` |
| Torsion Fingerprint Deviation (TFD) | `nvmolkit.tfd` | `GetTFDMatrix(mol)`, `GetTFDMatrices(mols)` |
| Butina clustering | `nvmolkit.clustering` | `butina(distance_matrix, cutoff)` (precomputed matrix), `fused_butina(fingerprints, cutoff)` (memory-efficient, on-the-fly) |
| Substructure search | `nvmolkit.substructure` | `hasSubstructMatch`, `countSubstructMatches`, `getSubstructMatches` |
| Hardware tuning (batch size, GPU IDs) | `nvmolkit.types` | `HardwareOptions(...)` passed to ETKDG / MMFF / UFF |
| Optional autotuning of `HardwareOptions` | `nvmolkit.autotune` | `tune_embed_molecules`, `tune_mmff_optimize`, `tune_uff_optimize`, `tune_batched_forcefield`. Requires the `optuna` package |

## Result types and execution model

Two return shapes carry GPU-resident output, depending on what the operation produces.

### `AsyncGpuResult`

Used by operations that return a single flat tensor (fingerprints, similarity matrices, RMSD/TFD vectors, Butina inputs). Key behaviors:

- Asynchronous. The kernel may not have completed when the call returns.
- `result.torch()` returns a zero-copy `torch.Tensor` on the GPU. Caller is responsible for synchronizing before reading values on the host.
- `result.numpy()` synchronizes and returns a CPU numpy array.
- Exposes `__cuda_array_interface__`, so it can be passed directly into other nvMolKit functions (e.g. fingerprints → similarity) with no host round-trip.

#### CUDA stream control

A subset of the `AsyncGpuResult`-returning APIs accept an optional `stream: torch.cuda.Stream | None = None` argument so callers can submit nvMolKit work to a non-default stream and overlap it with their own kernels. When omitted, the call uses the current torch stream.

APIs that take a `stream` argument:

- `MorganFingerprintGenerator.GetFingerprints`
- `crossTanimotoSimilarity`, `crossCosineSimilarity`, and their `*MemoryConstrained` variants
- `butina`, `fused_butina`
- `GetConformerRMSMatrix`, `GetConformerRMSMatrixBatch`

Other APIs (ETKDG, MMFF/UFF optimization, TFD, substructure search) are synchronous to the caller — no stream plumbing needed.

Typical pattern:

```python
import torch
from rdkit import Chem
from nvmolkit.fingerprints import MorganFingerprintGenerator
from nvmolkit.similarity import crossTanimotoSimilarity

stream = torch.cuda.Stream()
fpgen = MorganFingerprintGenerator(radius=2, fpSize=1024)
mols = [Chem.MolFromSmiles(smi) for smi in ["CCO", "c1ccccc1", "CC(=O)O"]]

with torch.cuda.stream(stream):
    fps = fpgen.GetFingerprints(mols, stream=stream)
    sim = crossTanimotoSimilarity(fps, stream=stream)
stream.synchronize()
print(sim.torch())
```

### `Device3DResult`

Used by ETKDG embedding and MMFF/UFF optimization (one-shot and `BatchedForcefield`) when called with `output=CoordinateOutput.DEVICE`. The GPU-resident equivalent of writing conformers back to `Mol` objects. Fields:

- `values`: `AsyncGpuResult` of shape `(total_atoms, 3)` float64. Concatenated conformer coordinates in CSR-style layout.
- `atom_starts`, `mol_indices`, `conf_indices`: `AsyncGpuResult` int32 buffers describing the layout (`values[atom_starts[i]:atom_starts[i+1]]` is conformer `i`'s atoms).
- `energies`, `converged`: `AsyncGpuResult` buffers populated only for MMFF/UFF minimization (not for plain ETKDG).
- `gpu_id`: device the buffers live on. The `targetGpu` argument on each API picks this; `targetGpu=-1` uses the default consolidation device.
- `.per_molecule()` returns nested `list[list[torch.Tensor]]` of per-conformer views; `.dense(pad_value=nan)` materializes a padded `(n_mols, max_confs, max_atoms, 3)` tensor.

The default mode (`CoordinateOutput.RDKIT_CONFORMERS`) still writes optimized coordinates back into each `Mol` and returns Python lists of energies/convergence flags. Reach for `CoordinateOutput.DEVICE` when chaining downstream GPU work (e.g. ETKDG → MMFF → similarity scoring) without host round-trips.

## Configuration

Two configuration objects expose the GPU/CPU knobs.

### `HardwareOptions` (ETKDG, MMFF, UFF)

`from nvmolkit.types import HardwareOptions`. Passed via `hardwareOptions=` to `EmbedMolecules`, `MMFFOptimizeMoleculesConfs`, `UFFOptimizeMoleculesConfs`, and the `BatchedForcefield` constructors. Every field has an "auto" sentinel; the defaults are usually fine.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `preprocessingThreads` | int | `-1` (all visible CPUs) | CPU threads for preprocessing |
| `batchSize` | int | `-1` (auto-tuned) | Number of conformers per GPU batch |
| `batchesPerGpu` | int | `-1` (auto) | Concurrent batches per GPU; must be `>0` or `-1` |
| `gpuIds` | `list[int]` | `[]` (all visible GPUs) | Specific device ordinals to target |

Passing a `gpuIds` entry for a device that isn't visible raises `RuntimeError: invalid device ordinal`. For finding good values automatically across a representative sample, see `nvmolkit.autotune` (requires the `optuna` extra); each `tune_*` function returns a `TuneResult` whose `best_config` is a fully-populated `HardwareOptions` ready to pass back into the real call.

`HardwareOptions` round-trips through `to_dict()` / `from_dict()` for persisting tuned configs to disk.

### `SubstructSearchConfig` (substructure search)

`from nvmolkit.substructure import SubstructSearchConfig`. Passed via `config=` to `hasSubstructMatch`, `countSubstructMatches`, and `getSubstructMatches`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `batchSize` | int | `1024` | (target, query) pairs per GPU batch |
| `workerThreads` | int | `-1` (auto) | GPU runner threads per GPU |
| `preprocessingThreads` | int | `-1` (auto) | CPU threads for preprocessing |
| `maxMatches` | int | `0` (unlimited) | Max matches returned per (target, query) pair |
| `uniquify` | bool | `False` | Drop duplicate matches that differ only in atom enumeration order |
| `gpuIds` | `list[int] \| None` | `None` (current device only) | Specific device ordinals to target |

Substructure search currently does not support chirality-aware matching, enhanced stereochemistry, or other advanced RDKit `SubstructMatchParameters` options.

## Recipes

### Morgan fingerprints + bulk Tanimoto similarity

```python
import torch
from rdkit import Chem
from nvmolkit.fingerprints import MorganFingerprintGenerator
from nvmolkit.similarity import crossTanimotoSimilarity

smiles = ["CCO", "CCN", "c1ccccc1", "CC(=O)O", "CCOCC"]
mols = [Chem.MolFromSmiles(smi) for smi in smiles]

fpgen = MorganFingerprintGenerator(radius=2, fpSize=1024)
fps = fpgen.GetFingerprints(mols)

sim = crossTanimotoSimilarity(fps)
torch.cuda.synchronize()
print(sim.torch())
```

Inputs are `list[Mol]`. Output of `GetFingerprints` is an `AsyncGpuResult` wrapping an `(n_mols, fpSize / 32)` int32 tensor of packed bits. Pass it straight into `crossTanimotoSimilarity` for an `(n, n)` similarity matrix; pass two fingerprint sets for an `(n, m)` cross-matrix. For sets too large to materialize on the GPU, use `crossTanimotoSimilarityMemoryConstrained` (chunked compute, returns numpy on CPU).

### ETKDG conformer embedding

```python
from rdkit.Chem import AddHs, MolFromSmiles
from rdkit.Chem.rdDistGeom import ETKDGv3
from nvmolkit.embedMolecules import EmbedMolecules

mols = [AddHs(MolFromSmiles(smi)) for smi in ["C1CCCCC1", "C1CCCCC2CCCCC12", "COO"]]
params = ETKDGv3()
params.useRandomCoords = True

EmbedMolecules(mols, params, confsPerMolecule=10, maxIterations=-1)

for mol in mols:
    print(mol.GetNumConformers())
```

Inputs are `list[Mol]`, sanitized and with hydrogens added (`AddHs`). Conformers are added in-place. `params.useRandomCoords` must be `True` - nvMolKit's ETKDG only supports random-coord initialization. A handful of niche `EmbedParameters` options are not supported (bounds matrices, custom CPCI, coord maps, separate-fragment embedding); the Features section of the docs site lists the full restrictions.

### MMFF94 minimization of a batch of conformers

```python
from rdkit.Chem import AddHs, MolFromSmiles
from rdkit.Chem.rdDistGeom import ETKDGv3
from nvmolkit.embedMolecules import EmbedMolecules
from nvmolkit.mmffOptimization import MMFFOptimizeMoleculesConfs

mols = [AddHs(MolFromSmiles(smi)) for smi in ["CCO", "CCN", "c1ccccc1"]]
params = ETKDGv3(); params.useRandomCoords = True
EmbedMolecules(mols, params, confsPerMolecule=5)

energies = MMFFOptimizeMoleculesConfs(mols, maxIters=500)
for mol, mol_energies in zip(mols, energies):
    print(mol.GetNumConformers(), mol_energies)
```

Inputs are `list[Mol]` with conformers already populated (typically by ETKDG, RDKit's `EmbedMultipleConfs`, or a prior nvMolKit call). Coordinates are updated in place; the return is `list[list[float]]` of optimized energies aligned with the input molecule order and conformer index. UFF is identical in shape: swap in `from nvmolkit.uffOptimization import UFFOptimizeMoleculesConfs`.

If any input molecule is `None` or lacks MMFF/UFF atom types, the call raises `ValueError`. The exception's `args[1]` is a dict with keys `"none"` and `"no_params"` listing the offending indices - useful for filtering a noisy input set.

### Custom forcefield options + constraints (`BatchedForcefield`)

Reach for `MMFFBatchedForcefield` / `UFFBatchedForcefield` instead of the one-shot `MMFFOptimizeMoleculesConfs` / `UFFOptimizeMoleculesConfs` when you need any of:

- Custom `maxIters` / `forceTol` per call
- Per-molecule `nonBondedThreshold` (MMFF) or `vdwThreshold` (UFF), or per-molecule `ignoreInterfragInteractions`
- Per-molecule `MMFFMolProperties` objects (e.g. MMFF94s vs MMFF94)
- Distance, position, angle, or torsion constraints
- Standalone `compute_energy()` / `compute_gradients()` without minimization

```python
from rdkit.Chem import AddHs, MolFromSmiles
from rdkit.Chem.rdDistGeom import EmbedMultipleConfs
from nvmolkit.batchedForcefield import MMFFBatchedForcefield

mols = [AddHs(MolFromSmiles(smi)) for smi in ["CCO", "CCCCCC"]]
for mol in mols:
    EmbedMultipleConfs(mol, numConfs=5)

ff = MMFFBatchedForcefield(
    mols,
    nonBondedThreshold=[100.0, 20.0],
    ignoreInterfragInteractions=True,
)

ff[0].add_position_constraint(0, max_displ=0.1, force_constant=50.0)
ff[1].add_distance_constraint(0, 4, relative=False, min_len=1.8, max_len=2.2, force_constant=25.0)

energies, converged = ff.minimize(maxIters=500, forceTol=1e-4)
for mol, mol_energies, mol_converged in zip(mols, energies, converged):
    print(mol.GetNumConformers(), mol_energies, mol_converged)
```

All conformers of each input molecule are minimized in one batch. Constraints attached via `ff[i].add_*_constraint(...)` apply to every conformer of molecule `i`; constraint setters mark the wrapper dirty and the native forcefield rebuilds on the next call. Pass `output=CoordinateOutput.DEVICE` to `.minimize(...)` to keep optimized coordinates on the GPU (`Device3DResult`) instead of writing them back into RDKit conformers. UFF is the same shape: `UFFBatchedForcefield(mols, vdwThreshold=..., ...)`.

## Going deeper

- Full feature list, API reference, and guides: <https://nvidia-bionemo.github.io/nvMolKit/>
- What changed in each release: <https://nvidia-bionemo.github.io/nvMolKit/changelog.html>
- Worked examples (Jupyter notebooks): the `examples/` directory in the GitHub repo
