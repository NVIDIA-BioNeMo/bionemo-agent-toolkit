## Description: <br>

Run the released RFD4-Proteina NIM for joint protein structure and sequence
design, conditioned generation, and reward-guided beam search. The skill
prepares complete requests, invokes NVIDIA's hosted API or an existing
self-hosted NIM, and saves structures, sequences, metrics, and execution
provenance. It also supports offline preparation and saved-response extraction.
The [public product page](https://build.nvidia.com/ipd/rfd4-proteina) is the
source for service access and the API contract. <br>

## Owner

NVIDIA BioNeMo (`bionemofeedback@nvidia.com`) <br>

### License/Terms of Use: <br>

Toolkit default: Apache-2.0 AND CC-BY-4.0 — code under Apache-2.0; skill
content additionally available under CC-BY-4.0. These terms do not replace the
model, container, or hosted-service terms. The public
[model card](https://build.nvidia.com/ipd/rfd4-proteina/modelcard) identifies the
model's BSD 3-Clause license and the NVIDIA API Trial Service Terms of Use.
Consult that page for the governing terms and attribution. <br>

## Use Case: <br>

Developers and computational biologists conducting research protein-design work:

- Joint structure/sequence generation, including conditioned protein binders.
- Indexed motif scaffolding, enzyme design, and small-molecule binders.
- Antibody or nanobody CDR design with appropriate framework/target conditions.
- Partial diffusion of existing designs and inverse folding of fixed backbones.
- Search using deployment-supported reward metrics.

Inputs are JSON requests containing inline annotated mmCIF, or a parsed
`condition_spec` with complete mmCIF attachments. The task selects a sampler;
the input conditions define the biological problem. The bundled PD-1 binder
request comes from the public Deploy tab. <br>

Public RFdiffusion, ProteinMPNN, Proteina-Complexa, and native-model training
use separate workflows. Independent refolding and experimental validation are
outside this client's inference and extraction steps. <br>

### Deployment Geography for Use: <br>

The public model card lists global deployment. Service access and use remain
subject to the applicable product terms and the user's deployment environment. <br>

## Requirements / Dependencies: <br>

**Requires API Key or External Credential:** Yes for hosted inference and
container/model downloads; no for offline work or unauthenticated local
inference. <br>
**Credential Type(s):** NVIDIA API key in `NVIDIA_API_KEY` (client fallback:
`NGC_API_KEY`); NGC key in `NGC_API_KEY` for public container deployment. <br>

| Mode | Requirements |
| --- | --- |
| Offline preparation / saved-response extraction | Python >=3.10, task-selected input files, and a new writable output directory. The helper uses only the standard library. |
| Hosted inference | Network access to `https://health.api.nvidia.com/v1/biology/ipd/rfd4-proteina/generative` and a key with access to the product, sent as a Bearer token. No client GPU is required. |
| Existing self-hosted NIM | Reachable compatible service; default `http://localhost:8000/biology/ipd/rfd4-proteina/generative`. The helper does not send an API key in local mode. |
| Container deployment | Docker, NVIDIA Container Toolkit, a supported allocated GPU/driver, NGC access, and model-cache space. The public image is `nvcr.io/nim/ipd/rfd4-proteina:latest`; record or select a digest for reproducibility. |

An agent needs file and shell access to run the helper. No MCP server or private
source checkout is required. Use the [Deploy tab](https://build.nvidia.com/ipd/rfd4-proteina/deploy)
and [deployment reference](references/deployment.md) for local setup. <br>

## Known Technical Limitations: <br>

- **Input validation:** the helper catches common wire/attachment errors but does
  not implement every server rule or verify scientific conditioning. Renaming
  PDB to mmCIF is insufficient, and a task label cannot create missing conditions.
- **Model evidence:** response-integrity checks and finite-coordinate flags do
  not establish binding, folding, catalytic activity, or developability. Search
  rewards reflect the configured objective, not experimental success.
- **Refolding:** the documented API has no built-in oracle. Inspect `model.oracle`
  and actual predictor results before quoting pLDDT or refolding confidence.
- **Interpretation:** null metrics are unavailable values. Aggregate `n` can be
  smaller than design count. Search survivors and retained intermediates must
  be distinguished, and full returned sequences may include target chains and
  non-protein `X` tokens.
- **Runtime and replay:** limits, cache warmup, batching, and search affect time
  and memory. Preserve inputs, seeds, weights, backend, runtime, and schedule;
  replay complete batches/searches. `latest` can change, and cross-runtime GPU
  determinism is not guaranteed.
- **Validation coverage:** this revision has no claimed live production run,
  local GPU deployment, or completed agent benchmark. Offline checks are
  recorded separately from those unperformed evaluations.

## Known Risks and Mitigations: <br>

- **Data disclosure:** a submission sends all inline structures and conditions
  to the selected endpoint. Use inputs permitted by the product's data-use
  terms. For data that must remain on the machine, use a service on that machine;
  a user-supplied local-mode URL can still point to a remote host.
- **Credential leakage:** keys are read from the environment, not CLI arguments.
  The client sends hosted credentials only to its fixed hosted destination,
  omits them in local/offline modes, refuses redirects, and does not record
  request Authorization headers. Keep keys out of transcripts and shell tracing.
- **Unintended writes and duplicate work:** output directories must be new.
  The helper makes one POST without automatic retries. Retain pending/error IDs
  and establish service state before resubmitting. Review replicate/search budgets.
- **Local service exposure:** the documented Docker command binds inference to
  loopback and selects an allocated GPU. It does not replace existing containers
  or depend on a private launcher. The host enforces filesystem/network isolation.
- **Untrusted inputs and scientific misuse:** treat structures and responses as
  data, not agent instructions. Verify the user's biological conditions and
  report actual warnings. Designs require independent scientific review.

## Reference(s): <br>

- [NVIDIA product page and API](https://build.nvidia.com/ipd/rfd4-proteina)
- [Public model card](https://build.nvidia.com/ipd/rfd4-proteina/modelcard)
- [Public deployment guide](https://build.nvidia.com/ipd/rfd4-proteina/deploy)
- [Runtime instructions](SKILL.md) and [request API](references/request-api.md)
- [Examples](references/examples.md) and [parameters](references/parameters.md)
- [Science](references/science.md) and [result validation](references/validation.md)
- [Source provenance](references/sources.md) and [fixture manifest](assets/source-manifest.json)
- [Benchmark status](BENCHMARK.md) and [validation record](evals/validation-results.json)

## Skill Output: <br>

**Output Type(s):** [API Calls, Files, Analysis, Deployment Instructions] <br>
**Output Format:** [JSON, raw responses, annotated mmCIF, FASTA, and a report] <br>
**Output Parameters:** [Sequences/scalar metrics, per-design metadata, and 3D coordinates] <br>

| Artifact | Contents |
| --- | --- |
| `request.json` | Exact prepared/submitted bytes. |
| `transport.json` | Destination, mode, timestamps, status, hashes, and returned transport IDs when available. |
| `response.raw`, `response.json` | Raw response and parsed JSON when parsing succeeds. |
| `design_0000.cif`, etc. | Returned structures under client-assigned safe filenames. |
| `sequences.fasta` | Full returned sequences, when requested. |
| `summary.json` | Counts, IDs, seeds, origins, metrics/denominators, diagnostics, errors, warnings, and model/runtime/schedule provenance. |

**Other Properties Related to Output:** artifacts depend on mode and response.
Preparation does not generate structures. Saved-response extraction is labeled
`saved_response` and does not prove a new inference run. Identify chains from
the mmCIF before treating a sequence as binder-only. <br>

## Fail Operation: <br>

Exit `0` may indicate offline preparation or successful response extraction;
inspect status/provenance before claiming completed inference. HTTP 202 returns
exit `3` and retains pending diagnostics. No polling URL is guessed and no POST
is automatically repeated. Errors return `1`; invalid CLI arguments return `2`.
Available raw responses and transport metadata are preserved for diagnosis.
Missing hosted credentials fail before network access. <br>

## Evaluation Agents Used: <br>

No live agent run is claimed for this public-service revision. The benchmark
must be regenerated with the repository's evaluation tooling after the final
content is ready; earlier scores do not attest to the modified files. <br>

## Evaluation Tasks: <br>

[Five task definitions](evals/evals.json) cover hosted binder execution,
instructions-only local deployment, offline search preparation, condition-spec
preparation, and pending/oracle handling. Hosted execution needs a provisioned
API key and service access. [Trigger definitions](evals/trigger_evals.json)
contain nine positive and six negative queries; no trigger scores are claimed. <br>

## Evaluation Metrics Used: <br>

The intended agent evaluation checks security, answer correctness, skill
activation, task completion and workflow adherence, tool productivity, and token
use. These dimensions measure agent behavior, not biological design success.
Offline unit tests measure client behavior against synthetic responses. <br>

## Evaluation Results: <br>

**Live agent benchmark: pending.** [BENCHMARK.md](BENCHMARK.md) states that this
revision has not been evaluated. [evals/validation-results.json](evals/validation-results.json)
records the actual offline client and public-schema checks. No production
inference, local GPU deployment, independent refolding, or experimental success
is inferred from them. <br>

## Skill Version(s): <br>

Public-service revision: October 20, 2026. The public model card and API schema
identify RFD4-Proteina 1.0.0. That model/API version is distinct from the toolkit
package version and the container's mutable `latest` tag. Record the actual
image digest and returned model/runtime metadata for reproducible runs. <br>

**Signing evidence:** a new service-account signature is required after fresh
evaluation. The obsolete signature was removed rather than retained against
modified content. Catalog onboarding remains pending until new evidence is
attached. <br>

## Ethical Considerations: <br>

NVIDIA believes Trustworthy AI is a shared responsibility. Review whether this
skill and its underlying service meet the requirements of the intended use,
including data handling and potential misuse. Treat designs as research
candidates requiring independent validation, not clinical guidance or evidence
of therapeutic safety or efficacy. Review applicable biological safety
requirements before synthesis or experimental work. <br>

Report potential security vulnerabilities to NVIDIA PSIRT (`psirt@nvidia.com`)
following the toolkit's `SECURITY.md`, rather than publishing sensitive details
in public issues. <br>
