# AtomWorks Studio in the conversation

This adapter packages the actual Studio v0.1.0 browser editor as a self-contained
MCP App. It reuses the upstream sequence strip, annotation forms, selection,
analysis, structure editing and undo. There is no second molecular editor to maintain.
The BioNeMo additions are compute registration/status, design notes, immutable
run review, upstream RFD4 sampling options, and result retrieval. Existing RFD4 skills supply setup and inference
instructions; this integration does not introduce an RFD4 skill.

## Upstream maintenance and building

The source of truth is [Studio v0.1.0](https://github.com/RosettaCommons/atomworks-studio/releases/tag/v0.1.0),
commit `648cfe3905d1f1893c0c37d2cc4b8eea942a5616`. `build-upstream.mjs` checks
that revision and rejects tracked frontend modifications. It applies narrow
build-time adapters without changing upstream files: API transport, session events,
in-memory browser storage, inline CIF-parser WASM, and disabled PWA installation.
Mol* is the supported renderer. Patinae and optional MP4 encoding are excluded.
The build emits provenance, Studio's license, and notices for bundled dependencies.

The upstream repository is private ahead of launch. Generated upstream assets
are ignored and remain local; an unbuilt checkout cannot open the editor. The
previous custom editor has been removed. For a release artifact, build against
an authorized checkout and include the generated assets and licenses. Public
redistribution should wait for the upstream launch.

With Node 24 and pnpm 11.25 installed, first build Studio's CIF parser using its
upstream build instructions (or use matching compiled artifacts from your authorized
v0.1.0 build), so `packages/web/src/wasm/` exists. Then:

```sh
cd integrations/atomworks-studio
pnpm install --frozen-lockfile --ignore-scripts
ATOMWORKS_STUDIO_SOURCE=/authorized/atomworks-studio pnpm build
RFD4_STUDIO_HOME=/path/to/state python scripts/preview.py
```

The same generated `assets/studio-upstream.html` serves the local preview at
`http://127.0.0.1:8766` and the MCP app resource. No iframe or external JavaScript
is needed. The local CSP permits WASM compilation, not JavaScript eval. The
actual embedded host must also support WASM; local browser success is not proof
of host rendering. Requalify the host when updating Studio or its dependencies.

## Compute user flow

The editor shows the target name, transport, registration/readiness state, GPU
information and check time. Registration is not readiness; checks expire after
15 minutes. A readiness check establishes shell/GPU access, the pinned runtime
entrypoint/revision, presence of registered weight files, and Studio API access.
It does not establish that weights are compatible or that inference will succeed.

**Set up compute in chat** sends a user message through `ui/message`. It does
not run commands or provision infrastructure. In the standalone development
preview it shows the equivalent text to copy into chat. The agent uses existing
RFD4 setup and Brev CLI skills, then registers and checks the selected target:

- `local`: a Linux GPU machine hosting the tool server; it need not be the
  computer displaying ChatGPT.
- `ssh`: a host already reachable with an SSH config alias or `user@host`, using
  noninteractive SSH and the user's normal host-key verification.
- `brev`: an existing Brev instance bound to its immutable ID in the active org.
  New-instance provisioning belongs in chat, with machine and cost review.

`register_rfd4_compute` is an agent-only tool. `check_compute` and
`get_compute_status` are available to the app. Registration doesn't install,
provision, authenticate, or declare success. Switching the target invalidates
previous run approvals. Existing jobs require their original target configuration.

The runtime layout is `RUNTIME_ROOT/model/.venv/bin/rfd4-generate`, with the model
checkout revision in `RUNTIME_ROOT/model-revision`. The pinned model revision is
in `scripts/core.py`. Studio is independently served on a loopback HTTP port;
forward remote Studio to that port. SSH credentials and Brev authentication stay
on the tool-server machine, never in browser storage.

Example existing SSH registration (after setup):

```json
{
  "kind": "ssh",
  "name": "lab-gpu",
  "ssh_host": "lab-gpu",
  "runtime_root": "/srv/rfd4",
  "studio_url": "http://127.0.0.1:18764",
  "weight_paths": ["/srv/weights/actual-checkpoint.ckpt"]
}
```

The old Brev `config.json` format still works. Keep state outside the repository
using `RFD4_STUDIO_HOME`; the default is `~/.local/share/bionemo-rfd4`.

## Scientific and execution boundaries

Studio owns molecular state and validation. The tool bridge allowlists editor
routes and accepts neither arbitrary URLs nor execution commands. Studio's
revision and confirmation behavior is preserved. Image/text notes accompany the
input; they are not automatically converted into model constraints.

Review freezes the exported CIF, checksum, seed, count, thinking preset, backbone/latent noise and exact target. Generate
sends that review to the conversation for agent execution. Jobs use detached
workers and durable records. Ambiguous submission is never automatically retried.
This is a single-user adapter. Inference completion is not scientific validation;
use the existing upstream evaluation skill.

Stage the local plugin with the existing model skills unchanged:

```sh
python scripts/plugin_sync.py --write
python scripts/stage_rfd4_plugin.py --model-repo /authorized/RFD4 --output /local/plugin
```

Restricted model docs and skills stay in that local bundle. No model weights are
included. Keep upstream licenses and access requirements separate from this adapter.

## Verification

```sh
python -m unittest discover -s tests -p 'test_atomworks_*.py'
python scripts/plugin_sync.py --check
```

The generated-HTML test is skipped when authorized upstream assets have not been
built. CI checks the bridge/compute/protocol contracts without private source.
Local qualification additionally covers the real upstream bundle, demo loading,
selection, annotation, undo and compute status. Local and SSH execution transports
have unit coverage; live inference has only been exercised on the configured Brev
machine. Patinae, MP4, trajectory playback and host download behavior are not
qualified in this embedded build.

## Recorded-demo qualification

The adapter supports the recorded binder workflow: choose an upstream example,
realize its variable-length segment, review thinking (low/medium/high), backbone
noise and sequence/side-chain latent noise, submit through chat, and inspect the
result using upstream Style and Analyze controls. Noise defaults are 0.3/0.1;
Hydra mappings are documented in `scripts/generation.py`. These small host controls
mirror the upstream RFD4 generation provider; no sampling algorithm lives here.

Runs offers saved Input / Design selectors and Download all (ZIP). Studio's own
Save CIF exports the active structure and retains upstream validation prompts.
Switching run structures uses Studio's existing file-opening lifecycle, clearing
old selections, trajectories and contact visuals. Run files are loaded from saved
artifacts, not the current mutable editor document.

2026-10-16: HTML replay on the existing A100 completed a single binder design,
reopened 1,453 atoms, and displayed 57 inter-chain contacts using upstream analysis.
The input realization sampled 72 residues (the recording sampled 85); this is the
same variable-length operation, not a claim of identical generated coordinates.
The ZIP was downloaded and its input/design contents and CRC verified. Individual
CIF export was downloaded and preserved Studio's missing-atoms confirmation. These are execution and
UI checks, not scientific validation of the generated binder.

For manual embedded-host acceptance, open Studio from the plugin in chat, repeat
this workflow, verify that Generate in chat delivers the exact reviewed plan,
and check Save CIF / Download all in the host sandbox. Those host-specific checks
remain manual; the HTML preview and MCP app use the same generated frontend.
Set `RFD4_PREVIEW_PORT` to use a different localhost port during development.
