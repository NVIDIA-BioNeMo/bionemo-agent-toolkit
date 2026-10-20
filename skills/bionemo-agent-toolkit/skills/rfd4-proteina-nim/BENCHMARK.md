# Skill Benchmark: rfd4-proteina-nim

> **Overall verdict: NOT EVALUATED — public-service revision requires a new run**

## Scope

This revision targets the released RFD4-Proteina NIM at
`https://health.api.nvidia.com/v1/biology/ipd/rfd4-proteina/generative`, with
Bearer authentication, and the public `nvcr.io/nim/ipd/rfd4-proteina` container.
Its endpoint, authentication, examples, documentation, and evaluation tasks have
changed. Earlier scores and signatures do not attest to these files.

## Available checks

[Client tests](tests/test_design.py) exercise request preparation, hosted
credential handling, local requests, redirects, pending/error responses, and
artifact extraction using synthetic responses and temporary loopback servers.
[Validation results](evals/validation-results.json) record the checks performed
for this revision. They are not a live agent benchmark or proof of production
inference success.

## Evaluation dataset

Five task definitions are in [evals/evals.json](evals/evals.json): hosted binder
execution, local deployment instructions, offline search preparation,
condition-spec preparation, and pending/oracle handling. The separate trigger
set has nine positive and six negative queries.

Hosted execution requires a valid NVIDIA API key made available to the agent
through the evaluation environment's secret mechanism and access to the product.
Offline cases require neither credentials nor a live NIM. A missing credential
or failed service request must remain a reported blocker, not a fabricated run.

## Results

No live-agent scores, production inference results, or local GPU deployment
results are claimed for this revision. Regenerate the benchmark with the
published evaluation tooling and obtain a new service-account signature after
the final content passes evaluation. Catalog onboarding remains pending until
that evidence is attached; an offline test result must not be relabeled PASS
for Tier 3.
