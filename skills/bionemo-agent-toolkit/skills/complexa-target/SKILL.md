---
name: complexa-target
description: Use this skill whenever the user wants to add, register, edit, list, show, or validate a Proteina-Complexa design target for any pipeline — protein binder (default), ligand binder, or AME / enzyme scaffolding. Triggers include "add a target", "define a new target for binder design", "register a hotspot", "set up a PDL1 binder target", "ligand binder pocket", "SMILES target", "AME task", "enzyme motif", "M0024_1nzy", "complexa target add", "complexa target show", "configure target X", "what targets are available", "where do hotspots live", "what does target_input mean", "chain-spec syntax", "binder length range", or any question about `configs/targets/{,ligand_}targets_dict.yaml` and `configs/design_tasks/ame_dict_v2.yaml`. Also covers `complexa validate target`. This is the only skill that touches the three targets dict files.
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# complexa-target

Add or edit a design target in Proteina-Complexa. Targets live in **three YAML files**, one per `complexa design` pipeline:

- `configs/targets/targets_dict.yaml` — protein binder (**default pipeline**)
- `configs/targets/ligand_targets_dict.yaml` — ligand binder
- `configs/design_tasks/ame_dict_v2.yaml` — AME / enzyme scaffolding

The `complexa target` CLI only manages the first two. AME tasks use an extended schema (the same core fields as ligand targets plus `contig_atoms` for hand-curated per-residue motif atom selections) and are file-edit-only.

## Preferred path: edit the YAML directly

`complexa target add` is a thin wrapper around "load YAML → build dict → append a block" (see `src/proteinfoundation/cli/target_manager.py:add_target_cli` and `append_target_to_dict`). For agentic use, **just edit the targets dict directly** — the schema is short, the existing entries are great copy templates, and you skip 14 CLI flags / SMILES shell-escaping. Use the CLI only if you explicitly want its YAML auto-quoter or its overwrite-prompt safety.

The skill therefore presents both paths:

| Step | Direct file edit (preferred) | CLI |
|---|---|---|
| Look at existing targets | Read `configs/targets/{,ligand_}targets_dict.yaml` (or `configs/design_tasks/ame_dict_v2.yaml` for AME) | `complexa target list` (protein/ligand only) |
| Look at one target | Read the dict and grep for the key | `complexa target show NAME` |
| Add a new target | Append a YAML block (Step 3a) | `complexa target add ...` (Step 3b) |
| Verify the PDB resolves on disk | — *(no shortcut, this checks Hydra defaults)* | `complexa validate target CONFIG --target NAME` |

`complexa target` only sees the two protein-style dicts (`targets_dict.yaml` and `ligand_targets_dict.yaml`). For AME tasks (which use a different schema), file-edit is the only path — see Step 1 below.

## What this skill enables

- Register a **protein target** (chain + residue range + hotspots) in `configs/targets/targets_dict.yaml`.
- Register a **ligand target** (PDB pocket + 3-letter code + SMILES) in `configs/targets/ligand_targets_dict.yaml`.
- Resolve the right **AME task name** (e.g. `M0024_1nzy`, `M0096_1chm`) for the AME pipeline — these are not added via `complexa target add` (see Step 1).
- Verify a target resolves to a real PDB on disk with `complexa validate target`.
- Emit a replayable artifact (`target_definition.yaml`) for downstream design runs.

## Step 1: Decide the target type

Targets live in **three different files**, one per `complexa design` pipeline. Pick the file by working out which pipeline the user will run, then add the entry to that file. Each file is consumed by exactly one pipeline.

