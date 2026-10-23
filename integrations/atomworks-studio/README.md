# RFD4-Proteina Studio

An embedded MCP App for BioNeMo Agent Toolkit. It packages AtomWorks Studio's
existing molecular editor with a preloaded PD-L1 example, 3D annotations, saved
drafts, reviewed RFD4 generation, results and chat-led execution on a named SSH host.
Image notes accompany the input; they do not become model constraints automatically.
The app uses a bundled frontend rather than an HTTP iframe. No NGS plugin is required.

## Install and open

Install the toolkit plugin from this repository's `skills/bionemo-agent-toolkit`
directory. Its `.mcp.json` starts separate app and agent servers using `uv` and
Python 3.12. The launcher installs the pinned MCP and CPU editor requirements
through `uv`; the first launch needs network access and may take longer. Opening
Studio automatically selects and saves a local loopback address and starts the
CPU editor. No editor environment variables, GPU, model weights or remote compute
registration are needed to view and annotate the preloaded example. Gradio is
not required. Later launches reuse the saved editor address and session store.

For custom installations, `RFD4_EDITOR_URL` or `editor.json` can select an existing
compatible CPU editor. `RFD4_EDITOR_PYTHON` can select a separate editor environment
prepared using `editor-requirements.txt`. `RFD4_STUDIO_PYTHON` bypasses `uv` and must
provide `requirements.txt` plus `editor-requirements.txt` (unless a separate editor
is configured). The editor runs locally and starts again on demand after a host
restart. `RFD4_STUDIO_HOME` selects persistent state (default
`~/.local/share/bionemo-rfd4`). Credentials stay in SSH/Brev configuration.

Ask chat to open **RFD4-Proteina Studio**, then:

1. Load the PD-L1 example, realize its editable segment and annotate residues.
2. Choose thinking, design count, seed and optional sampling settings. Review
   freezes the annotated CIF and settings without needing compute.
3. Choose **Generate in chat**. Chat reads the saved request and asks for an SSH
   host when the destination is unclear, verifies readiness, and submits it.
4. Open the completed design from **Runs**. Use **File → Save CIF** or the run's
   ZIP export. When Codex cannot download directly, chat retrieves the verified
   local export and returns a file link.

Drafts preserve annotations, notes and settings. Opening a result saves the current
draft. The toolbar reports the run's machine and job state. Unsupported chat
handoff preserves the request and explains how to continue; it never reports a
successful submission.

## Compute and runtime

Compute is user-managed. The plugin checks a named SSH host, submits immutable
requests, checks jobs and collects results/logs. It does not provision, start,
stop or own machines. The `rfd4-studio-chat` skill guides host choice and setup.
If Brev CLI is installed, chat can offer existing or new compute through that CLI.
Creation requires a price and shutdown policy reviewed in chat. Existing machines
stay running unless separately requested. No Brev installation, driver upgrade or
reboot happens silently.

SSH host and TLS verification stay enabled. Brev first-use trust can be approved
in chat; changed keys are refused. Launch validation, upload and acknowledgement
happen inside the active tool call. Only remote execution is detached. Durable
receipts prevent duplicate inference after retries or interruption. Closing chat
does not stop remote work or billing; resume in chat to collect and complete any
authorized shutdown. Verified collected results remain available after stopping.

Public model source is pinned to `RosettaCommons/RFD4-Proteina` at
`c7c6cacbc617ab074b4e234448bed6581840949f`; the Hugging Face bundle is pinned at
`a06e2509c7033b010fc43614e9fd840303588502`. `scripts/runtime_recipe.json` and
`runtime_dependencies.lock` define the verified Python 3.12.10/Linux x86_64/CUDA
13.2 runtime, AtomWorks 3.0.4 and TMol 0.1.64. Setup checks source, dependency and
bundle hashes. Generation uses the local bundle in Hub offline mode. The public
setup path requires no APT/compiler installation. Use a separate runtime root for
this release; setup refuses to replace a different checkout revision. Model weights,
private source, credentials, local state and evaluation bundles are not packaged.

