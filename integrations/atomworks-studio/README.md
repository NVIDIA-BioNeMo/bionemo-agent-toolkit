# Embedded AtomWorks Studio adapter

This adds a conversation-embedded MCP App to BioNeMo Agent Toolkit, following the NGS
Workbench separation between an app surface and agent execution tools. It does
not introduce an RFD4 skill. Use the existing RFD4-Proteína skills from your
authorized model checkout for setup, annotated CIFs, generation, and evaluation.

Ask Codex to “open RFD4 Studio” to display the tool card in the conversation.
It has no global full-page entry point; expand the card beside the chat if desired.

The app opens the deployed AtomWorks Studio editor with Molstar, preloads its
PD-L1 binder example, and exports a validated, immutable annotated CIF. Review
freezes the input checksum, number of designs, seed, and exact Brev target.
“Ask Codex to generate” sends that plan back to the conversation. Only the
agent server exposes execution; the host prompts before that tool runs.
Retrying the same plan reuses its job instead of submitting another GPU run.
Text and image notes are explanatory; only exported molecular conditions affect
RFD4 generation. The current embedded UI supports text notes, an optional PNG image note, and 3D selections.

## Local setup

Use the upstream setup skill to prepare an existing Brev GPU instance and
AtomWorks Studio. This adapter does not provision a machine or download weights.
The model checkout must match the revision in `scripts/core.py`; its installed
entrypoint is `REMOTE_ROOT/model/.venv/bin/rfd4-generate`. Write that checkout's
commit to `REMOTE_ROOT/model-revision`. Run Studio on remote loopback and forward
it to a local port (for example 18764). Set Studio's
`ANNOTATION_STUDIO_FRAME_ANCESTORS` to the actual trusted desktop app frame origin;
keep its existing self origin. A browser-only origin such as localhost:8765 will
not authorize the embedded desktop frame. Do not use a wildcard.

Copy `config.example.json` into `$RFD4_STUDIO_HOME/config.json`, with a directory
outside the repository. Fill in the exact Brev instance ID and remote root.
Without an override, state lives in `~/.local/share/bionemo-rfd4`. Authenticate
Brev and select the organization containing that instance. Runtime dependencies
are installed with uv; alternatively set `RFD4_STUDIO_PYTHON` to a Python 3.12
interpreter with `requirements.txt` installed.

Generate a local plugin that includes the existing upstream skills unchanged:

```sh
python scripts/plugin_sync.py --write
python scripts/stage_rfd4_plugin.py --model-repo /authorized/RFD4 --output /local/plugin
```

This staged bundle contains restricted model documentation and helpers. Keep it
local; it is not the public distribution artifact. Upstream skill instructions
still run against the configured model checkout. No Studio source, model
weights, or RFD4 skills are redistributed in this adapter's repository payload.
Upstream licenses remain applicable independently of this integration.

## Verification and limits

```sh
python -m unittest discover -s tests -p test_atomworks_studio.py
python scripts/plugin_sync.py --check
```

The Studio API must provide sessions, selection queries, conditions, and export.
Its server owns the annotation state. Jobs use a detached local submission worker
and durable records. Ambiguous submissions require inspection and are never
retried automatically. A stopped local worker before remote launch can leave a
queued record; inspect `worker.log` before preparing another plan. This is a
single-user local integration, not a multi-tenant execution service. Inference
completion alone is not scientific validation; use the existing evaluation skill.
