let seq = 0, activeSession = null, plan = null, imageNote = null, editEpoch = 0;
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
  if (type === "changed" || type === "ready") invalidate();
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
  if (local) {
    const box = document.getElementById("rfd-chat-prompt");
    box.hidden = false;
    box.value = text;
    box.focus();
    box.select();
    message("Local preview: copy this request into chat. In the embedded app, this action sends it to the conversation.");
    return;
  }
  const result = await rpc("ui/message", { role: "user", content: [{ type: "text", text }] });
  if (result?.isError) throw Error("Host did not accept the chat request");
  message("Request sent to the conversation.");
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
async function compute(check = false) {
  const c = await tool(check ? "check_compute" : "get_compute_status");
  document.getElementById("rfd-compute").textContent = c.state === "unregistered" ? "Compute: not configured" : `${c.name} \xB7 ${c.kind} \xB7 ${c.state.replaceAll("_", " ")}`;
  document.getElementById("rfd-compute-detail").textContent = [c.detail, c.gpu, c.checked_at ? `Last checked ${new Date(c.checked_at).toLocaleString()}` : ""].filter(Boolean).join(" \xB7 ");
}
async function initialize() {
  if (!local) {
    await rpc("ui/initialize", { appInfo: { name: "AtomWorks Studio for RFD4", version: "0.3.0" }, appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] }, protocolVersion: "2026-01-26" });
    parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, "*");
  }
  storage.setItem("annotation-studio-viewer-v2", "molstar");
  storage.setItem("annotation-studio-pending-example", "protein_binder");
  const bar = document.createElement("section");
  bar.id = "rfd-host";
  bar.innerHTML = `<div class="rfd-row"><strong id="rfd-compute">Checking registration\u2026</strong><button id="rfd-setup">Set up compute in chat</button><button id="rfd-check">Check readiness</button><button id="rfd-refresh">Refresh registration</button><button id="rfd-review" disabled>Review design</button></div><div id="rfd-compute-detail"></div><details><summary>Design notes and generation settings</summary><label>Notes <input id="rfd-note" placeholder="Describe what you want to design"></label><label>Image note (PNG) <input id="rfd-image" type="file" accept="image/png"></label><label>Thinking <select id="rfd-thinking"><option>low</option><option selected>medium</option><option>high</option></select></label><label>Backbone noise <input id="rfd-backbone-noise" type="number" min="0.01" max="1" step="0.01" value="0.3"></label><label>Sequence / side-chain latent noise <input id="rfd-latent-noise" type="number" min="0.01" max="1" step="0.01" value="0.1"></label><label>Designs <input id="rfd-samples" type="number" min="1" max="16" value="1"></label><label>Seed <input id="rfd-seed" type="number" min="0" value="42"></label><p>Image notes accompany the design. Molecular annotations determine the model's constraints.</p></details><div id="rfd-plan" hidden><span id="rfd-plan-text"></span> <button id="rfd-generate">Generate in chat</button></div><details><summary>Runs</summary><button id="rfd-runs-refresh">Refresh runs</button><div id="rfd-runs"></div></details><p id="rfd-message" role="status"></p><textarea id="rfd-chat-prompt" aria-label="Request to copy into chat" hidden readonly></textarea>`;
  document.querySelector(".app-shell").append(bar);
  action("rfd-setup", () => ask("Help me set up compute to run RFD4. First check the registered target and existing access. Offer a local Linux GPU, an existing SSH host (including a connected Brev machine), or a new Brev machine. Use the Brev CLI skill for Brev provisioning, showing the machine and hourly cost before creation. Use the existing upstream RFD4 setup skill; do not create a new skill. Register the chosen target with register_rfd4_compute, then run check_compute and report any remaining setup."));
  action("rfd-check", () => compute(true));
  action("rfd-refresh", () => compute());
  for (const id of ["rfd-note", "rfd-samples", "rfd-seed", "rfd-thinking", "rfd-backbone-noise", "rfd-latent-noise"]) document.getElementById(id).oninput = invalidate;
  document.getElementById("rfd-image").onchange = async (e) => {
    invalidate();
    imageNote = null;
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 1e7 || f.type !== "image/png") {
      message("Use a PNG under 10 MB.");
      return;
    }
    const bytes = new Uint8Array(await f.arrayBuffer());
    let binary = "";
    for (const v of bytes) binary += String.fromCharCode(v);
    imageNote = btoa(binary);
  };
  action("rfd-review", async () => {
    const epoch = editEpoch;
    const p = await tool("prepare_design", { session_id: activeSession, note: document.getElementById("rfd-note").value, samples: Number(document.getElementById("rfd-samples").value), seed: Number(document.getElementById("rfd-seed").value), image_base64: imageNote, generation: { thinking: document.getElementById("rfd-thinking").value, backbone_noise: Number(document.getElementById("rfd-backbone-noise").value), latent_noise: Number(document.getElementById("rfd-latent-noise").value) } });
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
