# Override Reference

Every common `++` override grouped by stage. Each row: key, type, default,
example, what it controls. Defaults come from the actual YAML files under
`configs/pipeline/` — when this doc disagrees with the config, the config
wins.

All overrides use Hydra `++` (forced) syntax — `+` would error on keys not
already in the config. Apply to a `complexa design` invocation; they propagate
to all four stages (generate, filter, evaluate, analyze).

## Top-level (pipeline YAML)

These live at the root of `configs/search_*_pipeline.yaml`.

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `run_name` | str | (config stem, e.g. `search_binder_local`) | `++run_name=pdl1_v1` | Suffix for output dirs and log file names |
| `ckpt_path` | str | `${oc.env:CKPT_PATH}` | `++ckpt_path=/data/ckpts` | Directory containing the model and AE checkpoints |
| `ckpt_name` | str | per pipeline: `complexa.ckpt` / `complexa_ligand.ckpt` / `complexa_ame.ckpt` | `++ckpt_name=complexa.ckpt` | Which model checkpoint to load |
| `autoencoder_ckpt_path` | str | `${oc.env:CKPT_PATH}/complexa[_ligand\|_ame]_ae.ckpt` | `++autoencoder_ckpt_path=/data/my_ae.ckpt` | AE checkpoint path |
| `seed` | int | `5` | `++seed=42` | Sampling RNG seed |
| `ncpus_` | int | `24` | `++ncpus_=16` | CPU count for dataloader workers |
| `gen_njobs` | int | `2` (binder/ligand/AME) | `++gen_njobs=4` | Number of parallel generate jobs |
| `eval_njobs` | int | `2` (binder/ligand/AME) | `++eval_njobs=4` | Number of parallel evaluate jobs |
| `lora.r` | int | `32` (ligand/AME), (unset for protein binder) | `++lora.r=64` | LoRA rank |
| `lora.lora_alpha` | float | `64.0` | `++lora.lora_alpha=128.0` | LoRA scaling factor (typically 2x rank) |
| `lora.lora_dropout` | float | `0.0` | `++lora.lora_dropout=0.1` | Dropout on LoRA inputs |
| `lora.train_bias` | enum | `none` | `++lora.train_bias=lora_only` | Bias training: `none`, `all`, `lora_only` |
| `env_vars.USE_V2_COMPLEXA_ARCH` | str | `"True"` (AME), unset (binder/ligand) | `++env_vars.USE_V2_COMPLEXA_ARCH=True` | Architecture toggle; injected into subprocess env |

## Generation — target and dataloader

Group `generation.*`. See `configs/pipeline/binder/binder_generate.yaml` and
the per-pipeline variants.

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.task_name` | str | per config (e.g. `33_TrkA`, `39_7V11_LIGAND`, `M0096_1chm`) | `++generation.task_name=02_PDL1` | Target / AME task; must be a key in the relevant dict |
| `generation.dataloader.batch_size` | int | `16` (binder/ligand/AME) | `++generation.dataloader.batch_size=8` | Samples per forward pass; drop on OOM |
| `generation.dataloader.dataset.nres.low` | int | per-target binder_length[0] | `++generation.dataloader.dataset.nres.low=80` | Minimum binder / scaffold length |
| `generation.dataloader.dataset.nres.high` | int | per-target binder_length[1] | `++generation.dataloader.dataset.nres.high=120` | Maximum binder / scaffold length |
| `generation.dataloader.dataset.nres.nsamples` | int | `4` (binder), `2` (ligand), `4` (AME) | `++generation.dataloader.dataset.nres.nsamples=200` | Number of length samples per pipeline |
| `generation.dataloader.dataset.nres.endpoint` | bool | `true` | `++generation.dataloader.dataset.nres.endpoint=false` | Include high in length range |
| `generation.dataloader.dataset.nrepeat_per_sample` | int | `1` | `++generation.dataloader.dataset.nrepeat_per_sample=4` | How many designs per length sample |

## Generation — diffusion sampling (`generation.args.*`)

From `configs/pipeline/model_sampling.yaml`.

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.args.nsteps` | int | `400` | `++generation.args.nsteps=200` | Diffusion / flow-matching steps; lower = faster, lower quality |
| `generation.args.self_cond` | bool | `True` | `++generation.args.self_cond=False` | Self-conditioning during sampling |
| `generation.args.guidance_w` | float | `1.0` | `++generation.args.guidance_w=2.0` | Classifier-free guidance weight |
| `generation.args.ag_ratio` | float | `0.0` | `++generation.args.ag_ratio=0.1` | Autoguidance mixing ratio |
| `generation.args.ag_ckpt_path` | str\|null | `null` | `++generation.args.ag_ckpt_path=/path/to/ag.ckpt` | Autoguidance checkpoint |
| `generation.args.save_trajectory_every` | int | `0` | `++generation.args.save_trajectory_every=50` | Snapshot interval (0 = disabled) |
| `generation.args.fold_cond` | bool | `False` | `++generation.args.fold_cond=True` | Use fold conditioning |
| `generation.n_recycle` | int | `0` | `++generation.n_recycle=1` | Recycling iterations |

