# AtomWorks Studio in the conversation

This adapter packages the actual Studio v0.0.1 browser editor as a self-contained
MCP App. It reuses the upstream sequence strip, annotation forms, selection,
analysis, structure editing and undo. There is no second molecular editor to maintain.
The BioNeMo additions are compute registration/status, design notes, immutable
run review, upstream RFD4 sampling options, and result retrieval. Existing RFD4 skills supply setup and inference
instructions; this integration does not introduce an RFD4 skill.

## Upstream maintenance and building

The source of truth is [Studio v0.0.1](https://github.com/RosettaCommons/atomworks-studio/releases/tag/v0.0.1),
commit `4b419ebd327405035c8cf6ccde7f333d0878888e`. `build-upstream.mjs` checks
that revision and rejects tracked frontend modifications. It applies narrow
build-time adapters without changing upstream files: API transport, session events,
in-memory browser storage, inline CIF-parser WASM, and disabled PWA installation.
Mol* is the supported renderer. Patinae and optional MP4 encoding are excluded.
The build emits provenance, Studio's license, and notices for bundled dependencies.

Studio is public under its upstream license. The generated HTML, provenance,
Studio license and dependency notices are tracked in Git, both here and in the
synced aggregate plugin, so Git installations include the browser editor. Rebuild
from the pinned public source when changing the frontend, then run
`python scripts/plugin_sync.py --write` from the repository root. CI checks that
both copies contain identical assets and that provenance matches the build pin.
The adapter does not ship model weights; the CPU editor environment described
below is still required.

With Node 24, pnpm 11.25, Rust and wasm-pack installed, check out the pinned
public Studio commit. In that checkout, run `pnpm install --frozen-lockfile`
and `pnpm --dir packages/web build:core` to create `packages/web/src/wasm/`.
Then build this adapter:

```sh
cd integrations/atomworks-studio
pnpm install --frozen-lockfile --ignore-scripts
ATOMWORKS_STUDIO_SOURCE=/path/to/atomworks-studio pnpm build
RFD4_STUDIO_HOME=/path/to/state RFD4_PREVIEW_PORT=8769 python scripts/preview.py
```

The same generated `assets/studio-upstream.html` serves the local preview at
`http://127.0.0.1:8769` with the command above and the MCP app resource. No iframe or external JavaScript
is needed. The local CSP permits WASM compilation, not JavaScript eval. The
actual embedded host must also support WASM; local browser success is not proof
of host rendering. Requalify the host when updating Studio or its dependencies.

## CPU editor and self-contained compute

Compute appears in the top toolbar. Its panel shows registration, timestamped model
readiness, active runs, and chat-based setup. The first-run reminder is dismissible.
No provider lifecycle command runs from the app. Host messaging is capability
checked; the standalone preview provides a copyable request.

Set `RFD4_EDITOR_URL` to a CPU Studio loopback service independent of the GPU.
Optionally set `RFD4_EDITOR_PYTHON` to an already-prepared Studio Python 3.12
interpreter: the MCP server starts that CPU service once with upstream session
persistence and an OS lock. This never installs dependencies or starts GPU compute.
Prepare an isolated Python 3.12 environment with
`pip install "atomworks-studio==0.0.1"`, then use that environment's Python.
Gradio is optional and is not used by the MCP app. The embedded frontend is built separately above.
The old compute-bound Studio URL remains a compatibility fallback.

CIF and results-archive exports use the MCP host's advertised `downloadFile` capability and `ui/download-file` request. The host may ask the user to confirm. Unsupported, rejected or failed host downloads show an error; they never fall back to a sandboxed browser anchor or claim the file was saved. The standalone localhost preview retains normal browser downloads.

Drafts auto-save annotated CIF, notes, image notes, and sampling settings in the
adapter's private state directory. Saved drafts can be reopened explicitly after
reload. This avoids relying solely on upstream's two-hour session retention.
Session-specific compute selection is captured independently; changing another
session's selection does not retarget a draft or an existing job.

Opening a saved run input or result preserves the current draft, then restores
that run's notes and generation settings from its verified input plan. These
settings can be edited for a new run. Opening a run never reconnects compute.
Legacy runs without verifiable metadata show new-draft defaults explicitly and
clear unrelated notes and images. Unverified historical image notes are not
presented as belonging to the run; new plans bind image bytes by checksum.

BioNeMo owns `managed-v2/state.json` in its private state directory. It has no
external plugin, registry daemon, Python environment or authentication dependency.
Agent tools register existing local, SSH or Brev targets, list and inspect them,
and select a saved target for a Studio session. Registration resolves SSH identity
locally; inspection tests connectivity; readiness separately checks GPU, runtime
and weights. Credentials stay in SSH/Brev configuration. Local means the tool-server
machine. Brev creation remains in chat through the existing CLI/setup skills.

The catalog uses versioned JSON, atomic writes, restrictive permissions and process
locks. Legacy workspaces require an explicit offline upgrade into a separate
directory. Disable the old installation and stop its controllers and workers first;
finish or resolve outstanding runs and setup operations before upgrading. Run
`python scripts/upgrade_state.py --legacy /absolute/old-root --new /absolute/new-root --old-installation-disabled`
with the integration's Python environment, then point `RFD4_STUDIO_HOME` at the new
root. The helper refuses live writers and unresolved work, quarantines the old tree
read-only, retains its bytes and backups, and durably activates the imported tree.
An interrupted upgrade resumes with the same arguments; do not unfreeze the old
tree or restore backups over newer work. Backend and editor startup refuse legacy
roots and incompletely activated imports before writing workspace state. This fence
assumes the old installation remains disabled; it cannot constrain a same-user
program deliberately changing permissions or redirecting an old binary to the new
root. Migration never reads another plugin's registry. Old plans and jobs remain
unchanged and continue checking their pinned SSH identity. New plans require fresh
readiness evidence after migration. Changing a catalog target requires reselecting
and reviewing it; existing jobs remain attached to their original target.

A CPU-only directory containing drafts or editor sessions, with no saved compute,
setup records or jobs, remains compatible without a compute-state import. Opening
it preserves scientific files and starts with no compute selected. This does not
quarantine that directory; do not run old and new installations against it at the
same time. Any legacy compute or setup record requires the offline flow above.

Setup requests have durable IDs. Repeated clicks resume the same unfinished
request. The agent reports actual tool-derived steps through `update_compute_setup`;
reporting completion cannot itself mark a GPU ready. Brev creation still requires
the agent to reconcile existing machines before retrying an ambiguous CLI outcome.

The runtime uses the public BSD-3-Clause [RFD4-Proteina release](https://github.com/RosettaCommons/RFD4-Proteina), pinned to commit `c7c6cacbc617ab074b4e234448bed6581840949f`. Its Linux x86_64 Python 3.12.10 recipe installs hash-pinned CUDA 13.2 wheels, AtomWorks 3.0.4 and TMol 0.1.64. It does not install an OS compiler or optional refolding/search engines. The read-only prerequisite check requires glibc 2.28 or later and a CUDA 13 compatible driver; the later CUDA and representative generation checks determine actual readiness.

Setup downloads the anonymous Hugging Face bundle `nvidia/RFD4-Proteina` at revision `a06e2509c7033b010fc43614e9fd840303588502`: `config.json` and `model.safetensors`, 1,742,667,866 bytes total. Both file sizes and SHA-256 checksums, resolved configuration and a revision receipt must match. The bundle contains the autoencoder; no separate AE checkpoint is downloaded. Generation uses this local bundle with Hub offline mode, native inference and optional metrics disabled. Setup cannot mark a runtime ready without a successful representative GPU generation and a second integrity check.

Use a separate runtime root when moving from the development recipe to this public release. Setup refuses to replace a checkout at another revision; existing runs and their inputs are retained. Previously issued run reviews require fresh readiness and review against the new runtime. Anonymous source/bundle access, wheel resolution, CPU tensor loading and configuration composition have been verified. A real Linux install and GPU generation remain qualification gates; see `TESTING-2026-10-20.md`.

## Compute user flow

Each machine belongs to one installation and canonical controller state directory.
After registration and verified access, chat reviews `prepare_executor_claim` and
requests approval for `execute_executor_claim`. This uses noninteractive administrator
access only to establish a protected machine-wide ownership receipt; it installs
nothing and starts no model. Ordinary ownership checks do not need sudo. Without
administrator access, ask the machine administrator to complete the reviewed claim;
do not request passwords in chat or fall back to a user-home ownership file.

The receipt survives disconnect, restart and completed runs. A second installation,
copied state directory, missing receipt or incomplete publication cannot authorize
setup, generation, recovery writes or stop. An uncertain claim is observed rather
than repeated; an already-present matching receipt with incomplete publication has
a separate approved, noncreating confirmation. Ownership transfer and state-directory
relocation are unsupported. Keep an already-owned state root unchanged during plugin
upgrades. Legacy imports claim only after the offline upgrade described above.

A stopped Brev machine needs its previously verified local receipt bound to the
immutable organization/instance identity before it can start. A newly registered
stopped machine cannot acquire ownership through its name or provider inventory.
After start, live identity, protected ownership and runtime checks are still required.
SSH and Brev aliases share the physical machine owner; each saved connection must
have its own verified local association. The root receipt binds executor/root/physical
identity; the immutable Brev tuple is stored in the local association.

The editor shows the target name, transport, registration/readiness state, GPU
information and check time. Registration is not readiness; checks expire after
15 minutes. A readiness check verifies committed ownership, shell/GPU access, the pinned
runtime and checkpoint digests. Editor availability is separate. Setup has a separate
representative inference check; an ordinary readiness check runs no inference.

Runs retain their original machine and reviewed input after disconnect. Check status
shows the backend's explanation, including unresolved transport or worker outcomes.
For a run that remains queued because its controller stopped, chat can explicitly
call `recover_queued_rfd4_job` with the original accepted plan checksum. The host
must approve this action because it can perform the first GPU launch. It continues
the same job and reservation; it does not create another design. Possibly submitted
or legacy jobs without durable dispatch proof cannot be replayed through recovery.

Reviewed scripts, helper modules and input are frozen before acceptance. Each upload
uses a unique attempt directory. A checksum-bound isolated helper copies reviewed
bytes into separate immutable payload inodes before launch; surviving SSH/SCP uploads
cannot overwrite them. Logs, output and cancellation/package receipts remain outside
that payload. Publication alone never authorizes execution or releases a reservation.

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

Brev execution and file transfers use direct SSH/SCP, never `brev exec` or
`brev copy`: those CLI commands can implicitly start a stopped VM. Saved Brev
access must first be refreshed explicitly in chat with `refresh_compute_access`
for a connect operation. That tool verifies the saved organization and immutable
instance before and after `brev refresh`, then checks physical identity over
strict SSH. It can update local SSH/key/helper configuration, but never starts a
machine or enrolls a host key. The Brev organization must already be selected.
An unknown or changed host key blocks connection and requires independent key
verification; scanning a key alone is not verification. Existing runs retain
their original access snapshot. A changed endpoint requires explicit recovery,
not silent rebinding of a run. Access refresh invalidates previous readiness and
run reviews; check compute and review again afterward. If the controller crashes,
use `recover_compute_access` to close the unaccepted attempt after its process
lease is free, then request a new refresh. Recovery never repeats the CLI command.

`register_rfd4_compute` is an agent-only tool. `check_compute` and
`get_compute_status` are available to the app. Registration doesn't install,
provision, authenticate, or declare success. Switching the target invalidates
previous run approvals. Existing jobs retain their own immutable target configuration and remain inspectable after a target switch. New submissions recheck readiness; retrying a previously submitted plan returns the existing job.

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
  "weight_paths": ["/srv/rfd4/model-bundle/config.json", "/srv/rfd4/model-bundle/model.safetensors"]
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
python scripts/stage_rfd4_plugin.py --output /local/plugin
```

The public upstream setup, annotation and generation skills are already synchronized
into this bundle with their BSD licenses. No model weights, private source or local
state are included. Commands in upstream references expect the model checkout root.

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

### Managed Brev provisioning contract

The managed adapter uses the organization-scoped catalog and control-plane endpoints used by Brev CLI v0.6.332 (source commit `6b111e1f041d354d682541cc489375431f195fcf`). The old `brev start --gpu` path rejects current catalog types; `brev create` uses ambient organization state. Neither is used for managed creation. Authentication remains the executor's existing Brev login; credentials never enter reviews or exported plans.

Call `list_compute_creation_options` with the explicit organization ID, then `prepare_compute_creation` with an exact returned instance type. The initial recipe accepts one stoppable A100 80 GB x86_64 VM, with 120 GiB storage and no Jupyter installation. The review includes provider account reference, location, hardware, catalog base price and available storage rates; these are estimates, not a total billing quote. Execution rechecks that specification and requires a fresh review if it changes. No automatic substitution or setup follows creation.

Power requests use an immutable provider ID, verify its organization through the provider, and never use CLI ambient organization. Cloud requests are not automatically retried. Lost acknowledgments retain the original operation for reconciliation. These interfaces remain under qualification; local tests are not proof of live provisioning, safe shutdown or installed-host acceptance.

Managed stop needs noninteractive privileged process visibility (`sudo -n`) on the dedicated Linux executor. The probe performs read-only inspection and does not install or change sudo policy. It refuses restricted/container process views, GPU work, held execution locks, user workloads and unrecognized processes. Only the main processes of a short set of known OS services may be exempted after checking their system control group and root-owned, non-writable executable. Child processes are not exempted. A machine with an unrecognized provider agent can therefore remain blocked until its supported-image behavior is qualified; do not bypass this by disabling the check. The lock path is expanded in the original executor user's shell before privilege elevation.

The upstream Close structure control is hidden in the embedded app: it deletes
the editor session and reloads its page, which cannot navigate the MCP resource.
Use File → Open CIF to replace the structure; the current draft is saved first.
The app preserves upstream inferred/custom import settings and temporary-session
cleanup without adding arbitrary HTTP or filesystem access.

Before changing the upstream pin, run
`ATOMWORKS_STUDIO_SOURCE=/checkout node test-public-import.mjs` from this directory.
It compiles the actual adapted upstream file controller and checks delayed
inspection, an expired import dialog, and a successful subsequent import. These
API/DOM fault fixtures supplement browser checks; they do not execute a model.