| User intent | Pipeline | Targets dict file | This skill? |
|---|---|---|---|
| Bind a protein surface (PD-L1, IFNAR2, TNF-α, …) — **default** | `configs/search_binder_local_pipeline.yaml` | `configs/targets/targets_dict.yaml` | Yes — Step 2 (protein) |
| Bind a small-molecule pocket (FAD, SAM, OQO, …) | `configs/search_ligand_binder_local_pipeline.yaml` | `configs/targets/ligand_targets_dict.yaml` | Yes — Step 2 (ligand) |
| AME / enzyme scaffolding (motif + ligand, `M####_<pdb>` names) | `configs/search_ame_local_pipeline.yaml` | `configs/design_tasks/ame_dict_v2.yaml` | Partial — see "AME tasks" below |

### AME tasks (enzyme pipeline)

Similar story — AME tasks live in `configs/design_tasks/ame_dict_v2.yaml` under `motif_target_dict_cfg:` with their own schema (`source`, `target_filename`, `ligand`, `contig_atoms`, `binder_length`, `use_bonds_from_file`). The `contig_atoms` string encodes per-residue motif atom selections like `"A64: [O, C]; A86: [CB, CA, N, C]; ..."` — these are hand-curated, so adding a new AME task is a file edit, not a CLI invocation. Browse the file, copy a similar entry as a template, and pass `++generation.task_name=<NAME>` to `complexa design configs/search_ame_local_pipeline.yaml`.

## Step 2: Gather required info

Use AskUserQuestion to collect — do not guess these. Required fields differ for protein vs ligand.

### Protein target

| Field | Question | Example | Required |
|---|---|---|---|
| name | "Target name (used as the dict key and `task_name`)?" | `02_PDL1`, `MyTarget_v1` | yes |
| source | "Source directory under `$DATA_PATH/target_data/`?" | `bindcraft_targets`, `custom_targets` | yes (or `target_path`) |
| target_filename | "PDB filename (no `.pdb` extension)?" | `PD-L1`, `IFNAR2` | yes (or `target_path`) |
| target_input | "Chain + residue range — see reference for grammar." | `A1-115`, `A1-50,B1-50` | yes |
| hotspot_residues | "Hotspot residues (interface contact residues)?" | `["A33", "A95", "A102"]` | optional, recommended |
| binder_length | "Binder length range `[min, max]` or single `[length]`?" | `[80, 150]`, `[100]` | optional (default `[60, 120]`) |
| pdb_id | "Reference PDB ID (optional, metadata only)?" | `"2lag"` | optional |

### Ligand target — protein fields above (minus `target_input`), plus:

| Field | Question | Example | Required |
|---|---|---|---|
| ligand | "3-letter PDB ligand residue code?" | `FAD`, `OQO`, `SAM` | yes (presence marks target as ligand) |
| smiles | "SMILES string for the ligand?" | `"O=C2C3=Nc1cc(c(...)..."` | recommended |
| ligand_only | "Generate pocket around ligand only (no protein-protein interface)?" | `true` / `false` | optional (default `true`) |
| use_bonds_from_file | "Use bond info from the input PDB/CIF?" | `true` / `false` | optional (default `true`) |
| target_input | not required for ligand targets | — | no |

Check for name collisions by reading the dict (`rg '^  NEW_NAME:' configs/targets/targets_dict.yaml`) or running `complexa target list -v --ligand` / `--protein`.

## Step 3a: Append the YAML block directly (preferred)

Open `configs/targets/targets_dict.yaml` (or `ligand_targets_dict.yaml` for ligand targets), find a similar existing entry as a style template, and append the new block under `target_dict_cfg:`. Two-space indent, single blank line between entries.

### Protein template

```yaml
  02_PDL1:
    source: bindcraft_targets
    target_filename: PD-L1
    target_input: "A1-115"
    hotspot_residues: ["A37", "A39", "A49", "A98"]
    binder_length: [64, 155]
    pdb_id: "4z18"
```

Rules to match the existing file style (mirrors what `complexa target add` would emit):

- Quote chain/residue ranges (`"A1-115"`, `"A33"`) and any SMILES — flow-style strings get tripped up by `:` and brackets otherwise.
- Use flow-style lists (`["A33", "A95"]`, `[64, 155]`) — that's what the on-disk dump produces.
- `target_input`, `source`, `target_filename` are required for protein. `target_path` (absolute path) can replace `source + target_filename` if the PDB lives outside `$DATA_PATH/target_data/`.