## Generation — search algorithm (`generation.search.*`)

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.search.algorithm` | enum | `best-of-n` (binder, ligand), `single-pass` (AME) | `++generation.search.algorithm=beam-search` | Strategy: `single-pass`, `best-of-n`, `beam-search`, `fk-steering`, `mcts` |
| `generation.search.max_batch_size` | int | inherits `dataloader.batch_size` | `++generation.search.max_batch_size=8` | Max samples per forward pass during search |
| `generation.search.reward_threshold` | float\|null | `null` | `++generation.search.reward_threshold=0.5` | Filter lookahead samples by reward |
| `generation.search.step_checkpoints` | list[int] | `[0, 100, 200, 300, 400]` | `++generation.search.step_checkpoints=[0,200,400]` | Diffusion-step checkpoints used by all algorithms |
| `generation.search.best_of_n.replicas` | int | `2` | `++generation.search.best_of_n.replicas=4` | best-of-n replica count |
| `generation.search.beam_search.beam_width` | int | `4` | `++generation.search.beam_search.beam_width=8` | Beam-search width |
| `generation.search.beam_search.n_branch` | int | `4` | `++generation.search.beam_search.n_branch=8` | Beam-search branch factor |
| `generation.search.beam_search.keep_lookahead_samples` | bool | `true` | `++generation.search.beam_search.keep_lookahead_samples=false` | Keep intermediate beam samples |
| `generation.search.beam_search.save_intermediate_states` | bool | `false` | `++generation.search.beam_search.save_intermediate_states=true` | Save PDBs at each checkpoint (expensive) |
| `generation.search.fk_steering.beam_width` | int | `4` | `++generation.search.fk_steering.beam_width=8` | FK-steering beam width |
| `generation.search.fk_steering.n_branch` | int | `4` | `++generation.search.fk_steering.n_branch=8` | FK-steering branch factor |
| `generation.search.fk_steering.temperature` | float | `0.1` | `++generation.search.fk_steering.temperature=0.5` | FK-steering softmax temperature |
| `generation.search.fk_steering.keep_lookahead_samples` | bool | `true` | `++generation.search.fk_steering.keep_lookahead_samples=false` | Keep lookahead samples |
| `generation.search.mcts.n_simulations` | int | `20` | `++generation.search.mcts.n_simulations=50` | MCTS simulations per node |
| `generation.search.mcts.exploration_prob` | float | `0.5` | `++generation.search.mcts.exploration_prob=0.7` | MCTS exploration probability |
| `generation.search.mcts.exploration_constant` | float | `1.0` | `++generation.search.mcts.exploration_constant=1.4` | MCTS exploration constant |
| `generation.search.mcts.keep_lookahead_samples` | bool | `true` | `++generation.search.mcts.keep_lookahead_samples=false` | Keep MCTS lookaheads |

## Generation — refinement (`generation.refinement.*`)

Refinement is disabled by default. Enable `sequence_hallucination` for AF2-loss
post-hoc optimization of the binder sequence.

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.refinement.algorithm` | enum\|null | `null` | `++generation.refinement.algorithm=sequence_hallucination` | Enable refinement |
| `generation.refinement.refine_targets` | enum | `final` | `++generation.refinement.refine_targets=all` | What to refine: `final` (samples) or `all` (final + lookaheads) |
| `generation.refinement.save_pre_refinement` | enum | `none` | `++generation.refinement.save_pre_refinement=final` | Also save pre-refinement copies |
| `generation.refinement.enable_soft_optimization` | bool | `false` | `++generation.refinement.enable_soft_optimization=true` | Stages 2 + 3 (softmax + one-hot) |
| `generation.refinement.enable_greedy_optimization` | bool | `true` | `++generation.refinement.enable_greedy_optimization=false` | Stage 4 (PSSM semigreedy) |
| `generation.refinement.n_temp_iters` | int | `45` | `++generation.refinement.n_temp_iters=60` | Temperature-anneal iterations |
| `generation.refinement.n_hard_iters` | int | `5` | `++generation.refinement.n_hard_iters=10` | Hard one-hot iterations |
| `generation.refinement.n_recycles` | int | `3` | `++generation.refinement.n_recycles=5` | AF2 recycling during refinement |
| `generation.refinement.n_greedy_iters` | int | `15` | `++generation.refinement.n_greedy_iters=30` | Greedy iterations |
| `generation.refinement.greedy_percentage` | int | `1` | `++generation.refinement.greedy_percentage=5` | Greedy fraction |
| `generation.refinement.loss_weights.{pae,plddt,i_pae,con,i_con,dgram_cce,rg,i_ptm,helix_binder}` | float | various (see `binder_generate.yaml`) | `++generation.refinement.loss_weights.rg=0.5` | AF2 loss term weights during refinement |

