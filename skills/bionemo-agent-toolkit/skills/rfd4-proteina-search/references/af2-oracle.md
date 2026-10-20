# The AF2 oracle

AF2Oracle is the protein-only counterpart to AF3Oracle. It refolds monomers
with `model_1_ptm` and protein complexes with `model_1_multimer_v3`, then
publishes the standard oracle confidence metrics and caches the refolded CIF.

Enable it through `configs/metrics/refolding_oracles/af2.yaml`. The `oracle`
entry handles monomers; `oracle_ppi` templates atoms selected by
the derived `C_CRD` mask. Inputs containing ligands, nucleic acids, or `UNL`
are rejected before dispatch. Search checkpoints explicitly list `oracle` or
`oracle_ppi` in `metrics`; ordinary final evaluation selects them through
`metrics_tags`.

Optional ColabFold knobs on `AF2Oracle` / manifest (defaults preserve stock AF2):

- `initial_guess` (bool, default `false`): seed recycle `prev_pos` from the
  design CIF via `all_atom_positions` (requires the colabfold model overlay).
- `pct_seq_mask` (float in `[0, 1]`, default `0.15`): BERT MSA
  `replace_fraction`; set `0` to disable inference masking stochasticity.

The runtime requires `AF2_IMAGE`, `AF2_MODEL_DIR`, and
`AF2_JAX_CACHE_DIR`. `AF2_RESIDENT_MODELS` defaults to
`model_1_ptm,model_1_multimer_v3`. On Apptainer clusters,
`launch_generate.sh` and `launch_evaluate.sh` start one resident daemon per GPU;
without a launcher, `AF2Oracle.setup()` starts a rank-local daemon.

Build `AF2_IMAGE` manually by layering the public
`alphafold-colabfold==2.3.18` package over the DeepMind CUDA-12 base. The AF2
runtime README contains the cbuild, squash export, Apptainer conversion, and
canonical artifact-upload commands; build implementation files are
intentionally not stored in the repository.
Pallas is enabled by default (`AF2_USE_PALLAS=true`) and requires bf16 plus an
NVIDIA compute capability 8.0 or newer GPU. `AF2_COMPILE_MODE` is `tuned` by
default and also accepts `fast` or `full`. Use a new `AF2_JAX_CACHE_DIR` after
changing images.

Within each manifest, the worker stable-sorts inputs by resident model and
discrete residue bucket. This preserves one-design-at-a-time inference while
keeping equal JAX compile shapes contiguous.

Results are cached under the same canonical oracle confidence/refolded-CIF
paths used by other refolding oracles, so repeated scoring skips completed
designs.
