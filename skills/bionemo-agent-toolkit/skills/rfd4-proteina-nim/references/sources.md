# Sources and version boundaries

This skill is internal. It was researched against the user's local RFD4 and
BioNeMo toolkit checkouts on 2026-10-13. The operational contract is grounded
in the RFD4 source and live responses, rather than copied from another NIM.

## Nam's instructions

The user supplied Nam's staging endpoint and two `run_staging_nvcf.sh`
invocations, plus the pinned RC image and `NGC_API_KEY_STAGING` instruction.
His message describes two workflows: invoke an already deployed staging
service, or launch the RC locally. The staging script does not use the
registry key. No message was sent to Nam as part of creating this skill.

## Source revision

Repository: [bionemo/rfd4-proteina-nim](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim).
Inspected branch: `origin/ntdo/oss-pipeline`.
Pinned source snapshot: `67d600ba62f1219ed6516bb0c682e55d3b71c47c`.

The existing working checkout stayed on `main` at
`8c1b90a257e05aeb0e490ea877feaef1cd49875d`. Its root `examples/sample_request.json`,
`examples/sample_request.py`, `examples/sample_response.json`, `lib/api_models/`,
and `inference.py` describe a fixed-response scaffold. They were read, but do
not define the implemented service. The named branch was inspected through a
temporary Git archive without switching or modifying that checkout.

Primary source files at the pinned revision:

| Source | What it establishes |
| --- | --- |
| [sample_requests/run_staging_nvcf.sh](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/sample_requests/run_staging_nvcf.sh) | Exact buildapi route, no auth, hold header, curl timeout, output trailer |
| [scripts/deploy_nim.sh](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/scripts/deploy_nim.sh) | Credential precedence, runtime key, port 6626, mounts, foreground execution, container replacement |
| [nim/api/dto/request.py](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/nim/api/dto/request.py) | Input dialects, validation, task alias, schedules, batching, partial/search rules |
| [nim/api/dto/response.py](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/nim/api/dto/response.py) | Output structure, origins, diagnostics, seed semantics, aggregates |
| [nim/api/dto/constants.py](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/nim/api/dto/constants.py) | Strategy bands, metric tags and capability gates |
| [nim/api/tasks.py](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/nim/api/tasks.py) | Task rules and runtime-limit validation |
| [nim/api/rfd4_nim_main.py](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/blob/67d600ba62f1219ed6516bb0c682e55d3b71c47c/nim/api/rfd4_nim_main.py) | Inference, discovery, and readiness routes |
| [nim/examples/](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/tree/67d600ba62f1219ed6516bb0c682e55d3b71c47c/nim/examples) | Implemented task examples and input-authoring context |
| [sample_requests/](https://gitlab-master.nvidia.com/bionemo/rfd4-proteina-nim/-/tree/67d600ba62f1219ed6516bb0c682e55d3b71c47c/sample_requests) | Bundled request sources and documented capability/metric caveats |

Also inspected: `docs/contract.md`, `docs/deploy.md`, `nim/api/settings.py`,
`nim/api/exceptions.py`, the antibody/nanobody example guides, and internal
OpenAPI client examples. Some READMEs contain older claims alongside
corrections; the executable DTO/validator and observed response take priority.
The bundled files retain their original JSON bytes; SHA-256 provenance lives
in `assets/source-manifest.json`. Upstream licensing and notices remain at
the source repository; this internal skill does not relicense the model or data.

## Review of fixture scan findings

The October 13 evaluator reported whitespace padding in
`assets/requests/16_ppi_binder.json` and a phone-number pattern in
`assets/requests/25_secondary_structure_conditioning.json`. Inspection of the
decoded mmCIF located the padding in the `_entity_poly` table (line 33): two
121-space column separators, with no concealed instructions. The phone-shaped
matches span the `_atom_site.pdbx_formal_charge` and `_atom_site.Cartn_x`
columns, starting at atom ID 193 (decoded line 433): a positive formal charge
followed by a Cartesian coordinate, not contact information.

These fixtures retain their upstream bytes and manifest hashes. Keep chemical
charges, coordinates, annotations, and sequences intact when reviewing these
advisories; the scanner's pattern labels do not establish an injection or PII.

## Authoring pattern

The entrypoint, API/parameters/examples/science/validation references,
executable client, and evaluation cases follow the layout of
`/workspace/bat/bionemo-agent-toolkit/nim-skills/`, particularly the
RFDiffusion, ProteinMPNN, and MSA-Search skills. Their endpoint/authentication,
PDB payloads, image paths, cache mounts, and performance claims were not
transferred to RFD4.

[Anthropic's skill-authoring guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
informed the concise discovery description, short entrypoint, direct links to
conditional references, deterministic helpers, and behavior-based evaluation
scenarios. The local skill-creator guidance supplied the scaffolding and
frontmatter validation. No special agent permissions or model changes are
required by this skill.

## Validation evidence and limits

See `../evals/validation-results.json` for captured run metadata and the
repository's `artifacts/validation-20261013/` for full local run artifacts.
Those generated outputs are Git-ignored; the compact evidence file is retained.
Fixtures in `tests/test_design.py` are synthetic and exercise client behavior,
not protein-design quality. Evaluation prompts and trigger examples are
provided separately; writing them does not establish model-based evaluation
scores, which were not measured during authoring.

Live staging tests identify a responding service and its reported runtime;
they do not identify Nam's exact RC image digest or certify its compatibility.
Docker and exported NGC keys were unavailable here, so local deployment was
not executed. The September image remains pinned in the instructions, with
schema discovery required before using October examples against it.
