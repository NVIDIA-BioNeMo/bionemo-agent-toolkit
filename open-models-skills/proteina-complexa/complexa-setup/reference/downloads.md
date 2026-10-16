# `complexa download` Reference

Full flag matrix, destination layout, and NGC source for every checkpoint
Complexa can pull.

`complexa download` is a thin Python wrapper around `env/download_startup.sh`
— the CLI argparse (in `src/proteinfoundation/cli/cli_runner.py:download_main`)
forwards `sys.argv[2:]` straight to the bash script, so any flag the bash
script accepts is reachable.

---

## Flag matrix

The Python argparse explicitly defines these flags:

| Flag | What it downloads | Destination | Approx size | Source |
|------|-------------------|-------------|-------------|--------|
| `--complexa` | `complexa.ckpt` + `complexa_ae.ckpt` (protein binder) | `./ckpts/` | ~3 GB | NGC `proteina_complexa` |
| `--complexa-ligand` | `complexa_ligand.ckpt` + `complexa_ligand_ae.ckpt` (ligand binder) | `./ckpts/` | ~3 GB | NGC `proteina_complexa_ligand` |
| `--complexa-ame` | `complexa_ame.ckpt` + `complexa_ame_ae.ckpt` (motif scaffolding) | `./ckpts/` | ~3 GB | NGC `proteina_complexa_ame` |
| `--complexa-all` | All three Complexa pairs | `./ckpts/` | ~9 GB | NGC (3 models) |
| `--all` | ProteinMPNN + LigandMPNN + AF2 + ESM2 + ESMFold + RF3 | `./community_models/...` | ~50 GB | Mixed (GitHub + AWS + HF + NGC) |
| `--everything` | All Complexa + community + Boltz2 | both | ~100+ GB | Mixed |
| `--status` | Show install state; downloads nothing | (none) | n/a | n/a |

The underlying bash script also accepts per-model flags (`--pmpnn`,
`--ligmpnn`, `--af2`, `--esm2`, `--esmfold`, `--rf3`, `--boltz2`) that pass
through unchanged. They are listed in `env/download_startup.sh:show_help` but
not in the Python argparse — they still work because of the `sys.argv[2:]`
passthrough.

| Passthrough flag | Destination | Approx size |
|------------------|-------------|-------------|
| `--pmpnn` | `./community_models/ProteinMPNN/{ca,vanilla}_model_weights/` | ~50 MB |
| `--ligmpnn` | `./community_models/LigandMPNN/model_params/` | ~500 MB |
| `--af2` | `./community_models/ckpts/AF2/params/` | ~3 GB |
| `--esm2` | `./community_models/ckpts/ESM2/` | ~2.5 GB |
| `--esmfold` | `./community_models/ckpts/ESMFold/` | ~8.5 GB |
| `--rf3` | `./community_models/ckpts/RF3/` | ~10 GB |
| `--boltz2` | `./community_models/ckpts/Boltz2/` | ~5 GB |

---

## Default destinations

All downloads land relative to the *current working directory* (the script
`cd`s to project root, derived from `PROJECT_ROOT` inside `download_startup.sh`).

```
$PROJECT_ROOT/
├── ckpts/                                   ← all 6 Complexa ckpts here, flat
│   ├── complexa.ckpt                        ← protein binder model
│   ├── complexa_ae.ckpt                     ← protein binder autoencoder
│   ├── complexa_ligand.ckpt                 ← ligand binder model
│   ├── complexa_ligand_ae.ckpt              ← ligand binder autoencoder
│   ├── complexa_ame.ckpt                    ← AME motif scaffolding model
│   └── complexa_ame_ae.ckpt                 ← AME autoencoder
└── community_models/
    ├── ProteinMPNN/
    │   ├── ca_model_weights/                ← Cα-only weights
    │   └── vanilla_model_weights/           ← full-backbone weights
    ├── LigandMPNN/model_params/             ← LigandMPNN weights
    └── ckpts/
        ├── AF2/params/                      ← AlphaFold2 .npz / .pkl params
        ├── ESM2/                            ← ESM2-650M weights
        ├── ESMFold/                         ← ESMFold model
        ├── RF3/                             ← RoseTTAFold3 ckpt
        └── Boltz2/                          ← Boltz2 (optional)
```