## Generation — post-generation filter (`generation.filter.*`)

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.filter.filter_samples_limit` | int\|null | `1000` (binder/ligand/AME) | `++generation.filter.filter_samples_limit=500` | Max samples after filtering (top-N by reward) |
| `generation.filter.delete_non_top_n_samples` | bool | `false` (binder), `true` (ligand, AME) | `++generation.filter.delete_non_top_n_samples=false` | Delete vs move filtered-out samples |
| `generation.filter.dedup_sequence` | bool | `true` | `++generation.filter.dedup_sequence=false` | Drop duplicate sequences before ranking |
| `generation.filter.reward_threshold` | float\|null | `null` | `++generation.filter.reward_threshold=0.3` | Drop samples below this reward before top-N |

## Generation — reward model (`generation.reward_model.*`)

Reward weights apply to the named sub-model inside the `CompositeRewardModel`.
The protein binder pipeline uses `af2folding`; ligand binder and AME (when
reward is enabled) use `rf3folding`. Other reward models (`tmol`,
`bioinformatics`, `hbplus`, `boltz2folding`, `hbplus_af2`, `hbplus_boltz2`,
`rf3folding`) are pre-wired but commented out — uncomment in the YAML or add
via override.

### `af2folding` reward weights (protein binder)

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.reward_model.reward_models.af2folding.reward_weights.i_pae` | float | `-1.0` | `++generation.reward_model.reward_models.af2folding.reward_weights.i_pae=-2.0` | Interface PAE weight (negative = minimize) |
| `...af2folding.reward_weights.plddt` | float | `0.0` | `++generation.reward_model.reward_models.af2folding.reward_weights.plddt=0.5` | pLDDT weight (positive = maximize) |
| `...af2folding.reward_weights.con` | float | `0.0` | `++generation.reward_model.reward_models.af2folding.reward_weights.con=1.0` | Intra-binder contact loss |
| `...af2folding.reward_weights.dgram_cce` | float | `0.0` | `++generation.reward_model.reward_models.af2folding.reward_weights.dgram_cce=0.5` | Distogram cross-entropy |
| `...af2folding.reward_weights.min_ipae` | float | `0.0` | `++generation.reward_model.reward_models.af2folding.reward_weights.min_ipae=-1.0` | Minimum interface PAE |
| `...af2folding.reward_weights.{min,max,avg}_ipsae[_10]` | float | `0.0` | `++...avg_ipsae=0.5` | Interface pSAE family |
| `...af2folding.num_recycles` | int | `3` | `++generation.reward_model.reward_models.af2folding.num_recycles=4` | AF2 recycling iterations |
| `...af2folding.use_initial_guess` | bool | `True` | `++generation.reward_model.reward_models.af2folding.use_initial_guess=False` | Warm-start AF2 from generated structure |
| `...af2folding.use_initial_atom_pos` | bool | `False` | `++generation.reward_model.reward_models.af2folding.use_initial_atom_pos=True` | Use initial atom positions |
| `...af2folding.protocol` | enum | `binder` | `++generation.reward_model.reward_models.af2folding.protocol=binder` | AF2 protocol |
| `...af2folding.use_multimer` | bool | `True` | `++generation.reward_model.reward_models.af2folding.use_multimer=False` | Use AF2-multimer |

