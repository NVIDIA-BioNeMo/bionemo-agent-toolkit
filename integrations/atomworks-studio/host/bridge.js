import {navigationRequest} from './navigation-request.js';
let seq = 0, activeSession = null, plan = null, imageNote = null, editEpoch = 0;
let hostCapabilities = {}, saving = Promise.resolve(), draftTimer;
let watchedRun = null, checkingRun = false, uploadGeneration = 0;
let navigationGeneration = 0, navigationCommitting = false;
let freshDocumentRequest = null;
let draftEpoch = 0;
let documentMetadataRequest = null;
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
  const body = [204, 205, 304].includes(value.status) ? null : value.text;
  return new Response(body, { status: value.status, headers: { "Content-Type": value.content_type } });
}
export async function downloadFile({filename, mimeType, text, base64}) {
  if (typeof filename !== 'string' || !filename || typeof mimeType !== 'string'
      || (typeof text === 'string') === (typeof base64 === 'string')) {
    throw Error('Invalid download contents.');
  }
  const name = filename.replace(/[\\/\x00-\x1f\x7f]/g, '_');
  if (local) {
    const bytes = typeof text === 'string' ? text : Uint8Array.from(atob(base64), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type:mimeType}));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = name;
    try { anchor.click(); }
    finally { setTimeout(() => URL.revokeObjectURL(url), 60000); }
    return;
  }
  if (!hostCapabilities.downloadFile) {
    if (!hostCapabilities.message) throw Error('This host cannot download files or send export requests to chat. The file was not saved.');
    const saved = await tool('save_rfd4_export', {filename:name, mime_type:mimeType,
      ...(typeof text === 'string' ? {text} : {base64_data:base64})});
    if (!saved || !/^[0-9a-f]{32}$/.test(saved.export_id)) throw Error('The export could not be saved.');
    const sent = await sendScopedChat('Please retrieve RFD4 export ' + saved.export_id +
      ' using get_rfd4_export and share its clickable local file link. It contains the exact CIF or results ZIP saved when I clicked export; do not run a design.');
    if (!sent) throw Error('The export was saved locally, but the editor changed before chat confirmed it.');
    message('Export saved locally. Continue in chat for the file link.');
    return;
  }
  const resource = {uri:'file:///' + encodeURIComponent(name), mimeType,
    ...(typeof text === 'string' ? {text} : {blob:base64})};
  const result = await rpc('ui/download-file', {contents:[{type:'resource', resource}]});
  if (!result || typeof result !== 'object' || result.isError) {
    throw Error('The host cancelled or rejected the download. The file was not saved.');
  }
}
function studioEvent(type, session) {
  if (type === 'ready' && freshDocumentRequest?.state === 'committing') {
    resetDocumentMetadata();
    freshDocumentRequest = null;
  }
  if (type === "ready") { document.getElementById("rfd-chat-prompt").hidden = true; message(""); }
  if (type === 'ready' && documentMetadataRequest?.id === session && documentMetadataRequest.request.state === 'committing') {
    applyDocumentMetadata(documentMetadataRequest.metadata);
    documentMetadataRequest.applied = true;
  }
  if (activeSession !== session) uploadGeneration++;
  activeSession = session;
  if (type === "changed" || type === "ready") { invalidate(); queueDraft(); }
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
    message("Copy this request into chat to continue. This preview cannot send a message to the conversation.");
    return false;
  }
  return sendScopedChat(text);
}
export async function sendScopedChat(text, send = params => rpc('ui/message', params)) {
  const session = activeSession;
  try {
    const result = await send({role:'user',content:[{type:'text',text}]});
    if (session !== activeSession) return false;
    if (result?.isError) throw Error('Host did not accept the chat request');
    message('Request sent to the conversation. Continue there.');
    return true;
  } catch(error) {
    if (session !== activeSession) return false;
    throw error;
  }
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
export async function attachImage(file) {
  const generation = ++uploadGeneration, session = activeSession;
  invalidate(); imageNote = null; queueDraft();
  if (!file) return false;
  if (file.size > 1e7 || file.type !== 'image/png') {
    message('Use a PNG under 10 MB.'); return false;
  }
  let buffer;
  try { buffer = await file.arrayBuffer(); }
  catch(error) {
    if (session === activeSession && generation === uploadGeneration) throw error;
    return false;
  }
  if (session !== activeSession || generation !== uploadGeneration) return false;
  let binary = '';
  for (const value of new Uint8Array(buffer)) binary += String.fromCharCode(value);
  imageNote = btoa(binary);
  invalidate(); queueDraft();
  return true;
}
function queueDraft() {
  clearTimeout(draftTimer);
  const session = activeSession, epoch = ++draftEpoch;
  document.getElementById('rfd-draft-status').textContent = 'Unsaved changes';
  draftTimer = setTimeout(() => {
    if (session !== activeSession || epoch !== draftEpoch) return;
    saveDraft().catch(e => {
      if (session === activeSession && epoch === draftEpoch)
        document.getElementById('rfd-draft-status').textContent = 'Draft not saved: '+e.message;
    });
  }, 1500);
}
export async function saveDraft() {
  if (!activeSession) return null;
  const session = activeSession, epoch = draftEpoch;
  const args = {session_id: activeSession, note: document.getElementById('rfd-note').value, image_base64: imageNote, settings: settings()};
  // Serialize exports so an older response cannot replace the newest draft.
  saving = saving.catch(() => {}).then(() => tool('save_draft', args));
  const draft = await saving;
  if (session === activeSession && epoch === draftEpoch)
    document.getElementById('rfd-draft-status').textContent = 'Draft saved';
  return draft;
}
export async function saveBeforeRestore() {
  try { await saveDraft(); return false; }
  catch (error) {
    if (!error.message.includes('EDITOR_SESSION_EXPIRED:')) throw error;
    return true;
  }
}
export function beginNavigation() {
  if (navigationCommitting) throw Error('Wait for the current structure to finish opening.');
  const generation = ++navigationGeneration, session = activeSession, epoch = editEpoch;
  return () => generation === navigationGeneration && session === activeSession && epoch === editEpoch;
}
function resetDocumentMetadata() {
  document.getElementById('rfd-note').value = '';
  document.getElementById('rfd-image').value = '';
  imageNote = null;
  uploadGeneration++;
  document.getElementById('rfd-samples').value = '1';
  document.getElementById('rfd-seed').value = '42';
  for (const radio of document.querySelectorAll('input[name="thinking"]')) radio.checked = radio.value === 'medium';
  for (const [name, value] of [['backbone', '0.3'], ['latent', '0.1']]) {
    document.getElementById(`rfd-${name}-noise`).value = value;
    document.getElementById(`rfd-${name}-value`).value = value;
  }
  const origin = document.getElementById('rfd-generation-origin');
  if (origin) { origin.textContent = ''; origin.hidden = true; }
}
function normalizeDocumentMetadata(value) {
  if (!value || typeof value.note !== 'string' || value.note.length > 20000 ||
      (value.image_base64 != null && typeof value.image_base64 !== 'string')) throw Error('Saved document metadata is invalid; your current draft is preserved.');
  const s = value.settings;
  if (s != null && (!Number.isInteger(s.samples) || s.samples < 1 || s.samples > 16 ||
      !Number.isInteger(s.seed) || s.seed < 0 || s.seed >= 2**31 ||
      !['low','medium','high'].includes(s.generation?.thinking) ||
      !['backbone_noise','latent_noise'].every(key => Number.isFinite(s.generation[key]) && s.generation[key] > 0 && s.generation[key] <= 1)))
    throw Error('Saved generation settings are invalid; your current draft is preserved.');
  return value;
}
function applyDocumentMetadata(value) {
  resetDocumentMetadata();
  document.getElementById('rfd-note').value = value.note;
  imageNote = value.image_base64 || null;
  if (value.settings) {
    const s = value.settings;
    document.getElementById('rfd-samples').value = s.samples;
    document.getElementById('rfd-seed').value = s.seed;
    for (const radio of document.querySelectorAll('input[name="thinking"]')) radio.checked = radio.value === s.generation.thinking;
    for (const name of ['backbone','latent']) {
      document.getElementById(`rfd-${name}-noise`).value = s.generation[name+'_noise'];
      document.getElementById(`rfd-${name}-value`).value = s.generation[name+'_noise'];
    }
  }
  const origin = document.getElementById('rfd-generation-origin');
  origin.textContent = value.source === 'saved_run' ? 'Saved run settings; editable for a new run.' :
    value.source === 'unavailable' ? 'This older run has no verified saved metadata. New draft defaults are shown.' : '';
  if (value.image_note_unavailable) origin.textContent += ' The original image note could not be verified.';
  origin.hidden = !origin.textContent;
}
export async function nativeFileNavigation(operation, {freshDocument = false} = {}) {
  const request = navigationRequest(beginNavigation());
  const abort = new AbortController();
  navigationCommitting = true;
  const previousInert = document.body.inert;
  document.body.inert = true;
  uploadGeneration++;
  clearTimeout(draftTimer);
  let timer;
  try {
    const work = (async () => {
      const draft = await saveDraft();
      if (!request.current()) throw Error('The design changed; open the structure again.');
      const token = {current: request.current, signal: abort.signal, async copySavedSession() {
        if (!request.current() || !draft?.draft_id || !draft.snapshot_checksum) throw Error('Save the current design with the latest plugin before combining.');
        const copy = await tool('restore_draft', {draft_id: draft.draft_id, expected_checksum: draft.snapshot_checksum});
        if (!request.current()) throw Error('The design changed; combine the structure again.');
        return copy.session_id;
      }, beginCommit() {
        request.beginCommit();
        if (freshDocument) freshDocumentRequest = request;
      }};
      return await operation(token);
    })();
    const deadline = new Promise((resolve, reject) => {
      timer = setTimeout(() => {
        if (request.expire()) { abort.abort(); reject(Error('Opening timed out before replacement. Your previous design is preserved; try opening again.')); }
        else message('Studio is still replacing the structure. Editing remains locked; if it does not finish, reload and restore your saved draft.');
      }, 120000);
    });
    return await Promise.race([work, deadline]);
  } finally {
    clearTimeout(timer);
    abort.abort();
    if (freshDocumentRequest === request) freshDocumentRequest = null;
    request.settle();
    document.body.inert = previousInert;
    navigationCommitting = false;
  }
}
// A successful replacement changes the session and edit epoch by design. Report
// recovery at its commit acknowledgment, before a slow compute refresh.
export async function restoreDraft(draftId) {
  const current = beginNavigation();
  clearTimeout(draftTimer); const expired = await saveBeforeRestore();
  if (!current()) return;
  const v = await tool('restore_draft', {draft_id:draftId});
  if (!current()) return;
  await openStudioSession(v.session_id, current, {...v, source:'saved_draft'});
  if (expired) message('Restored the saved draft. The previous editor session expired; unsaved edits could not be recovered.');
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
        await restoreDraft(d.draft_id);
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
  const help = document.createElement('a');
  help.id = 'rfd-help';
  help.textContent = 'Get help';
  help.href = 'https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/issues';
  help.target = '_blank';
  help.rel = 'noopener noreferrer';
  help.title = 'Get help or report an issue on GitHub';
  help.onclick = async event => {
    if (local || !hostCapabilities.openLinks) return;
    event.preventDefault();
    try {
      const result = await rpc('ui/open-link', {url: help.href});
      if (result?.isError) throw Error('Could not open GitHub. Use the Get help link to copy its address.');
    } catch (error) { message(error.message); }
  };
  const studioCredit = document.getElementById('guide-link');
  studioCredit.onclick = async event => {
    if (local || !hostCapabilities.openLinks) return;
    event.preventDefault();
    try {
      const result = await rpc('ui/open-link', {url: studioCredit.href});
      if (result?.isError) throw Error('Could not open the AtomWorks Studio repository.');
    } catch (error) { message(error.message); }
  };
  const bar = document.createElement("section");
  bar.id = "rfd-host";
  bar.innerHTML = `<span id="rfd-draft-status" role="status"></span><details id="rfd-saved-drafts" open><summary>Saved drafts</summary><button id="rfd-drafts-refresh">Refresh drafts</button><div id="rfd-drafts"></div></details><details id="rfd-design-notes"><summary>Design notes</summary><label>Notes <input id="rfd-note" placeholder="Describe what you want to design"></label><label>Image note (PNG) <input id="rfd-image" type="file" accept="image/png"></label><p>Image notes accompany the design. Molecular annotations determine the model's constraints.</p></details><div id="rfd-plan" hidden><span id="rfd-plan-text"></span> <button id="rfd-generate">Generate in chat</button></div><details id="rfd-run-history"><summary>Runs</summary><button id="rfd-runs-refresh">Refresh runs</button><div id="rfd-runs"></div></details><p id="rfd-message" role="status"></p><textarea id="rfd-chat-prompt" aria-label="Request to copy into chat" hidden readonly></textarea>`;
  document.querySelector(".app-shell").append(bar);
  const generation = document.createElement('section');
  generation.id = 'rfd-generation';
  generation.innerHTML = `<div class="rfd-generation-row"><fieldset id="rfd-thinking"><legend>Thinking</legend><label><input type="radio" name="thinking" value="low">low</label><label><input type="radio" name="thinking" value="medium" checked>medium</label><label><input type="radio" name="thinking" value="high">high</label></fieldset><label>Designs<input id="rfd-samples" type="number" min="1" max="16" value="1"></label><label>Seed<input id="rfd-seed" type="number" min="0" value="42"></label></div><details><summary>Sampling</summary><div class="rfd-sampling"><label>Backbone noise <output id="rfd-backbone-value">0.3</output><input aria-label="Backbone noise" id="rfd-backbone-noise" type="range" min="0.01" max="1" step="0.01" value="0.3"></label><label>Sequence / side-chain latent noise <output id="rfd-latent-value">0.1</output><input aria-label="Sequence / side-chain latent noise" id="rfd-latent-noise" type="range" min="0.01" max="1" step="0.01" value="0.1"></label></div></details><button id="rfd-review" disabled>Review design</button></section>`;
  generation.insertAdjacentHTML('afterbegin', '<p id="rfd-generation-origin" role="status" hidden></p>');
  const generateSection = document.createElement('details');
  generateSection.id = 'rfd-generate-section';
  generateSection.className = 'card';
  generateSection.dataset.editorCard = 'main';
  generateSection.innerHTML = '<summary>Generate with RFD4-Proteina</summary>';
  generateSection.append(generation, document.getElementById('rfd-plan'));
  document.querySelector('.editor-document').after(generateSection);
  for (const name of ['backbone','latent']) document.getElementById(`rfd-${name}-noise`).addEventListener('input', e => { document.getElementById(`rfd-${name}-value`).value = e.target.value; });

  const runTarget = document.createElement('span');
  runTarget.id = 'rfd-run-target';
  runTarget.setAttribute('role', 'status');
  runTarget.textContent = 'Run on: choose in chat';
  const toolbar = document.querySelector('.header-actions');
  const menu = (id, title) => {
    const box = document.createElement('details');
    box.id = id; box.className = 'rfd-toolbar-menu';
    const summary = document.createElement('summary'); summary.textContent = title;
    const panel = document.createElement('div'); panel.className = 'rfd-toolbar-panel';
    box.append(summary, panel); return {box, panel};
  };
  const fileMenu = menu('rfd-file-menu', 'File');
  // Move upstream controls intact, keeping their input IDs and event handlers.
  fileMenu.panel.append(...toolbar.children);
  const draftMenu = menu('rfd-draft-menu', 'Drafts');
  draftMenu.panel.append(document.getElementById('rfd-draft-status'), document.getElementById('rfd-design-notes'), document.getElementById('rfd-saved-drafts'));
  const runsMenu = menu('rfd-runs-menu', 'Runs');
  runsMenu.panel.append(document.getElementById('rfd-runs-refresh'), document.getElementById('rfd-runs'));
  document.getElementById('rfd-run-history').remove();
  toolbar.append(fileMenu.box, draftMenu.box, runsMenu.box, runTarget, help);
  const menus = [fileMenu.box, draftMenu.box, runsMenu.box];
  for (const box of menus) box.addEventListener('toggle', () => {
    if (!box.open) return;
    for (const other of menus) if (other !== box) other.open = false;
    if (box === draftMenu.box) void drafts().catch(e => message(e.message));
    if (box === runsMenu.box) void refreshRuns().catch(e => message(e.message));
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const activeMenu = menus.find(box => box.open && box.contains(document.activeElement));
    for (const box of menus) box.open = false;
    activeMenu?.querySelector('summary')?.focus();
  });
  document.addEventListener('click', e => { for (const box of menus) if (!box.contains(e.target)) box.open = false; });
  action('rfd-drafts-refresh', drafts);
  setInterval(() => { if (!document.hidden) void pollRun(); }, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void pollRun(); });
  for (const id of ["rfd-note", "rfd-samples", "rfd-seed", "rfd-thinking", "rfd-backbone-noise", "rfd-latent-noise"]) document.getElementById(id).oninput = () => {
    document.getElementById('rfd-generation-origin').hidden = true;
    invalidate(); queueDraft();
  };
  document.getElementById("rfd-image").onchange = e => {
    void attachImage(e.target.files[0]).catch(error => message(error.message));
  };
  action("rfd-review", reviewDesign);
  action("rfd-generate", generateDesign);
  action("rfd-runs-refresh", refreshRuns);
}
export async function reviewDesign() {
    const epoch = editEpoch;
    const p = await tool("prepare_design_request", { session_id: activeSession, note: document.getElementById("rfd-note").value, samples: Number(document.getElementById("rfd-samples").value), seed: Number(document.getElementById("rfd-seed").value), image_base64: imageNote, generation: { thinking: document.querySelector('input[name="thinking"]:checked').value, backbone_noise: Number(document.getElementById("rfd-backbone-noise").value), latent_noise: Number(document.getElementById("rfd-latent-noise").value) } });
    if (epoch !== editEpoch) throw Error("The design changed during review; review it again.");
    plan = p;
    document.getElementById("rfd-plan-text").textContent = `${p.samples} design(s), seed ${p.seed}, thinking ${p.generation.thinking}, noise ${p.generation.backbone_noise} / ${p.generation.latent_noise}, choose a machine in chat. Saved input ${p.sha256.slice(0, 12)}. ${(p.issues || []).map((x) => x.message).join(" ")}`;
    document.getElementById("rfd-plan").hidden = false;
}
export async function generateDesign() {
    if (!plan) throw Error("Review the current design first");
    const request = plan, session = activeSession, epoch = editEpoch;
    const delivered = await ask(`Please run saved RFD4 design request ${request.request_id}. Read it with get_design_request and follow the RFD4 Studio chat workflow. Choose the execution host with me if it is unclear.`);
    if (delivered && plan === request && session === activeSession && epoch === editEpoch)
      watchedRun = {jobId: request.request_id, session, epoch};
}
// Only the most recently submitted plan may replace the current input.
// Edits, navigation and another submission invalidate that permission.
function canOpenRun(run) {
  return watchedRun === run && activeSession === run.session && editEpoch === run.epoch;
}
async function pollRun() {
  if (!watchedRun || checkingRun) return;
  checkingRun = true;
  const run = watchedRun;
  try {
    const workspace = await tool('get_workspace');
    let job = workspace.jobs.find(job => job.job_id === run.jobId);
    if (!job) return; // The chat may still be choosing a host.
    document.getElementById('rfd-run-target').textContent = `Run on: ${job.machine_name || job.instance || job.target?.ssh_alias || 'chosen in chat'} · ${job.status}`;
    if (['queued', 'submitted', 'submitting', 'submission_unknown', 'running'].includes(job.status)) {
      job = await tool('check_rfd4_job', {job_id: run.jobId});
    }
    if (watchedRun !== run) return;
    if (job.status === 'failed') {
      watchedRun = null;
      message('Generation failed. Open Runs for details.');
      return;
    }
    if (job.status !== 'completed') return;
    await refreshRuns();
    if (watchedRun !== run) return;
    if (!canOpenRun(run)) {
      watchedRun = null;
      message('Your design is ready in Runs. Your current edits have been kept.');
      return;
    }
    // Keep the guard active across retrieval, draft saving and structure import.
    const row = document.getElementById('rfd-runs').querySelector(`[data-job-id="${run.jobId}"]`);
    const opened = await showResults(run.jobId, row, () => canOpenRun(run));
    if (watchedRun === run) {
      watchedRun = null;
      message(opened ? 'Generation complete. Design 1 is now in the viewer.' : 'Your design is ready in Runs. Your current edits have been kept.');
    }
  } catch (error) {
    message('Could not refresh the run: ' + error.message + '. Retrying automatically.');
  } finally { checkingRun = false; }
}
async function refreshRuns() {
  const data = await tool("get_workspace"), host = document.getElementById("rfd-runs");
  host.replaceChildren();
  if (!data.jobs.length) host.textContent = 'No runs yet. Review a design in Generate to get started.';
  for (const job of data.jobs) {
    const row = document.createElement("div"), label = document.createElement("span"), button = document.createElement("button");
    row.dataset.jobId = job.job_id;
    label.textContent = `${job.job_id.slice(0, 8)} \xB7 ${job.status} \xB7 ${job.machine_name || job.instance || 'Original machine'} `;
    button.textContent = job.status === "completed" ? "View result" : "Check status";
    button.onclick = async () => {
      button.disabled = true;
      try {
        if (job.status === "completed") {
          watchedRun = null;
          document.getElementById('rfd-run-target').textContent = `Run on: ${job.machine_name || job.instance || 'original host'} · ${job.status}`;
          await showResults(job.job_id, row);
        } else {
          const observed = await tool("check_rfd4_job", { job_id: job.job_id });
          message(observed.detail || observed.error || `Run status: ${observed.status}`);
          await refreshRuns();
        }
      } catch (e) {
        message(e.message);
      } finally {
        button.disabled = false;
      }
    };
    row.append(label, button);
    if (job.detail || job.error) {
      const detail = document.createElement('small');
      detail.textContent = job.detail || job.error;
      row.append(detail);
    }
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

async function showResults(jobId, row, canOpen = () => true) {
  row.querySelector('[data-results]')?.remove();
  const data = await tool('list_results', {job_id: jobId});
  const controls = document.createElement('span');
  controls.dataset.results = 'true';
  const select = document.createElement('select');
  select.setAttribute('aria-label', 'Input or generated design');
  select.add(new Option('Input', ''));
  for (const design of data.designs) select.add(new Option(`Design ${design.index + 1}`, String(design.index)));
  async function open() {
    if (!canOpen()) return false;
    select.disabled = true;
    try {
      const navigation = beginNavigation();
      const current = () => navigation() && canOpen();
      clearTimeout(draftTimer);
      await saveDraft();
      if (!current()) return false;
      const value = await tool('open_run_structure', {job_id: jobId, index: select.value === '' ? null : Number(select.value)});
      if (!current()) return false;
      await openStudioSession(value.session_id, current, value.document_metadata || {source:'unavailable',note:'',image_base64:null,settings:null});
      return true;
    } catch(e) { message(e.message); throw e; }
    finally { select.disabled = false; }
  }
  select.onchange = () => { watchedRun = null; canOpen = () => true; void open().catch(e => message(e.message)); };
  const download = document.createElement('button');
  download.textContent = 'Download all';
  download.onclick = async () => {
    download.disabled = true;
    try {
      const file = await tool('download_results', {job_id: jobId});
      await downloadFile({filename:file.filename, mimeType:file.mime_type, base64:file.base64});
    } catch(e) { message(e.message); }
    finally { download.disabled = false; }
  };
  controls.append(select, download); row.append(controls);
  if (data.designs.length) select.value = String(data.designs[0].index);
  if (!data.designs.length) throw Error('The completed run has no generated structures');
  return await open();
}

export async function openStudioSession(id, current, metadata = null) {
  if (!current()) throw Error('The design changed; open the structure again.');
  if (metadata) normalizeDocumentMetadata(metadata);
  navigationCommitting = true;
  const request = navigationRequest(current), requestId = ++seq;
  const metadataRequest = metadata ? {id,request,metadata,applied:false} : null;
  documentMetadataRequest = metadataRequest;
  const previousInert = document.body.inert;
  document.body.inert = true;
  uploadGeneration++;
  try { return await new Promise((resolve,reject) => {
    const done = event => {
      if (event.detail.id !== id || event.detail.requestId !== requestId) return;
      clearTimeout(timer); removeEventListener('rfd-session-opened',done);
      request.settle();
      if (event.detail.error) reject(Error(event.detail.error));
      else if (metadataRequest && !metadataRequest.applied) reject(Error('Structure did not confirm its saved metadata; reopen the saved draft.'));
      else resolve();
    };
    const timer = setTimeout(() => {
      if (request.expire()) {
        removeEventListener('rfd-session-opened',done);
        reject(Error('Opening timed out before replacing the structure. You can try again.'));
      } else {
        message('Studio is still replacing the structure. Editing remains locked until it finishes. If it does not recover, reload Studio and reopen your saved draft.');
      }
    }, 120000);
    addEventListener('rfd-session-opened',done);
    dispatchEvent(new CustomEvent('rfd-open-session',{detail:{id,requestId,current:request.current,beginCommit:request.beginCommit}}));
  }); } finally {
    if (documentMetadataRequest === metadataRequest) documentMetadataRequest = null;
    document.body.inert = previousInert; navigationCommitting = false;
  }
}