Note: `LOCAL_CHECKPOINT_PATH` in `.env` defaults to `${LOCAL_CODE_PATH}/ckpts`,
which matches where `complexa download` writes Complexa ckpts. If you edit
`LOCAL_CHECKPOINT_PATH` to point elsewhere, you must also move (or symlink)
the existing `./ckpts/` contents — `complexa download` always writes to
`$PROJECT_ROOT/ckpts/` regardless of the `.env` setting.

---

## The three Complexa model variants

| Variant | Pipeline config | Required ckpt pair | Use case |
|---------|----------------|---------------------|----------|
| Protein binder | `configs/search_binder_local_pipeline.yaml` | `complexa.ckpt` + `complexa_ae.ckpt` | De novo binders for protein targets (PDL1, EGFR, etc.) |
| Ligand binder | `configs/search_ligand_binder_local_pipeline.yaml` | `complexa_ligand.ckpt` + `complexa_ligand_ae.ckpt` | Binders to small-molecule pockets (FAD, OQO, etc.) |
| AME | `configs/search_ame_local_pipeline.yaml` | `complexa_ame.ckpt` + `complexa_ame_ae.ckpt` | Scaffolding catalytic / functional motifs with ligand context |

Each pipeline YAML has three checkpoint fields at the top level that you
**must** point at your local ckpts. After `complexa download --complexa-all`
they will be at `./ckpts/complexa{,_ae,_ligand,_ligand_ae,_ame,_ame_ae}.ckpt`:

```yaml
ckpt_path: ./ckpts
ckpt_name: complexa.ckpt
autoencoder_ckpt_path: ./ckpts/complexa_ae.ckpt
```

Or override on the CLI without editing the YAML:

```bash
complexa design configs/search_binder_local_pipeline.yaml \
    ++ckpt_path=./ckpts \
    ++ckpt_name=complexa.ckpt \
    ++autoencoder_ckpt_path=./ckpts/complexa_ae.ckpt
```

> Note: `complexa download` always uses a *flat* `./ckpts/` layout. If you
> downloaded ckpts manually into per-variant subdirectories
> (`ckpts/complexa_protein/`, etc.), update the pipeline YAML `ckpt_path` to
> match — or move/symlink into the flat layout.

---

## `complexa download --status` output

Example output (post `--complexa-all` + `--af2`, no RF3 or ESMFold):

```
═══════════════════════════════════════════
  Installation Status
═══════════════════════════════════════════
    Complexa (Protein): ✓ Installed (./ckpts/)
    Complexa (Ligand):  ✓ Installed (./ckpts/)
    Complexa (AME):     ✓ Installed (./ckpts/)
    ProteinMPNN:     ○ Missing (community_models/ProteinMPNN/)
    LigandMPNN:      ○ Missing (community_models/LigandMPNN/model_params/)
    AF2:             ✓ Installed (community_models/ckpts/AF2/)
    ESM2:            ○ Not installed (community_models/ckpts/ESM2/)
    ESMFold:         ○ Not installed (community_models/ckpts/ESMFold/)
    RF3:             ○ Missing (community_models/ckpts/RF3/)
    Boltz2:          ○ Missing (community_models/ckpts/Boltz2/)
═══════════════════════════════════════════
```

Read each row as: `<Model name>: <✓ Installed | ○ Missing> (<destination>)`.
Re-run `complexa download --<flag>` for any row that is missing.

---

## Tips

- Run `complexa download --status` **before** any download — it shows what is already on disk and saves re-downloading.
- Re-running `complexa download --<flag>` is idempotent: existing non-empty ckpts are skipped (`download_complexa_weights` checks `[ -f "$fm_ckpt" ] && [ -s "$fm_ckpt" ]`).
- Failed downloads leave a zero-byte file then `rm -f` it — safe to retry without manual cleanup.
- For ESM2 / ESMFold specifically: set `HF_TOKEN` in `.env` before downloading to avoid HF Hub rate limits.
- `complexa download --everything` will fetch every model the script supports (~100 GB). Prefer the targeted flags unless you actually need all variants.
