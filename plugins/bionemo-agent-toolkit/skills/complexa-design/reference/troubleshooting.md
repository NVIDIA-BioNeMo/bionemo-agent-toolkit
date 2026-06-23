# Troubleshooting Reference

Symptoms, causes, and fixes for `complexa design` failures. Sourced from
`docs/INFERENCE.md` "Troubleshooting", `docs/EVALUATION_METRICS.md`, and the
pipeline configs themselves.

## GPU OOM during generation

**Symptom:** `torch.cuda.OutOfMemoryError` during the `generate` step;
process dies before the first PDB is written.

**Cause:** Default `generation.dataloader.batch_size: 16` is tuned for 80 GB
A100/H100. On a 40 GB GPU the latent flow-matching forward pass overflows.
Beam-search amplifies this because `max_batch_size` inherits from
`batch_size` and multiple beams run concurrently.

**Fix:**

```bash
++generation.dataloader.batch_size=8
++gen_njobs=1
```

If still OOMing, drop to `batch_size=4` and `++generation.args.nsteps=200` to
shrink activation history. Reference: `docs/INFERENCE.md` "Memory Issues".

## GPU OOM during folding

**Symptom:** OOM during the `evaluate` step, typically after the AF2 or RF3
model is loaded.

**Cause:** Multiple eval jobs share the GPU; ColabDesign with
`num_recycles: 3` and `num_redesign_seqs > 2` keeps a large state tree.

**Fix:**

```bash
++eval_njobs=1
++metric.num_redesign_seqs=2
++metric.sequence_types=[self]      # skip mpnn / mpnn_fixed redesigns
```

For RF3 specifically, also lower `++metric.num_redesign_seqs=1` — RF3 carries a
heavier per-sample state than AF2.

## Missing `AF2_DIR` (colabdesign fails)

**Symptom:** Hydra `InterpolationKeyError: AF2_DIR` raised when the reward
model or the evaluator tries to resolve `${oc.env:AF2_DIR}`.

**Cause:** The protein binder pipeline's `af2folding` reward model and the
default `binder_folding_method: colabdesign` both read `AF2_DIR` from the
environment. If `.env` does not define it, Hydra interpolation fails.

**Fix:** Add `AF2_DIR=/path/to/af2_params` to `.env`, or switch the eval
backend to ESMFold (does not need AF2 weights):

```bash
++metric.binder_folding_method=esmfold
```

Run `complexa download --all` to fetch AF2 weights into the canonical
location. Reference: `docs/INFERENCE.md` "Missing Model Weights".

## Missing `RF3_CKPT_PATH` / `RF3_EXEC_PATH` (rf3_latest fails)

**Symptom:** `InterpolationKeyError: RF3_CKPT_PATH` or `RF3_EXEC_PATH` during
generate (ligand binder) or evaluate (ligand binder, AME).

**Cause:** Ligand binder and AME pipelines bake `${oc.env:RF3_CKPT_PATH}` and
`${oc.env:RF3_EXEC_PATH}` into the RF3 reward and refold paths. RF3 is not
downloaded by `complexa download --complexa-*`; it ships with the community
model bundle.

**Fix:** Export both env vars (or set them in `.env`):

```bash
export RF3_CKPT_PATH=/path/to/rf3_latest.pt
export RF3_EXEC_PATH=/path/to/rf3
```

Run `complexa download --all` to install RF3 into the canonical location.
Reference: `docs/INFERENCE.md` "RF3 Environment Variables".

## Chain-ID mismatch between target PDB and `target_input`

**Symptom:** Target loads but `n_target_residues == 0` after dataloader runs;
or `KeyError: 'A'` raised by the target featurizer.

**Cause:** The `target_input` field in the targets dict (e.g. `A1-115`)
specifies chain A, but the PDB uses chain B (or unlabelled chains).

**Fix:** Inspect the target PDB:

```bash
grep '^ATOM' /path/to/target.pdb | head -1   # check chain ID at col 22
```

Then update the target entry in `configs/targets/targets_dict.yaml` so
`target_input` matches the actual chain. Or use the `complexa-target` skill to
re-add the target with the correct chain.

## Hotspot residue not in target PDB

**Symptom:** Warning / error from `TargetFeatures` that hotspot residue
`A45` does not exist; or hotspots silently dropped, leading to non-specific
binders.

**Cause:** `hotspot_residues: [A45, A67, A89]` references residues that the
PDB does not contain — usually because the PDB has been re-numbered or the
chain has been truncated.

**Fix:** Pull the actual residue numbers:

```bash
grep '^ATOM' /path/to/target.pdb | awk '{print $5, $6}' | sort -u
```

Update `hotspot_residues` to a subset of residues that exist in `target_input`.

## AME requires `USE_V2_COMPLEXA_ARCH: "True"`

**Symptom:** Shape mismatch or `KeyError` at model-load time when running the
AME pipeline.

**Cause:** AME uses the v2 architecture. The `search_ame_local_pipeline.yaml`
sets `env_vars.USE_V2_COMPLEXA_ARCH: "True"`, but a stray
`++env_vars.USE_V2_COMPLEXA_ARCH=False` override (or a stale shell export)
flips it back.

**Fix:** Do not override `USE_V2_COMPLEXA_ARCH`. If a shell export is set, unset
it:

```bash
unset USE_V2_COMPLEXA_ARCH
```