Fresh Brev images may have an older NVIDIA driver even when the machine has an
A100. The preliminary setup check requires driver major version 580 or newer for
this pinned runtime; passing that check alone does not establish readiness. If it
fails, ask chat to inspect the selected machine's OS and `nvidia-smi` output.
Choose a compatible provider image, or review a driver upgrade on that machine
using NVIDIA's official packages. A driver upgrade may require a reboot and must
wait until active work is finished. The plugin does not silently upgrade drivers,
reboot, or create a replacement machine. After an approved upgrade/reboot,
reconnect the same machine, repeat setup, and require all runtime checks plus the
setup smoke test to pass before generating a design. The fresh A100 UAT image
required a manual upgrade from 565.57.01 to 580.196.07; fresh provisioning is not
qualified as an unattended workflow.

Existing drafts, annotations, inputs and results are preserved in place. Legacy
job records retain their original reader and are never replayed through the new
submission path. Legacy compute records are suggestions only, not active selections.

## Build and package

Frontend source is public AtomWorks Studio v0.0.1, commit
`4b419ebd327405035c8cf6ccde7f333d0878888e`. The CPU editor uses
`atomworks-studio==0.0.1`. Narrow build-time adapters change transport, session
coordination, storage and inline WASM without editing upstream source. Mol* is the
renderer; Patinae, PWA installation and optional MP4 encoding are excluded.

With Node 24, pnpm 11.25, Rust and wasm-pack, check out that Studio revision and
run `pnpm install --frozen-lockfile` and `pnpm --dir packages/web build:core` there.
Then, from this integration directory:

```sh
pnpm install --frozen-lockfile --ignore-scripts
ATOMWORKS_STUDIO_SOURCE=/path/to/atomworks-studio pnpm build
ATOMWORKS_STUDIO_SOURCE=/path/to/atomworks-studio node test-public-import.mjs
RFD4_STUDIO_HOME=/path/to/dev-state RFD4_PREVIEW_PORT=8769 python scripts/preview.py
```

The tracked HTML, provenance, Studio license and dependency notices make Git
installations self-contained. The installed payload includes only the server,
Python helpers/profiles/locks, runtime requirements, this README and bundled
assets/attribution. Frontend source, build tooling and the localhost preview stay
in the development integration directory. From the repository root:

```sh
python scripts/plugin_sync.py --write
python scripts/plugin_sync.py --check
python scripts/stage_rfd4_plugin.py --output /absolute/path/to/new-plugin
python -m unittest discover -s tests -p 'test_atomworks_*.py'
python -m unittest discover -s tests -p test_studio_distribution.py
```

Canonical RFD4 skills retain their CC-BY-4.0 text and BSD-3-Clause helper attribution;
see the root NOTICE and canonical skill README. The header embeds NVIDIA's official
transparent green-eye/white-wordmark SVG; NVIDIA branding remains subject to trademark
terms (source attribution in the development integration's `host/BRANDING.md`). Build provenance and third-party notices must
remain with the bundled viewer.

The Python adapter is organized by responsibility: `service.py` keeps editor,
drafts and result operations; `design_request.py` freezes requests;
`chat_execution.py` handles named-host submission and collection; `ssh_job.py`
provides remote execution receipts. `registry.py` retains shared SSH transport,
and `brev_provider.py` only reads provider identity for a named Brev target.
There is no machine registry, provisioning service, ownership claim or local
submission worker. Authored source/test files stay below 1,000 lines; generated
viewer assets and dependency locks are retained intact.

## Validation scope

The chat-led path has completed one public PD-L1 design on the existing Brev
A100, recovered it from a fresh client process, collected its results and logs,
and opened the 1,454-atom result in the localhost editor. The existing machine
remains running. This is source/localhost evidence, not an installed-plugin pass.

The current release still requires an installed-plugin generation, chat handoff
and export pass. A separate new-machine UAT is in progress. Earlier installed
release results do not qualify this changed submission path. The broad runtime
profile remains `candidate_not_qualified`; ChatGPT.com deployment is separately
unqualified. Test evidence and outstanding checks are recorded in PR #58.
Inference success is not scientific validation; use the canonical evaluation skills.
