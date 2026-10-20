# RFD4-Proteina Studio

An embedded MCP App for BioNeMo Agent Toolkit. It packages AtomWorks Studio's
existing molecular editor with a preloaded PD-L1 example, 3D annotations, saved
drafts, reviewed RFD4 generation, results and self-contained compute management.
Image notes accompany the input; they do not become model constraints automatically.
The app uses a bundled frontend rather than an HTTP iframe. No NGS plugin is required.

## Install and open

Install the toolkit plugin from this repository's `skills/bionemo-agent-toolkit`
directory. Its `.mcp.json` starts separate app and agent servers using `uv` and
Python 3.12. Prepare an independent CPU editor environment:

```sh
uv venv --python 3.12 /absolute/path/to/editor-env
uv pip install --python /absolute/path/to/editor-env/bin/python -r integrations/atomworks-studio/editor-requirements.txt
```

Set `RFD4_EDITOR_PYTHON` to that environment's Python before starting the host.
The server starts the editor service with session persistence and an OS lock;
this does not install dependencies or start GPU compute. Alternatively, set
`RFD4_EDITOR_URL` to an existing CPU Studio loopback service. Gradio is not required.
`RFD4_STUDIO_PYTHON` optionally selects an already prepared MCP environment using
`requirements.txt`. `RFD4_STUDIO_HOME` selects persistent state (default
`~/.local/share/bionemo-rfd4`). Credentials stay in SSH/Brev configuration.

Ask chat to open **RFD4-Proteina Studio**, then:

1. Load the PD-L1 example, realize its editable segment and annotate residues.
2. Open **Compute**, select an existing machine and click **Connect**. The app
   checks connectivity, GPU, pinned runtime and weights before displaying Ready.
   If no machine is registered, **Manage in chat** requests setup assistance.
3. Choose thinking, design count, seed and optional sampling settings. Review
   freezes the annotated CIF and settings; approve execution in chat.
4. Open the completed design from **Runs**. Use **File → Save CIF** or the run's
   ZIP export. When Codex cannot download directly, chat retrieves the verified
   local export and returns a file link.

Drafts preserve annotations, notes and settings. Disconnect detaches the session
without stopping its machine or jobs; reconnect reuses the saved target. Opening
a result saves the current draft and does not reconnect compute. Unsupported host
messaging or failed exports produce an error instead of silently succeeding.

## Compute and runtime

Agent tools can register local Linux GPU, existing SSH and Brev targets. Registration
is separate from connection and model readiness; readiness expires after 15 minutes.
Switching targets invalidates run reviews, while existing jobs retain their original
machine and frozen inputs. Ambiguous dispatch is never automatically repeated.

Brev uses immutable organization/instance identity and direct SSH/SCP. Explicit
access refresh can remember a first-use key with OpenSSH `accept-new`; changed
keys are refused. Subsequent execution/copies and generic SSH use strict checking.
Refresh does not start or provision machines. Dedicated Brev setup/design uses
`dedicated_brev_user` scope without a privileged ownership marker; existing protected
owners and historical ownership-bound jobs retain their checks. Existing creation,
Start/Stop, setup and queued-job recovery remain agent-only reviewed operations.
Stop requires its existing activity/ownership checks; do not bypass a refusal.

Public model source is pinned to `RosettaCommons/RFD4-Proteina` at
`c7c6cacbc617ab074b4e234448bed6581840949f`; the Hugging Face bundle is pinned at
`a06e2509c7033b010fc43614e9fd840303588502`. `scripts/runtime_recipe.json` and
`runtime_dependencies.lock` define the verified Python 3.12.10/Linux x86_64/CUDA
13.2 runtime, AtomWorks 3.0.4 and TMol 0.1.64. Setup checks source, dependency and
bundle hashes. Generation uses the local bundle in Hub offline mode. The public
setup path requires no APT/compiler installation. Use a separate runtime root for
this release; setup refuses to replace a different checkout revision. Model weights,
private source, credentials, local state and evaluation bundles are not packaged.

Historical workspaces require the existing offline upgrade helper. Disable the old
installation and stop its controllers/workers; finish or resolve outstanding work.
Run `python scripts/upgrade_state.py --legacy /absolute/old-root --new /absolute/new-root --old-installation-disabled`,
then point `RFD4_STUDIO_HOME` to the new root. The helper preserves old bytes and
backups and refuses live writers/unresolved work. Resume an interrupted upgrade
with the same arguments; never restore backups over newer state. Existing queued
jobs require explicit recovery with their original accepted plan checksum.

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

## Validation scope

Real Codex testing passed on the existing Brev A100: connect/readiness,
disconnect/reconnect, annotation/draft preservation, one annotated public PD-L1
design, result viewing and CIF/ZIP exports. The result contained 1,403 atoms with
finite coordinates. A separate short-monomer setup smoke passed all nine checks
before and after inference. A real expired Brev login blocked readiness and normal
CLI sign-in restored it. Other unavailable-machine/dependency/stale-response cases
have regression coverage; isolated OpenSSH testing verifies first-use persistence
and changed-key refusal. CI covers Python/JavaScript contracts, packaging, upstream
imports and canonical RFD4 helpers.

This establishes the tested Codex/A100 workflow, not every GPU, preset, provisioning
or shutdown path. The broad runtime profile remains `candidate_not_qualified`;
ChatGPT.com deployment is separately unqualified. Legacy privileged prerequisite
qualification applies only to its pinned Ubuntu/A100 profile, not other images.
Recheck the actual embedded host after frontend/host changes: localhost rendering
alone does not prove WASM, chat messaging or download support in that host.
Inference success is not scientific validation; use the canonical evaluation skills.
