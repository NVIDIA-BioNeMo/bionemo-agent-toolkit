let seq = 0, activeSession = null, plan = null, imageNote = null, editEpoch = 0;
let hostCapabilities = {}, computeState = null, saving = Promise.resolve(), draftTimer, polling = false, setupPending = false, hintDismissed = false;
const pending = /* @__PURE__ */ new Map(), local = Boolean(window.localToken);
const storage = { data: /* @__PURE__ */ new Map(), getItem(k) {
  return this.data.get(k) ?? null;
}, setItem(k, v) {
  this.data.set(k, String(v));
}, removeItem(k) {
  this.data.delete(k);
} };
function rpc(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => {
      pending.delete(id);
      reject(Error("Host response timed out. Check status before retrying."));
    }, 12e4);
    pending.set(id, { resolve, reject, timer });
    parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
  });
}
addEventListener("message", (e) => {
  if (e.source !== parent || e.data?.jsonrpc !== "2.0") return;
  const p = pending.get(e.data.id);
  if (p) {
    clearTimeout(p.timer);
    pending.delete(e.data.id);
    e.data.error ? p.reject(Error(e.data.error.message)) : p.resolve(e.data.result);
  }
});
async function tool(name, args = {}) {
  const r = local ? await fetch("/api/tools", { method: "POST", headers: { "Content-Type": "application/json", "X-RFD4-Token": window.localToken }, body: JSON.stringify({ name, arguments: args }) }).then((r2) => r2.json()) : await rpc("tools/call", { name, arguments: args });
  if (r.isError) throw Error(r.content?.find((x) => x.type === "text")?.text || r.error || "Tool failed");
  return r.structuredContent ?? JSON.parse(r.content?.find((x) => x.type === "text")?.text || "{}");
}
async function studioFetch(path, init = {}) {
  if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const args = { method: init.method || "GET", path };
  if (init.body instanceof FormData) {
    args.form = [];
    for (const [name, value2] of init.body) args.form.push({ name, value: typeof value2 === "string" ? value2 : await value2.text(), filename: typeof value2 === "string" ? void 0 : value2.name });
  } else if (init.body) args.body = JSON.parse(init.body);
  const value = await tool("studio_request", args);
  if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  return new Response(value.text, { status: value.status, headers: { "Content-Type": value.content_type } });
}
function studioEvent(type, session) {
  activeSession = session;
  if (type === "ready") { document.getElementById("rfd-chat-prompt").hidden = true; message(""); }
  if (type === "changed" || type === "ready") { invalidate(); queueDraft(); }
  if (type === "ready") void compute().catch(e => message(e.message));
  document.getElementById("rfd-review").disabled = !session;
}
function invalidate() {
  editEpoch++;
  plan = null;
  document.getElementById("rfd-plan").hidden = true;
}
function message(text) {
  document.getElementById("rfd-message").textContent = text;
}
async function ask(text) {
  if (local || !hostCapabilities.message) {
    const box = document.getElementById("rfd-chat-prompt");
    box.hidden = false;
    box.value = text;
    box.focus();
    box.select();
    message("Copy this request into chat to continue setup. This preview cannot send a message to the conversation.");
    return false;
  }
  const result = await rpc("ui/message", { role: "user", content: [{ type: "text", text }] });
  if (result?.isError) throw Error("Host did not accept the chat request");
  message("Request sent to the conversation. Setup will continue there.");
  return true;
}
function action(id, fn) {
  document.getElementById(id).onclick = async () => {
    const button = document.getElementById(id);
    button.disabled = true;
    try {
      await fn();
    } catch (e) {
      message(e.message);
    } finally {
      button.disabled = false;
    }
  };
}
function settings() {
  return {samples: Number(document.getElementById('rfd-samples').value), seed: Number(document.getElementById('rfd-seed').value), generation: {thinking: document.querySelector('input[name="thinking"]:checked').value, backbone_noise: Number(document.getElementById('rfd-backbone-noise').value), latent_noise: Number(document.getElementById('rfd-latent-noise').value)}};
}
function queueDraft() {
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => saveDraft().catch(e => { document.getElementById('rfd-draft-status').textContent = 'Draft not saved: '+e.message; }), 1500);
}
async function saveDraft() {
  if (!activeSession) return null;
  const args = {session_id: activeSession, note: document.getElementById('rfd-note').value, image_base64: imageNote, settings: settings()};
  // Serialize exports so an older response cannot replace the newest draft.
  saving = saving.catch(() => {}).then(() => tool('save_draft', args));
  const draft = await saving;
  document.getElementById('rfd-draft-status').textContent = 'Draft saved';
  return draft;
}
function renderCompute(c) {
  const labels = {unregistered:'Not connected', registered:'Check needed', ready:'Ready', needs_setup:'Action needed', disconnected:'Disconnected', checking:'Checking', setting_up:'Setting up'};
  const label = c.active_jobs?.length && c.state === 'ready' ? 'Running' : labels[c.state] || 'Check needed';
  document.getElementById('rfd-compute-label').textContent = label;
  document.getElementById('rfd-compute-box').dataset.state = c.state;
  document.getElementById('rfd-compute-name').textContent = c.name || 'Connect a GPU to generate designs';
  document.getElementById('rfd-compute-gpu').textContent = (c.gpu || '').split('\n').map(line => line.split(',').slice(0,2).join(' · ')).join('\n');
  document.getElementById('rfd-compute-route').textContent = c.name ? `${c.kind === 'local' ? 'On the tool-server computer' : 'Connected through '+c.kind.toUpperCase()} · ${c.source || 'RFD4'}` : 'You can keep editing while compute is set up.';
  document.getElementById('rfd-compute-detail').textContent = c.detail || '';
  document.getElementById('rfd-compute-checked').textContent = c.checked_at ? 'Last checked '+new Date(c.checked_at).toLocaleString() : '';
  document.getElementById('rfd-setup').textContent = c.state === 'unregistered' ? 'Set up in chat' : ['needs_setup','disconnected'].includes(c.state) ? 'Continue setup in chat' : 'Manage in chat';
  document.getElementById('rfd-check').hidden = !c.name;
  document.getElementById('rfd-compute-hint').hidden = hintDismissed || c.state !== 'unregistered';
  document.getElementById('rfd-setup-progress').textContent = c.setup && c.setup.stage !== 'complete' ? c.setup.detail + ' · Updated '+new Date(c.setup.updated_at).toLocaleTimeString() : '';
  document.getElementById('rfd-compute-running').textContent = c.active_jobs?.length ? `${c.active_jobs.length} active run(s). Closing Studio does not stop them.` : c.name ? 'Completing a run does not stop its machine.' : '';
}
async function compute(check = false) {
  if (polling) return;
  polling = true;
  const session = activeSession;
  if (check) renderCompute({...computeState, state:'checking'});
  try {
    const c = await tool(check ? 'check_compute' : 'get_compute_status', {session_id: session});
    if (session !== activeSession) return;
    if (computeState?.fingerprint && computeState.fingerprint !== c.fingerprint) invalidate();
    computeState = c; renderCompute(c);
  } catch(e) {
    renderCompute({...computeState, state:'disconnected', detail:e.message});
  } finally { polling = false; }
}
async function setupCompute(targetId = null) {
  if (setupPending) return;
  setupPending = true;
  try {
    clearTimeout(draftTimer);
    const draft = await saveDraft();
    const setup = await tool('begin_compute_setup', {session_id:activeSession});
    const context = activeSession ? `For Studio session_id ${activeSession}${draft ? ', saved draft '+draft.draft_id : ''}. ` : '';
    await ask(`Setup request_id ${setup.request_id}. Report progress using update_compute_setup with this request_id and session_id, based on actual tool results. ` + context + (targetId ? `Help me use NGS registry target ${targetId} for RFD4. ` : 'Help me connect or manage compute for RFD4 Studio. ') + 'Use the NGS Workbench compute registry first: list_compute_targets, inspect_compute_target, and configure_ssh_target for an existing host. Reuse the selected target with use_registered_compute and this session_id; keep RFD4 runtime and checkpoint readiness separate. If no suitable target exists, offer the tool-server GPU, an existing SSH machine, or Brev. Use the existing Brev CLI and upstream RFD4 setup skills. Before creating a Brev machine, show its organization, GPU, and available price; do not create a duplicate on retry. Never stop a shared machine without discussing its active jobs. Finish with check_compute for this session. Preserve the draft and resume this session.');
  } finally { setupPending = false; }
}
async function registeredTargets() {
  const box = document.getElementById('rfd-targets');
  box.textContent = 'Checking NGS Workbench registry…';
  const data = await tool('list_registered_compute');
  box.replaceChildren();
  if (!data.available) { box.textContent = data.detail; return; }
  for (const t of data.targets) {
    const b = document.createElement('button');
    b.textContent = `${t.title}${t.supported ? '' : ' · Slurm not supported yet'}`;
    b.disabled = !t.supported;
    b.onclick = async () => { b.disabled = true; try { await setupCompute(t.target_id); } catch(e) { message(e.message); } finally { b.disabled = !t.supported; } };
    box.append(b);
  }
}
async function drafts() {
  const box = document.getElementById('rfd-drafts'); box.replaceChildren();
  const data = await tool('list_drafts');
  if (!data.drafts.length) box.textContent = 'No saved drafts yet.';
  for (const d of data.drafts) {
    const button = document.createElement('button');
    button.textContent = (d.note ? d.note.slice(0,60)+' · ' : '')+new Date(d.saved_at).toLocaleString();
    button.onclick = async () => {
      button.disabled = true;
      try {
        clearTimeout(draftTimer); await saveDraft();
        const v = await tool('restore_draft',{draft_id:d.draft_id});
        await openStudioSession(v.session_id);
        document.getElementById('rfd-note').value = v.note; imageNote = v.image_base64;
        if (v.settings) {
          document.getElementById('rfd-samples').value = v.settings.samples;
          document.getElementById('rfd-seed').value = v.settings.seed;
          for (const radio of document.querySelectorAll('input[name="thinking"]')) radio.checked = radio.value === v.settings.generation.thinking;
          for (const name of ['backbone','latent']) { document.getElementById(`rfd-${name}-noise`).value = v.settings.generation[name+'_noise']; document.getElementById(`rfd-${name}-value`).value = v.settings.generation[name+'_noise']; }
        }
        invalidate(); queueDraft(); await compute();
      } catch(e) { message(e.message); } finally { button.disabled = false; }
    };
    box.append(button);
  }
}
async function initialize() {
  if (!local) {
    const host = await rpc("ui/initialize", { appInfo: { name: "AtomWorks Studio for RFD4", version: "0.3.0" }, appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] }, protocolVersion: "2026-01-26" });
    hostCapabilities = host.hostCapabilities || {};
    parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, "*");
  }
  storage.setItem("annotation-studio-viewer-v2", "molstar");
  storage.setItem("annotation-studio-pending-example", "protein_binder");
  const bar = document.createElement("section");
  bar.id = "rfd-host";
  bar.innerHTML = `<span id="rfd-draft-status" role="status"></span><details><summary>Saved drafts</summary><button id="rfd-drafts-refresh">Refresh drafts</button><div id="rfd-drafts"></div></details><details><summary>Design notes</summary><label>Notes <input id="rfd-note" placeholder="Describe what you want to design"></label><label>Image note (PNG) <input id="rfd-image" type="file" accept="image/png"></label><p>Image notes accompany the design. Molecular annotations determine the model's constraints.</p></details><div id="rfd-plan" hidden><span id="rfd-plan-text"></span> <button id="rfd-generate">Generate in chat</button></div><details><summary>Runs</summary><button id="rfd-runs-refresh">Refresh runs</button><div id="rfd-runs"></div></details><p id="rfd-message" role="status"></p><textarea id="rfd-chat-prompt" aria-label="Request to copy into chat" hidden readonly></textarea>`;
  document.querySelector(".app-shell").append(bar);
  const generation = document.createElement('section');
  generation.id = 'rfd-generation';
  generation.innerHTML = `<div class="rfd-generation-row"><fieldset id="rfd-thinking"><legend>Thinking</legend><label><input type="radio" name="thinking" value="low">low</label><label><input type="radio" name="thinking" value="medium" checked>medium</label><label><input type="radio" name="thinking" value="high">high</label></fieldset><label>Designs<input id="rfd-samples" type="number" min="1" max="16" value="1"></label><label>Seed<input id="rfd-seed" type="number" min="0" value="42"></label></div><details><summary>Sampling</summary><div class="rfd-sampling"><label>Backbone noise <output id="rfd-backbone-value">0.3</output><input aria-label="Backbone noise" id="rfd-backbone-noise" type="range" min="0.01" max="1" step="0.01" value="0.3"></label><label>Sequence / side-chain latent noise <output id="rfd-latent-value">0.1</output><input aria-label="Sequence / side-chain latent noise" id="rfd-latent-noise" type="range" min="0.01" max="1" step="0.01" value="0.1"></label></div></details><button id="rfd-review" disabled>Review design</button></section>`;
  document.querySelector('.app-shell').prepend(generation);
  for (const name of ['backbone','latent']) document.getElementById(`rfd-${name}-noise`).addEventListener('input', e => { document.getElementById(`rfd-${name}-value`).value = e.target.value; });

  const computeBox = document.createElement('details');
  computeBox.id = 'rfd-compute-box';
  computeBox.innerHTML = `<summary>Compute · <span id="rfd-compute-label">Checking</span></summary><div class="rfd-compute-panel"><strong id="rfd-compute-name"></strong><div id="rfd-compute-gpu"></div><p id="rfd-compute-route"></p><p id="rfd-compute-checked"></p><p id="rfd-compute-running"></p><p id="rfd-setup-progress" role="status"></p><div class="rfd-compute-actions"><button id="rfd-setup">Set up in chat</button><button id="rfd-check">Check connection</button></div><details id="rfd-existing"><summary>Use an existing machine</summary><div id="rfd-targets"></div></details><details><summary>Details</summary><p id="rfd-compute-detail"></p></details></div>`;
  document.getElementById('download').after(computeBox);
  const hint = document.createElement('div'); hint.id = 'rfd-compute-hint'; hint.hidden = true;
  hint.innerHTML = `Connect a GPU when you’re ready to generate. <button id="rfd-hint-setup">Set up in chat</button> <button id="rfd-hint-dismiss" aria-label="Dismiss compute reminder">×</button>`;
  generation.append(hint);
  action('rfd-setup', () => setupCompute());
  action('rfd-hint-setup', () => setupCompute());
  action('rfd-check', () => compute(true));
  action('rfd-drafts-refresh', drafts);
  document.getElementById('rfd-hint-dismiss').onclick = () => { hintDismissed = true; hint.hidden = true; };
  document.getElementById('rfd-existing').ontoggle = e => { if (e.target.open) registeredTargets().catch(error => message(error.message)); };
  document.addEventListener('keydown', e => { if(e.key === 'Escape') computeBox.open = false; });
  document.addEventListener('click', e => { if(!computeBox.contains(e.target)) computeBox.open = false; });
  setInterval(() => { if (!document.hidden) void compute(); }, 15000);
  for (const id of ["rfd-note", "rfd-samples", "rfd-seed", "rfd-thinking", "rfd-backbone-noise", "rfd-latent-noise"]) document.getElementById(id).oninput = () => { invalidate(); queueDraft(); };
  document.getElementById("rfd-image").onchange = async (e) => {
    invalidate();
    imageNote = null; queueDraft();
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 1e7 || f.type !== "image/png") {
      message("Use a PNG under 10 MB.");
      return;
    }
    const bytes = new Uint8Array(await f.arrayBuffer());
    let binary = "";
    for (const v of bytes) binary += String.fromCharCode(v);
    imageNote = btoa(binary); queueDraft();
  };
  action("rfd-review", async () => {
    if (!computeState?.name) { document.getElementById("rfd-compute-box").open = true; message("Connect compute before reviewing a run. You can keep editing and saving your draft."); return; }
    const epoch = editEpoch;
    const p = await tool("prepare_design", { session_id: activeSession, note: document.getElementById("rfd-note").value, samples: Number(document.getElementById("rfd-samples").value), seed: Number(document.getElementById("rfd-seed").value), image_base64: imageNote, generation: { thinking: document.querySelector('input[name="thinking"]:checked').value, backbone_noise: Number(document.getElementById("rfd-backbone-noise").value), latent_noise: Number(document.getElementById("rfd-latent-noise").value) } });
    if (epoch !== editEpoch) throw Error("The design changed during review; review it again.");
    plan = p;
    document.getElementById("rfd-plan-text").textContent = `${p.samples} design(s), seed ${p.seed}, thinking ${p.generation.thinking}, noise ${p.generation.backbone_noise} / ${p.generation.latent_noise}, ${p.instance}. Saved input ${p.sha256.slice(0, 12)}. ${(p.issues || []).map((x) => x.message).join(" ")}`;
    document.getElementById("rfd-plan").hidden = false;
  });
  action("rfd-generate", () => {
    if (!plan) throw Error("Review the current design first");
    return ask(`Generate the reviewed RFD4 design using execute_rfd4_plan with plan_id ${plan.snapshot_id} and plan_checksum ${plan.plan_checksum}. Use this exact saved plan (${plan.samples} designs, seed ${plan.seed}, ${plan.instance}).`);
  });
  action("rfd-runs-refresh", refreshRuns);
  await compute().catch((e) => message(e.message));
}
async function refreshRuns() {
  const data = await tool("get_workspace"), host = document.getElementById("rfd-runs");
  host.replaceChildren();
  for (const job of data.jobs) {
    const row = document.createElement("div"), label = document.createElement("span"), button = document.createElement("button");
    label.textContent = `${job.job_id.slice(0, 8)} \xB7 ${job.status} `;
    button.textContent = job.status === "completed" ? "View result" : "Check status";
    button.onclick = async () => {
      button.disabled = true;
      try {
        if (job.status === "completed") {
          await showResults(job.job_id, row);
        } else {
          await tool("check_rfd4_job", { job_id: job.job_id });
          await refreshRuns();
        }
      } catch (e) {
        message(e.message);
      } finally {
        button.disabled = false;
      }
    };
    row.append(label, button);
    host.append(row);
  }
  if (!data.jobs.length) host.textContent = "No runs yet.";
}
export {
  initialize,
  storage,
  studioEvent,
  studioFetch,
  tool
};

