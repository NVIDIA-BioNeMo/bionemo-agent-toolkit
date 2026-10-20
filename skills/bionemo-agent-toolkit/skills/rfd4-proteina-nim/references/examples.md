# Examples and a diagnostic probe

All paths below are relative to the skill directory. Each bundled JSON carries
its complete mmCIF; no upstream repository, GPU, or Python package is needed
to prepare or submit a staging request. The files are unchanged copies, with
source revision and SHA-256 hashes in `assets/source-manifest.json`.

| Request in `assets/requests/` | Task / purpose |
| --- | --- |
| `01_annotated_cif_enzyme.json` | Nam's first smoke example; annotated catalytic motif, `enzyme_design` |
| `02_condition_spec_monomer.json` | Parsed spec dialect, attached annotated monomer template, `generation` |
| `03_replicates_seeded.json` | Four generation replicates with a base seed |
| `04_motif_scaffolding_indexed.json` | Two indexed motif scaffolds |
| `05_small_molecule_binder.json` | Two designs around SAM |
| `06_search_interchain.json` | SAM hydrogen-bond beam search without a refolding oracle |
| `09_partial_diffusion.json` | Two refinements of a complete 2KL8 structure |
| `10_inverse_folding.json` | Two sequence designs on the same complete backbone |
| `11_antibody_design.json` | Trastuzumab H3 redesign against HER2, condition-spec dialect |
| `14_nanobody_cdr_design.json` | Three VHH CDRs redesigned against PD-L1 |
| `16_ppi_binder.json` | De novo binder against PD-1, `generation` with target/hotspot conditions |
| `25_secondary_structure_conditioning.json` | Diagnostic probe only: source-valid, but HTTP 422 on tested staging |

The other eleven bundled requests completed on staging during authoring.
Example 06 returned a warning: a non-CCD `L;G` component caused three TMol
interface metrics to be omitted; its search still completed. Preserve and
report that warning, and repair chemistry using real CCD names if those
metrics are needed. Do not silently rename the component to make it pass.

Example 25's gateway response hid the field-level cause. Retain it as evidence
for deployment/input debugging, not as a validated secondary-structure recipe.

An example is a starting point for the specific structure it contains, not a
replacement for the user's target. Preserve the full input and alter only the
fields necessary to express the user's request. For a different protein or
epitope, author corresponding conditions against that structure.

## Nam's original commands

In a checkout of `ntdo/oss-pipeline` containing `sample_requests/`:

```bash
cd /path/to/rfd4-proteina-nim/sample_requests
./run_staging_nvcf.sh 01_annotated_cif_enzyme.json
./run_staging_nvcf.sh 01_annotated_cif_enzyme.json --output response.json
```

The first command prints the body followed by an `HTTP_STATUS:...` trailer,
so its complete stdout is not one JSON document. Use `--output` for a body-only
file. The upstream curl command lacks `--fail`; a zero shell exit by itself
does not prove HTTP success. The skill client checks HTTP status explicitly.

## Change count and seed without damaging the mmCIF

```bash
python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('assets/requests/16_ppi_binder.json').read_text())
p['sampling'].update(num_replicates=3, batch_size=1, seed=42)
Path('ppi-request.json').write_text(json.dumps(p, indent=2) + '\n')
PY
python scripts/design.py --mode staging --request ppi-request.json \
  --output-dir /tmp/rfd4-ppi-prepared --dry-run
```

This prepares a request only. `batch_size=1` permits replaying individual plain
sampling replicates and reduces peak memory, at the cost of batching speed.
To execute an authorized run, remove `--dry-run` and use a new output directory.

For three independent searches, start from example 06 and set the same three
sampling fields. Keep `thinking_medium` and checkpoints `[0,30,60]`; do not
equate three replicates with three returned beam designs.

## Export a response saved by Nam's script

```bash
python scripts/design.py \
  --request assets/requests/01_annotated_cif_enzyme.json \
  --response-json /path/to/response.json \
  --output-dir /tmp/rfd4-enzyme-extracted
```

This performs no network request and records `source=saved_response`. Supply
the exact request that produced the response; the helper can check basic
consistency but cannot independently authenticate that relationship.

## More specialized upstream examples

`sample_requests/07` and `08` demonstrate oracle search/refolding and require
an enabled oracle; they are not stock-staging success examples. The upstream
folder also contains peptide–MHC and TCR cases, RASA/H-bond/centroid conditions,
reward overrides, retained search intermediates, and metric aggregation.
Read their inputs and requirements at the source revision before using them.
They are intentionally not all loaded into the skill entrypoint.
