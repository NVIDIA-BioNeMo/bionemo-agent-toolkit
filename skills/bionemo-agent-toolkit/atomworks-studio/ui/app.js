import { MolecularViewer } from "./viewer.js";
const $ = (id) => document.getElementById(id), viewer = new MolecularViewer();
let sequence = 0, session = null, summary = null, selected = [], picked = null, selectionEpoch = 0, plan = null, imageNote = null, connected = false;
const pending = /* @__PURE__ */ new Map(), local = Boolean(window.localToken);
function status(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}
function rpc(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++sequence, timer = setTimeout(() => {
      pending.delete(id);
      reject(Error("No host response. Check status before retrying."));
    }, 12e4);
    pending.set(id, { resolve, reject, timer });
    parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
  });
}
addEventListener("message", (event) => {
  if (event.source !== parent || event.data?.jsonrpc !== "2.0") return;
  const m = event.data, p = pending.get(m.id);
  if (p) {
    clearTimeout(p.timer);
    pending.delete(m.id);
    m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result);
  }
});
async function tool(name, args = {}) {
  if (!connected) throw Error("The interface has not connected yet.");
  const result = local ? await fetch("/api/tools", { method: "POST", headers: { "Content-Type": "application/json", "X-RFD4-Token": window.localToken }, body: JSON.stringify({ name, arguments: args }) }).then((r) => r.json()) : await rpc("tools/call", { name, arguments: args });
  if (result.isError) throw Error(result.content?.find((x) => x.type === "text")?.text || result.error || "Tool failed");
  return result.structuredContent ?? JSON.parse(result.content?.find((x) => x.type === "text")?.text || "{}");
}
function action(id, fn) {
  $(id).onclick = async () => {
    const b = $(id);
    b.disabled = true;
    try {
      await fn();
    } catch (e) {
      status(e.message, true);
    } finally {
      b.disabled = false;
      updateSelectionControls();
    }
  };
}
function invalidate() {
  plan = null;
  $("review").hidden = true;
}
function updateSelectionControls() {
  for (const id of ["hotspot", "remove-hotspot", "sequence", "coordinate"]) $(id).disabled = !selected.length;
}
function clearSelection() {
  selectionEpoch++;
  selected = [];
  picked = null;
  viewer.select([]);
  $("selection").textContent = "Click the structure or select a residue below.";
  updateSelectionControls();
  renderResidues();
}
async function select(index, label) {
  const epoch = ++selectionEpoch, current = session;
  const resolved = await tool("resolve_selection", { session_id: current, atom_indices: [index], scope: $("scope").value });
  if (epoch !== selectionEpoch || current !== session) return;
  picked = { index, label };
  selected = resolved.atom_indices;
  viewer.select(selected);
  $("selection").textContent = `${label} \xB7 ${selected.length} atom(s) selected`;
  updateSelectionControls();
  renderResidues();
}
function renderResidues() {
  const host = $("residues");
  host.replaceChildren();
  for (const chain of summary?.sequence || []) {
    for (const r of chain.items) {
      if (r.kind !== "residue") continue;
      const b = document.createElement("button");
      b.textContent = `${chain.chain_id}:${r.code}${r.residue_id}`;
      b.title = `${r.residue_name} \xB7 ${(r.conditions || []).join(", ")}`;
      b.classList.toggle("hotspot", (r.conditions || []).includes("hotspot"));
      b.classList.toggle("selected", (r.atom_indices || []).some((i) => selected.includes(i)));
      b.onclick = () => select(r.atom_indices[0], b.textContent).catch((e) => status(e.message, true));
      host.append(b);
    }
  }
}
async function openStructure(value) {
  invalidate();
  session = value.session_id;
  summary = value.structure;
  selected = [];
  picked = null;
  selectionEpoch++;
  await viewer.load(value.cif, summary);
  $("structure-name").textContent = value.title || value.result_file || "Molecular design";
  $("note").value = "";
  imageNote = null;
  $("image-note").value = "";
  $("image-preview").hidden = true;
  $("prepare").disabled = false;
  clearSelection();
  status(value.description || `Loaded ${summary.atom_count} atoms. Select a residue to edit its instructions.`);
}
async function annotate(condition, enabled = true) {
  if (!selected.length) return;
  const result = await tool("set_condition", { session_id: session, atom_indices: selected, condition, enabled, expected_revision: summary.revision });
  summary = result.structure;
  invalidate();
  await viewer.color(summary);
  viewer.select(selected);
  renderResidues();
  status(`${enabled ? "Applied" : "Removed"} ${condition} for ${selected.length} atoms. Review the updated design before generating.`);
}
function showPlan(value) {
  plan = value;
  $("review").hidden = false;
  $("plan-summary").textContent = `${value.samples} design(s), seed ${value.seed}, on ${value.instance}. Saved input ${value.sha256.slice(0, 12)}. Later molecular edits require another review.`;
  $("warnings").textContent = (value.issues || []).map((i) => i.message).join("\n");
  $("request").textContent = local ? "Generate on Brev" : "Ask Codex to generate";
}
async function refresh() {
  const value = await tool("get_workspace");
  $("run-list").replaceChildren();
  for (const job of value.jobs) {
    const row = document.createElement("div");
    row.className = "run";
    const label = document.createElement("span");
    label.textContent = `${job.job_id.slice(0, 8)} \xB7 ${job.status}`;
    row.append(label);
    const check = document.createElement("button");
    check.textContent = "Check";
    check.onclick = async () => {
      check.disabled = true;
      try {
        await tool("check_rfd4_job", { job_id: job.job_id });
        await refresh();
      } catch (e) {
        status(e.message, true);
      } finally {
        check.disabled = false;
      }
    };
    row.append(check);
    if (job.status === "completed") {
      const view = document.createElement("button");
      view.textContent = "View design";
      view.onclick = async () => {
        view.disabled = true;
        try {
          status("Retrieving generated design\u2026");
          await openStructure(await tool("open_result", { job_id: job.job_id }));
        } catch (e) {
          status(e.message, true);
        } finally {
          view.disabled = false;
        }
      };
      row.append(view);
    }
    $("run-list").append(row);
  }
  if (!value.jobs.length) $("run-list").textContent = "Your generated structures will appear here.";
}
action("demo", async () => {
  status("Loading the prepared PD-L1 example\u2026");
  await openStructure(await tool("load_demo"));
});
action("clear", clearSelection);
action("reset", () => viewer.reset());
action("hotspot", () => annotate("hotspot"));
action("remove-hotspot", () => annotate("hotspot", false));
action("sequence", () => annotate("sequence"));
action("coordinate", () => annotate("coordinate"));
$("scope").onchange = () => {
  if (picked) select(picked.index, picked.label).catch((e) => status(e.message, true));
};
$("file").onchange = async () => {
  try {
    const f = $("file").files[0];
    if (!f) return;
    if (f.size > 2e7) throw Error("Use a CIF under 20 MB");
    await openStructure(await tool("import_structure", { cif: await f.text() }));
  } catch (e) {
    status(e.message, true);
  }
};
$("image-note").onchange = async () => {
  try {
    imageNote = null;
    $("image-preview").hidden = true;
    const f = $("image-note").files[0];
    if (!f) return;
    if (f.size > 1e7 || f.type !== "image/png") throw Error("Use a PNG under 10 MB");
    const data = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = reject;
      r.readAsDataURL(f);
    });
    imageNote = data.split(",")[1];
    $("image-preview").src = data;
    $("image-preview").hidden = false;
    invalidate();
  } catch (e) {
    status(e.message, true);
  }
};
for (const id of ["note", "samples", "seed"]) $(id).oninput = invalidate;
action("prepare", async () => {
  status("Validating the molecular conditions\u2026");
  showPlan(await tool("prepare_design", { session_id: session, note: $("note").value, samples: Number($("samples").value), seed: Number($("seed").value), image_base64: imageNote }));
  status("Design validated and saved. Ready to generate on Brev.");
});
action("request", async () => {
  if (!plan) return;
  if (local) {
    if (!confirm(`Generate ${plan.samples} design(s) on ${plan.instance}? This uses GPU time.`)) return;
    const job = await tool("execute_rfd4_plan", { plan_id: plan.snapshot_id, plan_checksum: plan.plan_checksum });
    status(`Run ${job.job_id.slice(0, 8)}: ${job.status}. Refresh Runs for progress.`);
    await refresh();
  } else {
    const result = await rpc("ui/message", { role: "user", content: [{ type: "text", text: `Generate the reviewed RFD4 design using execute_rfd4_plan with plan_id ${plan.snapshot_id} and plan_checksum ${plan.plan_checksum}. Use this exact saved plan (${plan.samples} designs, seed ${plan.seed}, ${plan.instance}).` }] });
    if (result?.isError) throw Error("The host did not accept the request");
    status("Generation requested in the conversation.");
  }
});
action("refresh", refresh);
async function init() {
  if (local) {
    connected = true;
    $("mode").textContent = "Local development preview \xB7 same bundled interface as the MCP app";
  } else {
    if (parent === window) throw Error("Run the local preview server or open this through the plugin.");
    await rpc("ui/initialize", { appInfo: { name: "RFD4 Design Studio", version: "0.2.0" }, appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] }, protocolVersion: "2026-01-26" });
    connected = true;
    parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, "*");
    $("mode").textContent = "Embedded app";
  }
  await viewer.initialize($("viewer"), (index, label) => select(index, label).catch((e) => status(e.message, true)));
  await refresh();
  await openStructure(await tool("load_demo"));
}
init().catch((e) => status(e.message, true));