### `rf3folding` reward weights (ligand binder, AME)

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `generation.reward_model.reward_models.rf3folding.reward_weights.min_ipAE` | float | `-1.0` | `++generation.reward_model.reward_models.rf3folding.reward_weights.min_ipAE=-2.0` | Minimum interface PAE weight |
| `...rf3folding.reward_weights.plddt` | float | `0.0` | `++...rf3folding.reward_weights.plddt=0.5` | pLDDT weight |
| `...rf3folding.reward_weights.ipAE` | float | `0.0` | `++...rf3folding.reward_weights.ipAE=-0.5` | Interface PAE weight |
| `...rf3folding.reward_weights.{mean_min_ipAE,mean_ipAE,min_mean_ipAE,pAE,ipTM,pTM,ranking_score}` | float | `0.0` | `++...rf3folding.reward_weights.ipTM=1.0` | RF3 confidence metrics |
| `...rf3folding.reward_weights.has_clash` | float | `0.0` | `++...rf3folding.reward_weights.has_clash=-5.0` | Clash penalty (1.0 if clash; negative = penalize) |
| `...rf3folding.reward_weights.{min,max,avg}_ipSAE` | float | `0.0` | `++...rf3folding.reward_weights.min_ipSAE=1.0` | Interface pSAE family |
| `...rf3folding.normalize_pae` | bool | `true` | `++...rf3folding.normalize_pae=false` | Divide PAE metrics by 31 to map to 0-1 |
| `...rf3folding.ckpt_path` | str | `${oc.env:RF3_CKPT_PATH}` | `++...rf3folding.ckpt_path=/data/rf3.pt` | RF3 checkpoint path |
| `...rf3folding.rf3_path` | str | `${oc.env:RF3_EXEC_PATH}` | `++...rf3folding.rf3_path=/opt/rf3` | RF3 executable directory |

## Evaluation (`metric.*`)

