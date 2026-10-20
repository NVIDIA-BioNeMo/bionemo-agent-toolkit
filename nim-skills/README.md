# Individual NIM Skills

Portable runtime skill bundles for individual BioNeMo NIM microservices. See
each bundle's metadata and references for its runtime, access, and license terms.

Each directory contains:

- `SKILL.md`: runtime workflow instructions for agents.
- `references/*.md`: endpoint, payload, response, Docker, science,
  parameter, validation, and example details for the NIM.
- `evals/`: packaged task and trigger eval definitions for Agent Skills
  publishing and compatibility.

Use the top-level README for setup and agent-discovery guidance.

## RFD4-Proteina

[`rfd4-proteina-nim`](rfd4-proteina-nim/SKILL.md) supports joint protein structure
and sequence design, conditioning, and reward-guided search through an internal
staging endpoint or a local release-candidate deployment. It requires access to
the selected service; the bundle retains its internal visibility metadata and
prerelease version boundaries. Its Python client uses the standard library.

The complete bundle was imported unchanged from `bionemo/rfd4-skill`, branch
`omosafi/nvcarps-signing`, commit
`3dc70a052c6449cd582f8d771cb97bc122f43862`. That commit was authored by
`nvcarps-service-account` and added the
[`BENCHMARK.md`](rfd4-proteina-nim/BENCHMARK.md) and
[`skill.oms.sig`](rfd4-proteina-nim/skill.oms.sig) artifacts.
The [live validation evidence](rfd4-proteina-nim/evals/validation-results.json),
request fixtures, references, tests, and UI metadata are included as well.
Source repository paths and evaluation dates in those files are historical
provenance. Changes to signed content require a new evaluation and signature.

The toolkit-added [skill card](rfd4-proteina-nim/skill-card.md) summarizes
capabilities, access requirements, limitations, and the retained evaluation
evidence. It is separate from the original signature's resource list.

The canonical toolkit copy is `nim-skills/rfd4-proteina-nim/`; the generated
plugin copy is `skills/bionemo-agent-toolkit/skills/rfd4-proteina-nim/`.
Both retain the original signed files. Run the client tests from the toolkit
root:

```bash
python -B -m unittest discover -s nim-skills/rfd4-proteina-nim/tests -v
```

These tests use synthetic responses and a temporary loopback HTTP service.
They do not perform live staging inference.

For native RFProteina model workflows, see the separate
[open-model skill collection](../open-models-skills/rfd4-proteina/README.md).
