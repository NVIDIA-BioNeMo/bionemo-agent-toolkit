# Offline bookkeeping and saved responses

Use these helpers for explicitly synthetic software exercises. They never read
credentials or submit inference. Outputs establish software behavior only, with
no biological validity, scientific calibration or endpoint coverage. Real
campaign response parsing must first establish the provider's actual schema and
confidence encoding.

## Score fixtures

From the skill directory:

```bash
python3 scripts/offline_bookkeeping.py /workspace/input/bookkeeping.json --output-dir /workspace/runs/bookkeeping
```

The input has `target`, optional `provenance`, and `profiles`. Each profile has
`name`, `rank_by`, `filters`, and `candidates` with `id`, `scores`, and control
flags. Names must be unique; a profile name is a single directory component.
One profile writes directly to `--output-dir`; multiple profiles create named
subdirectories. The destination must be empty. Existing scores, explicit nulls,
invalid strings and absent keys are preserved. Unknown filters are rejected.

Each run contains `manifest.json`, `all_candidates.csv`, `candidates.csv`, and
`summary.json`. The manifest is saved and reloaded before filtering. The audit
retains controls and incomplete candidates. The ranked file contains only
passing non-controls and retains a header when no design passes. Summary counts
exclude controls from the design denominator and disclose missing-score IDs and
a provisional-fraction flag. A finite below-threshold score is complete.

Check the exit status and inspect saved files before reporting their counts and
ranked IDs. A script on disk or an intended path is not an executed result.

## Recovering cached metrics

```bash
python3 scripts/refold_cache.py /workspace/input/resume_cache/manifest.json --output-dir /workspace/output/resumed
```

This copies the source run to a new destination, preserves failed stages and
existing finite scores, imports missing required metrics from supported cached
responses, and regenerates exports and the summary. The destination must not
exist or be inside the source run. Relative artifact paths resolve within the
copied run. Missing predictions remain blocked; this command never retries an
endpoint. Completed low-scoring candidates are preserved, not resubmitted.

The fixture format extends the normal manifest with
`target.structure: {path, sha256}` and a per-candidate `prediction` binding:

```json
{
  "provider": "boltz2",
  "candidate_id": "candidate-1",
  "sequence_sha256": "<SHA-256 of exact sequence UTF-8 bytes>",
  "target_sha256": "<SHA-256 of target structure bytes>",
  "response": {"path": "responses/candidate-1.json", "sha256": "<SHA-256>"},
  "sample_index": 1,
  "complex_sha256": "<SHA-256 of selected structure string UTF-8 bytes>",
  "binder_chain": "B",
  "target_chain": "A",
  "plddt_scale": "0-100",
  "backbone": {"path": "backbone.pdb", "sha256": "<SHA-256>"},
  "backbone_chain": "D"
}
```

These are local provenance fields, not fields promised by a model endpoint.
Digests establish consistency with recorded inputs; they do not authenticate a
model or prove inference occurred. Record bindings when the original request
and response are saved; do not invent them from a convenient cached file.
A changed candidate, sequence, target, response or selected sample blocks the
import. Preserve conflicting evidence and record the reason.

- **Boltz2:** pair `structures[sample_index]` with the same index in
  `confidence_scores`, retained only as `boltz2_confidence`. Require equal array
  lengths. Do not select a higher-confidence sample independently of coordinates.
- **OpenFold3:** match `outputs[].input_id` to the candidate, then select
  `structures_with_scores[sample_index]`. Only `iptm_score` supplies ipTM;
  `confidence_score` and `complex_plddt_score` cannot replace it.
- **Binder pLDDT:** fixtures explicitly encode it in CA B factors with
  `plddt_scale` of `0-1` or `0-100`. Average the binder only and normalize to
  0–100. Experimental PDB B factors need not encode pLDDT. mmCIF uses
  `label_asym_id` to match the request, which can differ from author chain IDs.
  Require the complete binder length and both chain roles.
- **Missing RMSD:** verify the backbone digest and align complete, explicitly
  identified binder CA sets with `metrics.ca_rmsd_from_structures()`. Unequal
  lengths fail; do not truncate or compare the target instead.

An incomplete candidate receives scores only after all missing applicable
metrics and bindings validate. Finite existing values are never overwritten.
Recovered candidates record `score_provenance` (the full binding) and
`artifacts.complex` (the selected structure). `cache_status` is `complete`,
`recovered`, or `blocked`; `cache_reason` explains blocked work. Historical
`failure_reason` and stage records remain intact. A provisional passing fraction
still includes incomplete design candidates in its denominator.

## Target preparation

`pdb_utils.py` extracts the first model, chooses one CA per author residue, and
keeps insertion codes as distinct map keys. A blank alternate location takes
precedence; otherwise highest occupancy wins, with a lexicographic tie break.
Sequence indices follow CA order, not arithmetic offsets from the first author
number. Specify a chain when author numbering overlaps across chains.
`remap_to_seq_index()` raises for absent hotspots: record the missing IDs and
block that handoff. Verify insertion-code support for a downstream endpoint
before emitting a request containing such a hotspot.