From `binder_evaluate.yaml`, `ligand_binder_evaluate.yaml`, `ame_evaluate.yaml`.

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `protein_type` | enum | `binder` (binder/ligand), `motif_binder` (AME) | `++protein_type=binder` | Selects which metric path runs |
| `input_mode` | enum | `generated` | `++input_mode=pdb_dir` | `generated` for design pipeline; `pdb_dir` for external PDBs |
| `metric.compute_binder_metrics` | bool | `true` (binder/ligand) | `++metric.compute_binder_metrics=true` | Run binder refolding |
| `metric.compute_motif_binder_metrics` | bool | (AME only) `true` | `++metric.compute_motif_binder_metrics=false` | Run joint motif + binder metrics |
| `metric.binder_folding_method` | enum | `colabdesign` (binder), `rf3_latest` (ligand, AME) | `++metric.binder_folding_method=esmfold` | Refold backend: `colabdesign`, `rf3_latest`, `boltz2_default`, `esmfold` |
| `metric.sequence_types` | list | `[self]` (binder default), `[self, mpnn]` (ligand), `[self, mpnn_fixed]` (AME) | `++metric.sequence_types=[self,mpnn,mpnn_fixed]` | Which inverse-folding outputs to evaluate |
| `metric.num_redesign_seqs` | int | `2` | `++metric.num_redesign_seqs=8` | Sequences generated per design by the inverse folder |
| `metric.inverse_folding_model` | enum | `soluble_mpnn` (binder), `ligand_mpnn` (ligand, AME) | `++metric.inverse_folding_model=protein_mpnn` | `protein_mpnn`, `ligand_mpnn`, `soluble_mpnn` |
| `metric.interface_cutoff` | float | (binder/ligand) `8.0` | `++metric.interface_cutoff=6.0` | Interface-residue distance cutoff in Angstroms |
| `metric.ranking_criteria` | dict\|null | `null` (default: minimize i_pAE for protein, min_ipAE for ligand) | `++metric.ranking_criteria.i_pAE.scale=1.0` | Custom composite-score ranking |
| `metric.motif_ranking_criteria` | dict\|null | `null` | `++metric.motif_ranking_criteria.motif_rmsd_pred.scale=1.0` | Custom motif-binder ranking (AME) |
| `metric.compute_esm_metrics` | bool | `true` (binder, ligand, AME) | `++metric.compute_esm_metrics=false` | Compute ESM pseudo-perplexity |
| `metric.compute_pre_refolding_metrics` | bool | `false` (binder, ligand), `true` (AME) | `++metric.compute_pre_refolding_metrics=true` | Pre-refolding bioinformatics/TMOL/HBPLUS |
| `metric.pre_refolding.bioinformatics` | bool | `true` | `++metric.pre_refolding.bioinformatics=false` | SC, SASA, hydrophobicity on generated |
| `metric.pre_refolding.tmol` | bool | `true` | `++metric.pre_refolding.tmol=false` | TMOL forcefield on generated |
| `metric.pre_refolding.hbplus` | bool | `true` | `++metric.pre_refolding.hbplus=false` | HBPLUS H-bond on generated |
| `metric.compute_refolded_structure_metrics` | bool | `false` (binder, ligand), `true` (AME) | `++metric.compute_refolded_structure_metrics=true` | Same set on refolded |
| `metric.refolded.{bioinformatics,tmol,hbplus}` | bool | `true` | `++metric.refolded.tmol=false` | Same toggles, refolded structure |
| `metric.compute_monomer_metrics` | bool | `true` (binder, ligand), `false` (AME) | `++metric.compute_monomer_metrics=true` | Run monomer designability / codesignability |
| `metric.monomer_folding_models` | list | `[esmfold]` | `++metric.monomer_folding_models=[esmfold,colabfold]` | Folding models for monomer metrics |
| `metric.compute_designability` | bool | `true` | `++metric.compute_designability=false` | Designability (ProteinMPNN -> fold) |
| `metric.designability_modes` | list | `[ca]` | `++metric.designability_modes=[ca,all_atom]` | RMSD modes for designability |
| `metric.compute_codesignability` | bool | `true` | `++metric.compute_codesignability=false` | Codesignability (fold original sequence) |
| `metric.codesignability_modes` | list | `[ca, all_atom]` | `++metric.codesignability_modes=[ca]` | RMSD modes for codesignability |
| `metric.compute_co_sequence_recovery` | bool | `false` | `++metric.compute_co_sequence_recovery=true` | Compare MPNN vs original sequence |
| `metric.compute_ss` | bool | `true` (binder) | `++metric.compute_ss=false` | Secondary-structure fractions via biotite |
| `metric.compute_novelty_pdb` | bool | `false` | `++metric.compute_novelty_pdb=true` | Novelty vs PDB |
| `metric.compute_novelty_afdb` | bool | `false` | `++metric.compute_novelty_afdb=true` | Novelty vs AlphaFold DB |
| `metric.compute_novelty_afdb_rep_v4` | bool | `false` | `++metric.compute_novelty_afdb_rep_v4=true` | Novelty vs AFDB rep v4 |
| `metric.keep_folding_outputs` | bool | `true` (binder, AME), `false` (ligand) | `++metric.keep_folding_outputs=false` | Keep refolded PDBs on disk |

## Analysis (`aggregation.*`)

From `binder_analyze.yaml`, `ligand_binder_analyze.yaml`, `ame_analyze.yaml`.