Reference: `configs/search_ame_local_pipeline.yaml` line 22.

## AME ligand residue name must be `L:0` for RF3

**Symptom:** RF3 reward model raises a residue-name parse error during AME
generation; or the ligand silently disappears from the refolded structure.

**Cause:** RF3 expects the ligand HETATM residue named `L` with sequence-number
`0` (canonical AME convention). PDBs downloaded from RCSB usually have
arbitrary ligand residue names (e.g. `OQO`, `FAD`, `ATP`).

**Fix:** Use `atomworks` (the renaming tool) to rewrite the ligand residue:

```bash
python -m atomworks rename_ligand \
    --in /path/to/target.pdb \
    --out /path/to/target_renamed.pdb \
    --target-resname L \
    --target-resnum 0
```

Update the AME task in `configs/design_tasks/ame_dict_v2.yaml` to point at the
renamed PDB. Reference: README in `target_data/` and the AME task definitions.

## Override key not recognized

**Symptom:** Hydra raises `InterpolationKeyError`, `MissingMandatoryValue`,
or "Could not override 'X'" when launching the pipeline.

**Cause:** Hydra `+` requires the key to already exist in the merged config;
`++` forces a new key. If a typo lands inside an existing key path, the error
looks like a missing value.

**Fix:** Always use `++` for design pipeline overrides (the pipeline composes
multiple configs and key existence varies by stage). Re-check the key against
`reference/overrides.md`.

Note: `complexa validate design` will **not** catch a bad override key. The
`validate` subcommand rejects `++` arguments outright ("unrecognized
arguments") and, even given a bare config, reads the YAML as written without
applying overrides — so it cannot surface unknown override keys. Validate the
bare config for ckpt/weight/target problems, but to catch a typo'd override key
you must launch and read Hydra's error (or dry-check the key against
`reference/overrides.md` first):

```bash
complexa validate design <pipeline_config>     # ckpts + weights + config-default target; NO ++overrides
```

## Missing checkpoint reported by `complexa download --status`

**Symptom:** `complexa download --status` lists a Complexa or community model
as `Missing`, and the pipeline fails immediately at the load step.

**Cause:** The relevant `complexa download --complexa-<variant>` or
`complexa download --all` has not been run, or the download was interrupted.

**Fix:**

```bash
complexa download --status                     # see what is missing
complexa download --complexa                   # protein binder weights
complexa download --complexa-ligand            # ligand binder weights
complexa download --complexa-ame               # AME / motif weights
complexa download --all                        # community models (AF2, RF3, MPNN, ESM2)
```

Hand off to the `complexa-setup` skill if the `.env` is also incomplete.

## ColabDesign env var missing

**Symptom:** ColabDesign fails on import or at AF2-params load with
`FileNotFoundError`.

**Cause:** `AF2_DIR` is set to a directory that does not contain
`params_model_*.npz` files, or the path is correct but does not exist.

**Fix:**

```bash
ls $AF2_DIR | grep '^params_model'
```

If empty, re-download:

```bash
complexa download --all
```

Or point `AF2_DIR` at the correct directory in `.env`.

## ProteinMPNN / LigandMPNN model directory missing

**Symptom:** Evaluation fails at the inverse-folding step with
`FileNotFoundError` on the MPNN weights directory.

**Cause:** The inverse-folding model is part of the community bundle, not the
Complexa bundle. `complexa download --complexa*` does not fetch it.

**Fix:**

```bash
complexa download --all
```

Or fetch the specific MPNN you need (LigandMPNN for ligand / AME pipelines,
SolubleMPNN for protein binder, ProteinMPNN for the motif designability
calculation). All three live under the community-model directory.

## Inverse folder returns 0 sequences

**Symptom:** Per-design CSV has empty `{seq}_sequence` columns; success rate
is 0% even though designs visually look reasonable.

**Cause:** The target is too short, the interface cutoff is too tight, or the
binder length is constrained so heavily that the MPNN sampler cannot find a
sequence consistent with the fixed positions.

**Fix:** Loosen the interface cutoff and re-run:

```bash
++metric.interface_cutoff=10.0
++metric.num_redesign_seqs=8
```

If the binder is shorter than ~30 residues, also expand
`generation.dataloader.dataset.nres.low/high` — the MPNN models are unreliable
at very short lengths.

## 0 designs pass success thresholds

**Symptom:** Pipeline completes, `res_filter_*_pass_*.csv` shows
`pass_rate: 0.0`. Per-design metrics look plausible but nothing passes.

**Cause:** Default thresholds are tuned for the published targets (PDL1,
TrkA, etc.) and may be too strict for harder targets or smaller search
budgets.

**Fix:** Loosen the thresholds via the aggregation overrides:

```bash
++aggregation.success_thresholds.i_pAE.threshold=10.0       # was 7.0
++aggregation.success_thresholds.pLDDT.threshold=0.8        # was 0.9
++aggregation.success_thresholds.scRMSD.threshold=2.0       # was 1.5
```

Or re-run analyze alone with the new thresholds — no need to re-generate:

```bash
complexa analyze configs/search_binder_local_pipeline.yaml ++run_name=<same> ++aggregation.success_thresholds.i_pAE.threshold=10.0
```

Reference: `docs/EVALUATION_METRICS.md` "Customizing Binder Thresholds".