### Ligand template

```yaml
  41_7BKC_LIGAND:
    source: ligand_targets
    target_filename: 7BKC_ligand_centered
    hotspot_residues: [null]
    binder_length: [100]
    pdb_id: 7BKC
    ligand: 'FAD'
    ligand_only: True
    SMILES: "O=C2C3=Nc1cc(c(cc1N(C3=NC(=O)N2)CC(O)C(O)C(O)COP(=O)(O)OP(=O)(O)OCC6OC(n5cnc4c(ncnc45)N)C(O)C6O)C)C"
    use_bonds_from_file: True
```

The presence of the `ligand:` key flips the target into ligand mode — there is no separate `is_ligand` flag. `target_input` is not required for ligands.

After saving, skip to Step 4 to verify.

## Step 3b: CLI alternative (`complexa target add`)

Use the CLI when you want its automatic chain/residue quoting, the overwrite-confirm prompt, or to wire target creation into a non-Python script. Prefer non-interactive mode for agentic use (`-i / --editor` opens an editor and blocks).

### Confirmed flags (from `src/proteinfoundation/cli/target_cli.py`)

| Flag | Type | Applies to | Notes |
|---|---|---|---|
| `name` (positional) | str | both | dict key |
| `--dict PATH` | path | both | override target dict path |
| `-i, --interactive` | flag | both | open `$EDITOR` |
| `-e, --editor NAME` | str | both | `code`, `nano`, `vim`, `cursor`, ... |
| `--source NAME` | str | both | directory under `$DATA_PATH/target_data/` |
| `--target-filename NAME` | str | both | PDB stem (no `.pdb`) |
| `--target-path PATH` | str | both | full path; overrides `source`+`filename` |
| `--target-input SPEC` | str | protein | chain/residue range, e.g. `A1-115` |
| `--hotspot-residues R [R ...]` | list | both | e.g. `A33 A95` |
| `--binder-length N [N ...]` | int list | both | `[min, max]` or `[length]` |
| `--pdb-id ID` | str | both | metadata only |
| `--ligand CODE` | str | ligand | presence marks ligand target |
| `--ligand-only` | flag | ligand | pocket-only mode |
| `--smiles STR` | str | ligand | SMILES for the ligand |
| `--use-bonds-from-file` | flag | ligand | use PDB bonds |
| `-f, --force` | flag | both | overwrite existing without prompt |

### Protein example

```bash
complexa target add 02_PDL1 \
  --source bindcraft_targets \
  --target-filename PD-L1 \
  --target-input A1-115 \
  --hotspot-residues A37 A39 A49 A98 \
  --binder-length 64 155 \
  --pdb-id 4z18
```

### Ligand example

```bash
complexa target add 41_7BKC_LIGAND \
  --source ligand_targets \
  --target-filename 7BKC_ligand_centered \
  --pdb-id 7BKC \
  --ligand FAD \
  --ligand-only \
  --use-bonds-from-file \
  --smiles "O=C2C3=Nc1cc(c(cc1N(C3=NC(=O)N2)CC(O)C(O)C(O)COP(=O)(O)OP(=O)(O)OCC6OC(n5cnc4c(ncnc45)N)C(O)C6O)C)C" \
  --binder-length 100
```

Why these defaults: `--source` defaults to `custom_targets` (protein) or `ligand_targets` (ligand) and `--target-filename` defaults to `name`, so be explicit when the PDB stem differs from the target name. The dict gets `ligand_only: true` and `use_bonds_from_file: true` by default for ligand targets — pass the flags to be explicit, or omit to accept defaults.

## Step 4: Verify

Run two checks, in order. Stop and fix on the first failure.