| Key | Type | Default | Example override | What it controls |
|-----|------|---------|------------------|------------------|
| `result_type` | enum | per pipeline | `++result_type=protein_binder` | One of: `protein_binder`, `ligand_binder`, `monomer`, `motif_protein_binder`, `motif_ligand_binder` |
| `aggregation.limit` | int\|null | `null` | `++aggregation.limit=200` | Limit number of result files merged (null = all) |
| `aggregation.analysis_modes` | list | `[binder, monomer]` (binder, ligand), `[motif_binder, monomer]` (AME) | `++aggregation.analysis_modes=[binder]` | Which analysis functions to run |
| `aggregation.success_thresholds.i_pAE.threshold` | float | `7.0` (protein_binder) | `++aggregation.success_thresholds.i_pAE.threshold=10.0` | Interface PAE threshold (after `* scale`) |
| `aggregation.success_thresholds.i_pAE.op` | str | `<=` | `++aggregation.success_thresholds.i_pAE.op=<` | Comparison operator |
| `aggregation.success_thresholds.i_pAE.scale` | float | `31.0` | `++aggregation.success_thresholds.i_pAE.scale=1.0` | Scale factor applied before comparison |
| `aggregation.success_thresholds.i_pAE.column_prefix` | str | `complex` | `++aggregation.success_thresholds.i_pAE.column_prefix=complex` | Column-name prefix |
| `aggregation.success_thresholds.pLDDT.threshold` | float | `0.9` (protein_binder), `0.8` (AME) | `++aggregation.success_thresholds.pLDDT.threshold=0.85` | pLDDT threshold |
| `aggregation.success_thresholds.pLDDT.op` | str | `>=` | `++aggregation.success_thresholds.pLDDT.op=>=` | Comparison operator |
| `aggregation.success_thresholds.scRMSD.threshold` | float | `1.5` (protein_binder), `2.0` (ligand_binder, AME) | `++aggregation.success_thresholds.scRMSD.threshold=2.0` | scRMSD threshold |
| `aggregation.success_thresholds.scRMSD.op` | str | `<` | `++aggregation.success_thresholds.scRMSD.op=<=` | Comparison operator |
| `aggregation.success_thresholds.scRMSD.column_prefix` | str | `binder` | `++aggregation.success_thresholds.scRMSD.column_prefix=binder` | Column-name prefix |
| `aggregation.motif_binder_success_thresholds.motif_rmsd_pred.threshold` | float | `1.5` (motif_ligand_binder), `2.0` (motif_protein_binder) | `++aggregation.motif_binder_success_thresholds.motif_rmsd_pred.threshold=1.0` | Motif RMSD in refolded structure |
| `aggregation.motif_binder_success_thresholds.motif_seq_recovery.threshold` | float | `0.5` (AME default), `1.0` (motif protein binder default) | `++aggregation.motif_binder_success_thresholds.motif_seq_recovery.threshold=0.8` | Motif sequence recovery threshold |
| `aggregation.designability_thresholds.ca.esmfold.threshold` | float | `2.0` | `++aggregation.designability_thresholds.ca.esmfold.threshold=1.5` | Designability CA-scRMSD threshold |
| `aggregation.ca_codesignability_thresholds.ca.esmfold.threshold` | float | `2.0` | `++aggregation.ca_codesignability_thresholds.ca.esmfold.threshold=1.5` | CA codesignability threshold |
| `aggregation.allatom_codesignability_thresholds.all_atom.esmfold.threshold` | float | `2.0` | `++aggregation.allatom_codesignability_thresholds.all_atom.esmfold.threshold=2.5` | All-atom codesignability threshold |
| `aggregation.require_all_thresholds` | bool | `false` | `++aggregation.require_all_thresholds=true` | AND vs OR across thresholds |
| `aggregation.compute_diversity` | bool | `true` (AME), unset elsewhere | `++aggregation.compute_diversity=false` | FoldSeek diversity |
| `aggregation.compute_mmseqs_diversity` | bool | `true` (AME) | `++aggregation.compute_mmseqs_diversity=true` | MMseqs2 sequence diversity |

## Common override patterns

Cheat-sheet of full overrides users run frequently.

```bash
# Production beam-search on PDL1
++generation.task_name=02_PDL1 \
++generation.search.algorithm=beam-search \
++generation.search.beam_search.beam_width=8 \
++generation.search.beam_search.n_branch=4 \
++run_name=pdl1_beam_v1

# Fast smoke test (single-pass, fewer steps, smaller batch)
++generation.search.algorithm=single-pass \
++generation.args.nsteps=100 \
++generation.dataloader.dataset.nres.nsamples=2 \
++run_name=quick_test

# Cheap iteration with ESMFold eval
++metric.binder_folding_method=esmfold \
++metric.compute_pre_refolding_metrics=false \
++metric.compute_refolded_structure_metrics=false

# Stricter success thresholds for top-N filtering
++aggregation.success_thresholds.i_pAE.threshold=5.0 \
++aggregation.success_thresholds.scRMSD.threshold=1.0

# Lower VRAM (40GB GPU)
++generation.dataloader.batch_size=8 \
++eval_njobs=1 \
++metric.num_redesign_seqs=2
```
