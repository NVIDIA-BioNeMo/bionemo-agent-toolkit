# Wire contract and transport

## Contents

- [Endpoints](#endpoints)
- [Request envelope and inputs](#request-envelope-and-inputs)
- [Response](#response)
- [Errors and long requests](#errors-and-long-requests)

## Endpoints

Use Nam's staging route:
`https://buildapi.dev.ngc.nvidia.com/v2/predict/models/nvidia/rfd4-proteina`.
POST JSON with `Content-Type: application/json` and `NVCF-POLL-SECONDS: 300`.
No `Authorization` header is used by `sample_requests/run_staging_nvcf.sh`.
Its curl timeout is 340 seconds; the bundled Python client allows 600 seconds
per socket operation. These are client limits, not service completion promises.

Staging submission uploads the complete JSON request, including every inline
structure and design specification, to NVIDIA's remote internal staging
service. The request has no Authorization header; this skill establishes no
retention or logging guarantee for that service. Use inputs permitted on
that destination. For data that must stay on the machine, use a local NIM
on that machine. Do not change a user's chosen destination silently.

Local inference: `POST /biology/ipd/rfd4-proteina/generative`, with no `/v1`
prefix. The upstream RC launcher maps host port 6626 to container port 8000.
Use `/v1/health/ready` for readiness, `/v1/tasks` for task and metric discovery,
and `/openapi.json` or `/docs` for that running image's schema. Some discovery
fields were added after the RC; their absence is a version difference.

The source also documents an alternative authenticated
`https://health.api.nvidia.com/v1/stg/biology/ipd/rfd4-proteina/generative` route.
It uses a function-authorized NGC key and has different access rules. It is
not the route in Nam's `run_staging_nvcf.sh`, and the bundled client does
not switch to it or implement its credentials. Registry access does not prove
function invocation access. No production endpoint is assumed by this skill.

## Request envelope and inputs

The top-level fields are `task`, `input`, `sampling`, `partial`, `search`,
`metrics`, and `output`. Unknown fields are rejected by the server's strict
Pydantic models. Task/schedule details live in `references/parameters.md`.

The snippets below only write a local request. Its embedded file contents
are uploaded if the request is subsequently submitted. Use only the input
files selected for the task; `--dry-run` never uploads them.

Canonical annotated-CIF request, built from a real user file:

```python
import json
from pathlib import Path

source = Path("target_annotated.cif")
payload = {
    "task": "generation",
    "input": {
        "format": "annotated_cif",
        "example_id": "target_design",
        "file": {"filename": source.name, "content": source.read_text()},
    },
    "sampling": {"recycle_strategy": "thinking_medium", "num_replicates": 1, "seed": 42},
    "metrics": {"tags": ["design"]},
    "output": {"structure_format": "mmcif", "include_sequence": True},
}
Path("request.json").write_text(json.dumps(payload, indent=2) + "\n")
```

This requires an already authored design specification in the mmCIF.
Conditions are stored in extra `_atom_site` columns and other annotations.
For unconditioned monomers the upstream input still contains a template with
expandable segments. NaN coordinates in these input placeholders can be
intentional; non-finite coordinates in generated output are a failure.

For a JSON condition spec and ordinary mmCIF attachments:

```python
spec = json.loads(Path("condition_spec.json").read_text())
structures = [Path("target.cif")]  # Include every structure the spec references.
payload["input"] = {
    "format": "condition_spec",
    "example_id": "conditioned_design",
    "spec": spec,
    "files": [{"filename": p.name, "content": p.read_text()} for p in structures],
}
Path("request.json").write_text(json.dumps(payload, indent=2) + "\n")
```

`spec` is an object, not a YAML string or full Hydra configuration. If the
supplied spec is YAML, parse it with a safe YAML loader first. `spec.input`
must exactly match an attached filename; other nested structure references
must also resolve to attachments. Filenames are bare names of at most 255
characters, never server paths. `input_as_annotated_cif: true` tells the
upstream converter to consume existing annotations (see example 02).

`C_CRD` holds coordinates, `C_SEQ` holds identities, and `C_HOT` marks hotspots.
Selections refer to the actual input chains/residues; use the antibody and PPI
examples to see concrete specifications. Do not invent selections for missing
targets. Conversion to ordinary mmCIF alone does not create design conditions.

PDB is not accepted in either dialect. The upstream guidance is
`atomworks.io.parser.parse` followed by `to_cif_file`, with bond/charge checks.
Use a chemistry-aware conversion for ligands and re-author missing conditions.
Renaming a PDB or putting it in `file.content` is insufficient. The removed
`contig_spec` dialect and scaffold's top-level `contigs` are not served.

## Response

| Field | Meaning |
| --- | --- |
| `request_id`, `task`, `duration_ms` | Server job metadata; `request_id` can be the literal `local`, so also retain transport IDs/hashes |
| `model` | Checkpoints, execution backend, device/dtype, and oracle list |
| `runtime` | Package versions, GPU, acceleration settings, and deployed limits |
| `schedule` | Reported steps, bands, trunk passes, and partial start times; see the BioIR partial-schedule caveat below |
| `search` | Search report, or null; rollout counts are computational work, not design counts |
| `designs[]` | Generated results with opaque `design_id`, `replicate_index`, `origin`, `seed` |
| `designs[].structure` | `{format: "mmcif", filename, content}`, or null when suppressed |
| `designs[].sequence` | One-letter sequence; `X` can represent non-protein tokens |
| `designs[].metrics` | `metric.output_key` values; null is permitted |
| `designs[].diagnostics` | Finite-coordinate flag, counts, batch size, optional CA RMSD and sequence recovery |
| `designs[].chain_of_interest` | Context for `*_coi` metrics; not automatically the designed binder |
| `designs[].search_reward` | Search selection score, or null outside search |
| `aggregated_metrics[]` | `{metric, reduction, value, n}`; retain the denominator |
| `warnings[]` | Nonfatal differences, unavailable metric results, schedule notices |

`output.structure_format` accepts `mmcif` (default) or `none`.
`output.include_sequence` defaults to true. Output is not `output_pdb` or
`elapsed_ms`. Standard responses already include provenance; optional
`X-Include-Runtime-Metrics` requests stage timings from supporting servers.
Shared batch/search forward timings must not be summed once per design.

In the authoring smoke test, a partial request with fraction 0.4 returned
`kind=partial` but still reported all 60 steps / 185 trunk passes and null
start times. The inspected BioIR response builder uses the full sampling
configuration for these fields. Preserve the values as reported metadata;
they do not establish the executed partial trajectory's cost.

## Errors and long requests

The NIM's own errors use
`{"error":{"code":"schema_violation","message":"...","details":["..."]}}`.
Gateway responses can instead be text/HTML. Preserve the raw body before
parsing. Typical NIM codes include `invalid_request`, `invalid_input`,
`request_too_large`, `out_of_memory`, `model_unavailable`,
`pipeline_unavailable`, `oracle_unavailable`, `service_busy`, and `timeout`.

The Python helper makes one POST and refuses redirects. A 202 saves the body
and `NVCF-REQID`/`X-Request-ID` when returned, exits 3, and leaves the job
pending. Nam's script supplies no documented result-fetch URL for buildapi.
Obtain a supported completion mechanism from the deployment owner before
retrieving a pending job; do not guess a generic NVCF URL.

For 422, inspect the actual error: common causes include raw PDB, unattached
structure references, wrong task or old fields, conflicting partial settings,
unavailable oracle metrics, or search checkpoints inconsistent with the
resolved schedule. A 200 without designs or a failed validation is not success.
