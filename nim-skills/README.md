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
and sequence design, conditioning, and reward-guided search through the released
[NVIDIA API](https://build.nvidia.com/ipd/rfd4-proteina) or a self-hosted public
NIM container. Hosted inference uses `NVIDIA_API_KEY` (`NGC_API_KEY` fallback);
the local client sends no inference credential. The Python client uses only
the standard library.

The bundle's endpoint, authentication, deployment instructions, and PD-1 request
are grounded in public product documentation. See the
[source notes](rfd4-proteina-nim/references/sources.md),
[fixture manifest](rfd4-proteina-nim/assets/source-manifest.json), and
[skill card](rfd4-proteina-nim/skill-card.md).

The previous evaluation/signature no longer applies to these modified files.
[`BENCHMARK.md`](rfd4-proteina-nim/BENCHMARK.md) marks live evaluation as pending;
a new service-account signature must be generated after evaluation. The
[validation record](rfd4-proteina-nim/evals/validation-results.json) describes
offline checks without claiming production inference or local GPU deployment.

The canonical toolkit copy is `nim-skills/rfd4-proteina-nim/`; the generated
plugin copy is `skills/bionemo-agent-toolkit/skills/rfd4-proteina-nim/`.
Keep both copies in sync. Run the client tests from the toolkit root:

```bash
python -B -m unittest discover -s nim-skills/rfd4-proteina-nim/tests -v
```

These tests use synthetic responses and a temporary loopback HTTP service.
They do not perform live production inference.

For native RFProteina model workflows, see the separate
[open-model skill collection](../open-models-skills/rfd4-proteina/README.md).
