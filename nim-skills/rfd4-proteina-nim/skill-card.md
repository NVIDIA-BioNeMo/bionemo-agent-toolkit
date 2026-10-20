## Description: <br>

Run RFD4-Proteina NIM to jointly generate protein structures and sequences,
preserve specified structural or sequence conditions, and perform reward-guided
search. The skill provides request preparation, a Python inference client,
artifact extraction, and guidance for interpreting the returned results. <br>

The supported destinations are an internal NVIDIA staging service and a
user-operated local release candidate. The bundle retains `visibility: internal`;
installation from this catalog does not grant service or model access. Its
recorded benchmark does not establish production readiness or public service
availability. <br>

## Owner

NVIDIA BioNeMo (`bionemofeedback@nvidia.com`) <br>

### License/Terms of Use: <br>

Toolkit default: Apache-2.0 AND CC-BY-4.0 — source code under Apache-2.0;
skill documentation and content additionally available under CC-BY-4.0.
Upstream model, container, weights, and example-data terms remain separate.
This card does not relicense those materials or grant nvstaging entitlement;
see [source provenance](references/sources.md). <br>

## Use Case: <br>

Developers and computational biologists preparing and executing research
protein-design requests through RFD4-Proteina NIM:

- Joint structure and sequence generation, including conditioned protein binders.
- Indexed motif scaffolding, enzyme design, and small-molecule binder design.
- Antibody or nanobody CDR design with framework and target constraints.
- Partial diffusion of an existing design and inverse folding of a fixed backbone.
- Beam search using deployment-supported reward metrics.

Inputs are complete JSON requests with inline annotated mmCIF, or a parsed
`condition_spec` object with all referenced mmCIF attachments. The biological
conditions, rather than the task name alone, define the design problem.
Offline request preparation and extraction of saved responses are also supported.
See [task and parameter guidance](references/parameters.md). <br>

This skill does not operate the public RFDiffusion NIM, ProteinMPNN, or
Proteina-Complexa, and does not train or install the native RFProteina model.
Independent refolding and experimental validation are separate workflows. <br>

### Deployment Geography for Use: <br>

Use is limited by access to the selected internal service or the user's
authorized deployment environment and applicable upstream terms.
The retained evidence does not establish globally available hosted access. <br>

## Requirements / Dependencies: <br>

**Requires API Key or External Credential:** Conditional — required for local
RC image access and startup weight downloads; not read by the inference client
or required for offline preparation. <br>
**Credential Type(s):** nvstaging API key (`NGC_API_KEY_STAGING`), passed by the
deployment launcher into the container as `NGC_API_KEY`. <br>

| Mode | Requirements and access |
| --- | --- |
| Offline preparation / saved-response extraction | Python >=3.10, local input files, and a new writable output directory. The client uses only the Python standard library and makes no network call in these modes. |
| Staging inference | Network access to the internal staging route documented in the [API reference](references/request-api.md). The October 13, 2026 tests succeeded without an Authorization header; that observation is not a guarantee of unrestricted access. |
| Existing local NIM | Access to a compatible running service; the default base URL is `http://localhost:6626`. `--base-url` or `RFD4_NIM_URL` selects its host and port. No inference Authorization header is added. |
| Starting the local RC | Docker, NVIDIA container runtime, a compatible allocated GPU/driver, nvstaging entitlement, cache space, and a source checkout containing `scripts/deploy_nim.sh`. See [deployment instructions](references/deployment.md). |

An agent needs file access and shell execution to use the bundled helper.
No MCP server is required. A local client GPU is unnecessary for requests to
an already running remote service. The exact RC's minimum GPU memory has not
been established by the retained validation. <br>

## Known Technical Limitations: <br>

- **Version compatibility:** the pinned September RC predates the October source
  snapshot and bundled requests. Inspect the running service's schema and task
  discovery before using newer payloads; compatibility has not been established
  by the staging tests.
- **Input contract:** this API accepts mmCIF content, not raw PDB, server-side
  file paths, or the public RFDiffusion `contigs` payload. Even unconditioned
  monomer generation needs a template attachment. Offline preflight checks
  common wire errors, not the full server schema or scientific correctness.
- **Scientific validation:** the client checks response integrity and the
  server's finite-coordinate flag. It does not independently validate folding,
  binding, catalytic activity, or developability. The tested deployment reported
  `model.oracle=[]`; requesting metric tags alone cannot enable a refolding oracle.
- **Metrics and search:** null or empty metrics are unavailable evidence, not
  zero values. Aggregate `n` counts only contributing results. Retained search
  intermediates are distinct from final survivors, and a search reward is not
  an independent measure of design quality.