```bash
# 1. Confirm the entry landed and looks right.
#    Direct read works just as well: `rg -A 7 '^  02_PDL1:' configs/targets/targets_dict.yaml`
complexa target show 02_PDL1

# 2. Resolve the PDB path and validate it exists on disk.
#    No shortcut for this — it traverses Hydra defaults to find the target dict.
complexa validate target configs/search_protein_local_pipeline.yaml --target 02_PDL1
```

`complexa validate target` (from `src/proteinfoundation/cli/validate.py::validate_target`) checks:

- `DATA_PATH` is set and `target_data/` exists.
- The target name resolves in `target_dict_cfg`.
- Either `target_path` exists, or `$DATA_PATH/target_data/<source>/<target_filename>.pdb` exists.
- `target_input`, `hotspot_residues`, `binder_length` are reported back so a human can sanity-check them.

For ligand targets, point `--target` at a ligand pipeline config (e.g. a ligand binder search config).

## Step 5: Emit artifact

Save a replayable record under `./target_<name>/`:

```bash
mkdir -p target_02_PDL1
complexa target show 02_PDL1 > target_02_PDL1/target_show.txt
```

Then write the appended YAML snippet (the lines `complexa target add` wrote under `target_dict_cfg:`) to `target_02_PDL1/target_definition.yaml` using the Write tool. The artifact lets the user diff target definitions across runs and re-create the entry on another checkout via `complexa target add ... --force`.

## Hardware requirements

None for target definition — this is a YAML edit, not a training/inference step. Disk impact is a few KB appended to the targets dict (plus an automatic `.yaml.bak` backup written by `save_targets_dict`).

For the downstream design / evaluate runs that consume the target, defer to `complexa-design` and `_shared/reference/hardware.md`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Target PDB file: File not found` from `validate target` | `<source>/<target_filename>.pdb` does not exist under `$DATA_PATH/target_data/` | Confirm the PDB stem and source dir. Use `--target-path /full/path.pdb` if the file lives outside `target_data/`. |
| "Target 'X' already exists! Overwrite? (y/N)" | Name collision in dict | Either pick a new name, or pass `-f / --force` to overwrite. |
| Hotspot residue not in PDB | Wrong chain or residue number | Open the PDB, re-check chain letters (case-sensitive) and residue indices. Hotspots use the format `<CHAIN><RESNUM>` — see reference. |
| Chain not found | `target_input` references a chain that does not exist in the PDB | Inspect the PDB with `grep "^ATOM" target.pdb \| awk '{print $5}' \| sort -u`. |
| Ligand code missing from PDB | The 3-letter `ligand` code does not appear as a `HETATM` residue name in the file | Open the PDB and check `HETATM` lines; you may need a `_ligand_centered` variant of the PDB. |
| SMILES parse failure downstream | Bad SMILES string | Validate with `rdkit.Chem.MolFromSmiles(smiles)` before adding. Quote SMILES in shell to escape brackets and parens. |
| Target name with leading digit breaks Hydra interpolation | YAML treats `02_PDL1` as a string fine; some override syntaxes need quoting | Use `++generation.task_name=02_PDL1`; quote if the shell strips characters. |
| `target_input` appears ignored for a ligand target | By design — ligand targets do not use `target_input`; pocket is defined by the ligand | Leave it unset for ligand targets. |

## Reference

- `reference/target_schema.md` — every field, chain-spec grammar, AME task-name grammar, three worked examples.
- `configs/targets/targets_dict.yaml` — live protein entries (copy a known-good one as a template).
- `configs/targets/ligand_targets_dict.yaml` — live ligand entries.
- `configs/design_tasks/ame_dict_v2.yaml` — AME task definitions (file-edit only, not exposed via `complexa target` CLI).
- `src/proteinfoundation/cli/target_cli.py` — argparse source of truth.
- `src/proteinfoundation/cli/target_manager.py` — `add_target_cli`, `list_targets`, `show_target`, schema in `TARGET_FIELDS`.
- `src/proteinfoundation/cli/validate.py` — `validate_target` implementation.
