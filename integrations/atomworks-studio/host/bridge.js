import {navigationRequest} from './navigation-request.js';
import {connectSavedCompute} from './compute-connection.js';
let seq = 0, activeSession = null, plan = null, imageNote = null, editEpoch = 0;
let hostCapabilities = {}, computeState = null, saving = Promise.resolve(), draftTimer, polling = false, setupPending = false, hintDismissed = false;
let watchedRun = null, checkingRun = false, uploadGeneration = 0;
let navigationGeneration = 0, navigationCommitting = false;
let freshDocumentRequest = null;
// Compute changes invalidate reviewed plans, but do not change draft contents.
let draftEpoch = 0;
let documentMetadataRequest = null;
const lastProbe = new Map();
let connectionPending = false, computeGeneration = 0;
let connectionUncertain = false, retryConnectionAt = 0;
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
  if (['begin_compute_setup', 'select_compute', 'refresh_selected_compute_access', 'disconnect_compute', 'prepare_design'].includes(name)) {
    const capabilities = await tool('get_compute_capabilities');
    if (capabilities.protocol !== 3 || capabilities.schema !== 2) throw Error('Update and restart the RFD4 plugin before changing compute.');
  }
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
function renderCompute(c) {
  const labels = {unregistered:'Not connected', registered:'Configured', ready:'Ready', ownership_required:'Ownership needed', needs_setup:'RFD4 setup needed', disconnected:'Not connected', connecting:'Connecting', checking:'Checking readiness', setting_up:'Setting up'};
  const label = c.active_jobs?.length && c.state === 'ready' ? 'Running' : labels[c.state] || 'Status unavailable';
  document.getElementById('rfd-compute-label').textContent = label;
  document.getElementById('rfd-compute-box').dataset.state = c.state;
  document.getElementById('rfd-compute-name').textContent = c.name || 'Connect a GPU to generate designs';
  document.getElementById('rfd-compute-gpu').textContent = (c.gpu || '').split('\n').map(line => line.split(',').slice(0,2).join(' · ')).join('\n');
  document.getElementById('rfd-compute-route').textContent = c.name ? `${c.kind === 'local' ? 'On the tool-server computer' : 'Via '+c.kind.toUpperCase()} · Connection: ${c.transport === 'reachable' ? 'connected' : c.state === 'connecting' ? 'checking' : 'not verified'}` : 'Choose an existing machine below, then Connect. You can keep editing.';
  document.getElementById('rfd-compute-detail').textContent = c.detail || '';
  document.getElementById('rfd-compute-checked').textContent = c.checked_at ? 'Last checked '+new Date(c.checked_at).toLocaleString() : '';
  document.getElementById('rfd-setup').textContent = (local || !hostCapabilities.message) ? 'Show chat request' : c.state === 'ownership_required' ? 'Review ownership in chat' : c.power === 'stopped' ? 'Start in chat' : c.state === 'unregistered' ? 'Connect compute' : ['needs_setup','disconnected'].includes(c.state) ? 'Continue setup in chat' : 'Manage in chat';
  document.getElementById('rfd-check').hidden = !c.name;
  document.getElementById('rfd-disconnect').hidden = !c.selection?.machine_id;
  for (const id of ['rfd-check','rfd-disconnect','rfd-setup']) document.getElementById(id).disabled = connectionPending;
  const stop = document.getElementById('rfd-stop');
  stop.hidden = !(c.selection?.machine_id && c.kind === 'brev' && c.power === 'running' && c.state !== 'ownership_required');
  stop.disabled = Boolean(c.active_jobs?.length || c.unresolved_active_jobs?.length);
  stop.textContent = (local || !hostCapabilities.message) ? 'Show stop request' : 'Review stop in chat';
  stop.title = stop.disabled ? 'Resolve active or unknown runs before stopping.' : 'Review a separate stop action. Disconnecting does not stop the machine.';
  document.getElementById('rfd-compute-hint').hidden = hintDismissed || c.state !== 'unregistered';
  document.getElementById('rfd-setup-progress').textContent = c.operation && !['succeeded','failed','cancelled'].includes(c.operation.state) ? (c.operation.detail || 'Waiting for your compute choice in chat.') : '';
  document.getElementById('rfd-compute-running').textContent = c.active_jobs?.length ? `${c.active_jobs.length} active run(s). Closing Studio does not stop them.` : c.name ? 'Completing a run does not stop its machine.' : '';
}
export async function compute(check = false) {
  if (polling || connectionPending) return;
  if (connectionUncertain) {
    if (!check && Date.now() < retryConnectionAt) return;
    check = true;
    retryConnectionAt = Date.now() + 60000;
  }
  polling = true;
  const session = activeSession;
  const generation = computeGeneration;
  let observed = computeState;
  if (check) renderCompute({...computeState, state:'checking'});
  try {
    let c = await tool(check ? 'check_compute' : 'get_compute_status', {session_id: session});
    if (session !== activeSession || generation !== computeGeneration) return;
    observed = c;
    if (check) lastProbe.set(c.fingerprint, Date.now());
    // Expired evidence is a refresh task, not a problem for the user to fix.
    // Probe only configured targets and bound retries if the service is down.
    if (!check && c.state === 'registered' && c.fingerprint &&
        Date.now() - (lastProbe.get(c.fingerprint) || 0) > 60000) {
      lastProbe.set(c.fingerprint, Date.now());
      renderCompute({...c, state:'checking'});
      c = await tool('check_compute', {session_id: session});
      if (session !== activeSession || generation !== computeGeneration) return;
    }
    if (computeState?.fingerprint && computeState.fingerprint !== c.fingerprint) invalidate();
    connectionUncertain = false;
    computeState = c; renderCompute(c);
  } catch(e) {
    if (session !== activeSession || generation !== computeGeneration) return;
    renderCompute({...observed, state:'disconnected', detail:e.message});
  } finally { polling = false; }
}
async function setupCompute(targetId = null, intent = 'manage') {
  if (setupPending) return;
  setupPending = true;
  const session = activeSession;
  try {
    // Compute management does not replace or mutate the editor document.
    if (session !== activeSession) return;
    const current = await tool('get_compute_status', {session_id: session});
    if (session !== activeSession) return;
    const setup = await tool('begin_compute_setup', {session_id: session,
      expected_revision: current.selection.revision, target_id: targetId});
    if (session !== activeSession) return;
    const request = intent === 'stop' ? 'Please review stopping this dedicated RFD4 machine, including active work and ownership checks. Do not treat this app message as final shutdown approval.' : 'Please help me connect or manage RFD4 compute.';
    const delivered = await ask(`${request} Inspect operation ${setup.id} with get_compute_operation and help me choose the next action. Studio session: ${setup.session_id}.`);
    if (delivered && session === activeSession) message('Compute request sent to chat.');
  } finally { setupPending = false; }
}
async function registeredTargets() {
  const box = document.getElementById('rfd-targets');
  box.textContent = 'Checking saved compute…';
  const data = await tool('list_registered_compute');
  box.replaceChildren();
  if (!data.available) { box.textContent = data.detail; return; }
  if (!data.targets.length) box.textContent = `No machines saved yet. Choose ${document.getElementById('rfd-setup').textContent} to connect one.`;
  if (!data.targets.length) return;
  const choices = document.createElement('select');
  choices.setAttribute('aria-label','Existing compute machine');
  for (const t of data.targets) {
    const option = document.createElement('option');
    option.value = t.target_id; option.textContent = t.title; option.disabled = !t.supported;
    choices.append(option);
  }
  choices.value = data.targets.find(t => t.supported)?.target_id || '';
  const button = document.createElement('button'); button.textContent = 'Connect';
  button.disabled = !choices.value || connectionPending;
  button.onclick = async () => {
    if (connectionPending || !choices.value) return;
    connectionPending = true;
    connectionUncertain = true;
    retryConnectionAt = Date.now() + 60000;
    const session = activeSession, generation = ++computeGeneration;
    const current = () => session === activeSession && generation === computeGeneration;
    choices.disabled = true; button.disabled = true;
    renderCompute({...computeState, state:'connecting', transport:'unverified', gpu:'', checked_at:null});
    try {
      await connectSavedCompute({targetId:choices.value, session, current, tool,
        render(c) { computeState = c; renderCompute(c); },
        accept(c) { connectionUncertain = false; invalidate(); computeState = c; renderCompute(c); }});
    } catch(error) {
      if (current()) { renderCompute({...computeState,state:'disconnected',detail:error.message}); message(error.message); }
    } finally {
      connectionPending = false; choices.disabled = false; button.disabled = !choices.value;
      for (const id of ['rfd-check','rfd-disconnect','rfd-setup']) document.getElementById(id).disabled = false;
      if (!current()) { connectionUncertain = false; void compute(); }
    }
  };
  box.append(choices, button);
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
  await compute();
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

  const computeBox = document.createElement('details');
  computeBox.id = 'rfd-compute-box';
  computeBox.innerHTML = `<summary>Compute · <span id="rfd-compute-label">Checking</span></summary><div class="rfd-compute-panel"><strong id="rfd-compute-name"></strong><div id="rfd-compute-gpu"></div><p id="rfd-compute-route"></p><p id="rfd-compute-checked"></p><p id="rfd-compute-running"></p><p id="rfd-setup-progress" role="status"></p><div class="rfd-compute-actions"><button id="rfd-setup">Set up in chat</button><button id="rfd-check">Check connection</button><button id="rfd-disconnect">Disconnect this session</button></div><details id="rfd-existing"><summary>Use an existing machine</summary><div id="rfd-targets"></div></details><details><summary>Details</summary><p id="rfd-compute-detail"></p><button id="rfd-stop" hidden>Review stop in chat</button></details></div>`;
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
  toolbar.append(fileMenu.box, draftMenu.box, runsMenu.box, computeBox, help);
  const menus = [fileMenu.box, draftMenu.box, runsMenu.box, computeBox];
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
  const hint = document.createElement('div'); hint.id = 'rfd-compute-hint'; hint.hidden = true;
  hint.innerHTML = `Connect a GPU when you’re ready to generate. <button id="rfd-hint-setup">Set up in chat</button> <button id="rfd-hint-dismiss" aria-label="Dismiss compute reminder">×</button>`;
  generation.append(hint);
  if (local || !hostCapabilities.message) document.getElementById('rfd-hint-setup').textContent = 'Show chat request';
  action('rfd-setup', () => setupCompute());
  action('rfd-hint-setup', () => setupCompute());
  action('rfd-check', () => compute(true));
  action('rfd-stop', () => setupCompute(computeState.selection?.machine_id, 'stop'));
  action('rfd-disconnect', async () => {
    const session = activeSession;
    const result = await tool('disconnect_compute', {session_id: session, expected_revision: computeState.selection.revision});
    if (session !== activeSession) return;
    invalidate(); message(result.detail); await compute();
  });
  action('rfd-drafts-refresh', drafts);
  document.getElementById('rfd-hint-dismiss').onclick = () => { hintDismissed = true; hint.hidden = true; };
  document.getElementById('rfd-existing').ontoggle = e => { if (e.target.open) registeredTargets().catch(error => message(error.message)); };
  setInterval(() => { if (!document.hidden) { void compute(); void pollRun(); } }, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { void compute(); void pollRun(); } });
  for (const id of ["rfd-note", "rfd-samples", "rfd-seed", "rfd-thinking", "rfd-backbone-noise", "rfd-latent-noise"]) document.getElementById(id).oninput = () => {
    document.getElementById('rfd-generation-origin').hidden = true;
    invalidate(); queueDraft();
  };
  document.getElementById("rfd-image").onchange = e => {
    void attachImage(e.target.files[0]).catch(error => message(error.message));
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
    watchedRun = {jobId: plan.snapshot_id, session: activeSession, epoch: editEpoch};
    return ask(`Generate the reviewed RFD4 design using execute_rfd4_plan with plan_id ${plan.snapshot_id} and plan_checksum ${plan.plan_checksum}. Use this exact saved plan (${plan.samples} designs, seed ${plan.seed}, ${plan.instance}).`);
  });
  action("rfd-runs-refresh", refreshRuns);
  await compute().catch((e) => message(e.message));
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
    if (!job) return; // The chat may still be waiting for execution approval.
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
