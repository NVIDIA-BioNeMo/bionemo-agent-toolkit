# Embedded AtomWorks Studio adapter

This adds a conversation-embedded MCP App to BioNeMo Agent Toolkit, following the NGS
Workbench separation between an app surface and agent execution tools. It does
not introduce an RFD4 skill. Use the existing RFD4-Proteína skills from your
authorized model checkout for setup, annotated CIFs, generation, and evaluation.

Ask Codex to “open RFD4 Studio” to display the tool card in the conversation.
It has no global full-page entry point; expand the card beside the chat if desired.

The app bundles Mol* and its CSS directly into one HTML resource. There is no
iframe, external script, CDN, or browser connection to Studio. A small transport
adapter uses MCP tools in the embedded app and a loopback tool endpoint during
local development. Both serve the identical generated HTML.

The preloaded PD-L1 example comes from the existing Studio deployment. Mol* picks
source atom indices; Studio expands them to residues or chains and applies the
conditions at the displayed document revision. This preserves Studio's annotation
semantics rather than reimplementing the RFD4 condition format. Supported edits
in this preview are hotspots, keeping sequence, and keeping coordinates. Text
and PNG image notes are saved alongside the input, not interpreted as conditions.

Review freezes a validated CIF, checksum, seed, design count, and Brev target.
The embedded app hands execution to the conversation's native approval flow.
The local preview asks for confirmation before calling the same execution service.

## Local setup

The tested Studio release is [v0.1.0](https://github.com/RosettaCommons/atomworks-studio/releases/tag/v0.1.0),
commit `648cfe3905d1f1893c0c37d2cc4b8eea942a5616`. Studio supplies a full
browser/VS Code editor and a PyMOL plugin. This adapter uses its annotation API
with a smaller custom Mol* interface; it does not bundle the complete Studio UI.
The release packages Studio separately from model inference. Repository access
is required until its public launch.

Use the upstream setup skill to prepare an existing Brev GPU instance and
AtomWorks Studio. This adapter does not provision a machine or download weights.
The model checkout must match the revision in `scripts/core.py`; its installed
entrypoint is `REMOTE_ROOT/model/.venv/bin/rfd4-generate`. Write the checkout commit
to `REMOTE_ROOT/model-revision`. Forward Studio's API to local loopback, for example
port 18764. The Python adapter accesses that API; the viewer does not embed or
fetch its website, and no frame-ancestor exceptions are needed.

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

## Build and preview

With Node.js and pnpm installed:

```sh
cd integrations/atomworks-studio
pnpm install --frozen-lockfile --ignore-scripts
pnpm build
RFD4_STUDIO_HOME=/path/to/state python scripts/preview.py
```

Open `http://127.0.0.1:8766`. The preview enforces `frame-src 'none'`, disallows
external scripts and eval, and authenticates its loopback tool calls with a
per-process token. The generated HTML is committed for plugin runtime use.
`THIRD_PARTY_NOTICES.txt` contains the licenses of bundled dependencies.

## Verification and limits

```sh
python -m unittest discover -s tests -p 'test_atomworks_*.py'
python scripts/plugin_sync.py --check
```

The Studio API must provide sessions, selection resolution, conditions, and
export. Its server owns annotation state. Jobs use a detached local submission
worker and durable records. Ambiguous submissions require inspection and are
never retried automatically. A stopped worker before remote launch can leave a
queued record; inspect `worker.log` before preparing another plan. This is a
single-user local integration, not a multi-tenant service. Inference completion
alone is not scientific validation; use the existing evaluation skill.