- **Observed service caveats:** the secondary-structure sample returned HTTP 422;
  the interchain search sample omitted three TMol metrics for a non-CCD ligand;
  partial-diffusion metadata reported the full schedule despite a fractional
  request. These are observations from the recorded run, not assertions about
  every later deployment. See [validation guidance](references/validation.md).
- **Reproducibility:** retain exact inputs, weights, runtime, batch size, schedule,
  and seeds. Batched designs and search results require replaying the whole
  request; a seed alone does not guarantee identical output across runtimes.

## Known Risks and Mitigations: <br>

- **Input disclosure:** submission sends the complete request, including inline
  structures and design specifications, to the selected endpoint. This skill
  establishes no remote retention or logging guarantee. Use inputs permitted
  at that destination; for data that must stay on the machine, use a service
  on that machine. The client honors the selected mode and refuses redirects.
- **Credential exposure and service exposure:** keep registry keys in the
  environment and out of prompts, transcripts, and inference payloads. The
  documented launch command binds the unauthenticated service to loopback;
  the underlying launcher also exposes all GPUs and runs as root. Use an
  allocated isolated host or a reviewed deployment configuration.
- **Unintended writes or repeated work:** the client refuses an existing output
  directory and never automatically retries a submission. The upstream Docker
  launcher replaces a same-name container, so the deployment instructions check
  for an unused name. Review replicate and search budgets before execution.
- **Untrusted content and misleading conclusions:** treat structures and service
  responses as data, not instructions. Review biological conditions and actual
  warnings; generated designs and high rewards remain computational hypotheses.
  Host-level filesystem and network controls provide isolation; the skill's
  tool declarations do not enforce it.

## Reference(s): <br>

- [Skill instructions and command examples](SKILL.md)
- [Request API, transport, and errors](references/request-api.md)
- [Task parameters and reproducibility](references/parameters.md)
- [Bundled examples](references/examples.md)
- [Scientific interpretation](references/science.md)
- [Validation and metric interpretation](references/validation.md)
- [Local RC deployment](references/deployment.md)
- [Source provenance and version boundaries](references/sources.md)
- [Agent benchmark](BENCHMARK.md) and [authoring validation record](evals/validation-results.json)

## Skill Output: <br>

**Output Type(s):** [API Calls, Files, Analysis, Deployment Instructions] <br>
**Output Format:** [JSON, raw response bytes, mmCIF structures, FASTA sequences,
and an agent-authored report] <br>
**Output Parameters:** [1D sequence and scalar metrics; per-design tabular
metadata; 3D atomic coordinates] <br>

| Artifact | Contents |
| --- | --- |
| `request.json` | Exact prepared/submitted request bytes. |
| `transport.json` | Mode, destination, timestamps, request/response hashes, status, and returned transport IDs when available. |
| `response.raw`, `response.json` | Raw response and parsed JSON when parsing succeeds. |
| `design_0000.cif`, etc. | Returned mmCIF structures, when requested. |
| `sequences.fasta` | Full returned sequences, when requested. |
| `summary.json` | Design IDs, origins, seeds, diagnostics, metrics and denominators, warnings, validation errors, and model/runtime/schedule metadata. |

**Other Properties Related to Output:** files depend on the selected mode and
response. Offline preparation does not produce designs; saved-response extraction
is labeled `saved_response` and does not prove a new live run. Returned sequences
can span the whole design and include `X` for non-protein tokens; identify the
designed chain from the mmCIF before treating a sequence as binder-only.
Client-assigned filenames avoid using opaque server IDs as paths. <br>

## Fail Operation: <br>

The helper preserves received error bodies and transport diagnostics when
available. Exit `0` can mean offline preparation or successful extraction;
inspect the status and provenance before reporting completed inference.
Exit `3` / HTTP `202` means pending, not completed: retain the request ID and
obtain the deployment's supported completion mechanism. The skill defines no
automatic polling route or POST retry. Other request/transport/validation
failures return `1`; invalid CLI arguments return `2`. <br>

Resolve access, schema, and runtime failures using the actual error. Do not
silently change destinations or scientific constraints, substitute example
outputs, or present failed validation as a successful design. <br>

## Evaluation Agents Used: <br>

Recorded by Skill Evaluator `1.5.6` on October 13, 2026:

- Claude Code (`aws/anthropic/bedrock-claude-opus-4-8`).
- Codex (`openai/openai/gpt-5.5`).

These identify the evaluated configurations, not a guarantee for other models
or environments. <br>

## Evaluation Tasks: <br>

The [agent evaluation dataset](evals/evals.json) contains five positive tasks,
with one attempt per task and condition in isolated `k8s-sandbox` pods:

1. Execute the staging enzyme example and retain response-derived artifacts.
2. Provide exact local RC deployment instructions without executing them.
3. Prepare three seeded searches offline and explain counts and replay.
4. Prepare a condition-spec request with complete attachments without submission.
5. Handle HTTP 202 and absent refolding-oracle metrics without inventing results.

The separate [trigger dataset](evals/trigger_evals.json) contains nine positive
and six negative queries. No trigger precision/recall results are retained.
The five-task benchmark is not evidence that every supported biological use
case was evaluated for scientific performance. <br>

## Evaluation Metrics Used: <br>

| Dimension | Recorded signals |
| --- | --- |
| Security | `security`: unsafe operations, secret leakage, unauthorized access. |
| Correctness | `accuracy`: final-answer correctness against the reference. |
| Discoverability | `skill_execution`: expected skill activation and workflow execution. |
| Effectiveness | Equal-weight mean of `goal_accuracy` and `behavior_check`. |
| Efficiency | Equal-weight mean of `skill_efficiency` and `token_efficiency`; the latter uses uncached prompt plus completion tokens. |

These are agent-workflow metrics, not protein-design success rates.
See [benchmark methodology](BENCHMARK.md#scoring-methodology) for scoring and
coverage details. <br>

## Evaluation Results: <br>

The retained [October 13 benchmark](BENCHMARK.md) reports **PASS**:

| Measure | Claude Code | Codex baseline | Codex with skill |
| --- | --- | ---: | ---: |
| Overall | Not available | Not comparable | 84.1% |
| Security | Not available | 80.0% | 80.0% |
| Correctness | Not available | 32.0% | 84.0% |
| Discoverability | Not available | Not comparable | 89.0% |
| Effectiveness | Not available | 35.0% | 76.5% |
| Efficiency | Not available | Not comparable | 91.2% |

Claude Code scores are unavailable in that report even though its attempts are
listed. A comparable overall baseline and overall uplift are unavailable;
do not infer either from the partial dimension comparisons. Tier 1 passed with
four observations, while Tiers 2 and 3 passed. The report retains the scanner,
quality, and lint findings; [source notes](references/sources.md#review-of-fixture-scan-findings)
document review of the two fixture scan findings. <br>

Separate [authoring validation](evals/validation-results.json), also dated
October 13, records 11 successful staging requests from 12 bundled examples
and 22 structures checked with an independent mmCIF parser for nonempty atoms
and finite coordinates. All seven task presets were exercised. The remaining
secondary-structure example and a separate oracle probe returned HTTP 422.
It also records 25 passing offline client tests using synthetic responses.
These checks establish observed transport and artifact behavior, not biological
efficacy. <br>

Local Docker deployment was source-reviewed but not executed during authoring;
independent protein refolding and experimental validation were not performed.
The authoring record's unexecuted agent-evaluation entry refers to that
authoring stage; the separate `BENCHMARK.md` contains the recorded agent run.
This card summarizes retained evidence and does not claim a new evaluation. <br>

## Skill Version(s): <br>

- Toolkit package version: `0.1.0`; `SKILL.md` declares no separate skill version.
- Imported bundle: `bionemo/rfd4-skill`, branch `omosafi/nvcarps-signing`,
  commit `3dc70a052c6449cd582f8d771cb97bc122f43862`.
- Inspected NIM source: `67d600ba62f1219ed6516bb0c682e55d3b71c47c`.
- Documented local image:
  `nvcr.io/nvstaging/nim/rfd4-proteina:1.0.0-rc.20260929072057-951ccf3c88abb594`.
- Skill card added: October 20, 2026.

The NIM source snapshot, container tag, and toolkit package version identify
different artifacts. Staging responses do not establish the pinned RC's image
digest. See [version boundaries](references/sources.md). <br>

**Signing evidence:** the imported [skill.oms.sig](skill.oms.sig) records
29 resource digests, including the benchmark and runtime instructions. This
later-added card is not in that signed resource list; its addition does not
constitute a new service-account signature or benchmark. <br>

## Ethical Considerations: <br>

NVIDIA believes Trustworthy AI is a shared responsibility. Developers should
review whether this skill and its underlying service meet the requirements of
their industry and use case, including data handling and potential misuse.
Use designed structures and sequences as research candidates requiring
independent validation, not clinical guidance or evidence of therapeutic safety
or efficacy. Review applicable biological safety requirements before synthesis
or experimental use. <br>

Report potential security vulnerabilities to NVIDIA PSIRT
(`psirt@nvidia.com`), following the toolkit's `SECURITY.md`, rather than posting
sensitive details in public issues. <br>