async function showResults(jobId, row) {
  row.querySelector('[data-results]')?.remove();
  const data = await tool('list_results', {job_id: jobId});
  const controls = document.createElement('span');
  controls.dataset.results = 'true';
  const select = document.createElement('select');
  select.setAttribute('aria-label', 'Input or generated design');
  select.add(new Option('Input', ''));
  for (const design of data.designs) select.add(new Option(`Design ${design.index + 1}`, String(design.index)));
  async function open() {
    select.disabled = true;
    try {
      const value = await tool('open_run_structure', {job_id: jobId, index: select.value === '' ? null : Number(select.value)});
      await openStudioSession(value.session_id);
    } catch(e) { message(e.message); }
    finally { select.disabled = false; }
  }
  select.onchange = open;
  const download = document.createElement('button');
  download.textContent = 'Download all';
  download.onclick = async () => {
    download.disabled = true;
    try {
      const file = await tool('download_results', {job_id: jobId});
      const blob = new Blob([Uint8Array.from(atob(file.base64), c => c.charCodeAt(0))], {type: file.mime_type});
      const url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href = url; a.download = file.filename; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch(e) { message(e.message); }
    finally { download.disabled = false; }
  };
  controls.append(select, download); row.append(controls);
  if (data.designs.length) select.value = String(data.designs[0].index);
  await open();
}

function openStudioSession(id) {
  return new Promise((resolve,reject) => {
    const done = event => {
      if (event.detail.id !== id) return;
      clearTimeout(timer); removeEventListener('rfd-session-opened',done);
      event.detail.error ? reject(Error(event.detail.error)) : resolve();
    };
    const timer = setTimeout(() => { removeEventListener('rfd-session-opened',done); reject(Error('Studio did not finish opening the structure')); }, 120000);
    addEventListener('rfd-session-opened',done);
    dispatchEvent(new CustomEvent('rfd-open-session',{detail:id}));
  });
}
