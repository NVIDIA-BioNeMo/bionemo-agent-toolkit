import path from "node:path";
import { readFile, writeFile, readdir } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { build } from "esbuild";
const root = path.resolve(process.env.ATOMWORKS_STUDIO_SOURCE || "../../../atomworks-studio");
const pin = "648cfe3905d1f1893c0c37d2cc4b8eea942a5616";
if (execFileSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).trim() !== pin) throw Error("Use the pinned Studio v0.1.0 checkout");
execFileSync("git", ["-C", root, "diff", "--exit-code", "HEAD", "--", "packages/web"]);
const web = path.join(root, "packages/web"), bridge = path.resolve("host/bridge.js");
const wasm = (await readFile(path.join(web, "src/wasm/annotation_studio_core_bg.wasm"))).toString("base64");
function replaceOnce(s, from, to) {
  if (s.split(from).length !== 2) throw Error(`Upstream hook changed: ${from}`);
  return s.replace(from, to);
}
const adapter = { name: "studio-host-adapter", setup(b) {
  b.onResolve({ filter: /annotation_studio_core\.js$/ }, () => ({ path: path.join(web, "src/wasm/annotation_studio_core.js") }));
  b.onResolve({ filter: /^\.\/patinae$/ }, () => ({ path: "patinae-disabled", namespace: "host" }));
  b.onLoad({ filter: /.*/, namespace: "host" }, () => ({ contents: 'export function createPatinaeAdapter(){throw Error("Patinae is not included in this embedded build. Choose Mol*.")}' }));
  b.onResolve({ filter: /^h264-mp4-encoder$/ }, () => ({ path: "mp4", namespace: "mp4-disabled" }));
  b.onLoad({ filter: /.*/, namespace: "mp4-disabled" }, () => ({ contents: 'export function createH264MP4Encoder(){throw Error("MP4 export is not available in the embedded editor")}' }));
  b.onLoad({ filter: /\.scss$/ }, () => ({ contents: "", loader: "css" }));
  b.onLoad({ filter: /packages\/web\/src\/.*\.ts$/ }, async (a) => {
    let s = await readFile(a.path, "utf8");
    if (a.path === path.join(web, "src/api.ts")) {
      s = `import {studioFetch} from ${JSON.stringify(bridge)};
` + s;
      s = replaceOnce(s, "await fetch(versionedApiPath(path),", "await studioFetch(versionedApiPath(path),");
    }
    if (a.path === path.join(web, "src/studio/session-file-controller.ts")) {
      s = replaceOnce(s, "      URL.revokeObjectURL(anchor.href);", "      setTimeout(() => URL.revokeObjectURL(anchor.href), 60000);");
    }
    if (a.path === path.join(web, "src/main.ts")) {
      s = `import {studioEvent} from ${JSON.stringify(bridge)};
` + s;
      s = replaceOnce(s, '  const parentOrigin = query.get("parent_origin");', '  studioEvent(type, sessionId);\n  const parentOrigin = query.get("parent_origin");');
      s = replaceOnce(s, '    onOpened: (response) => runViewerUpdate(async () => {', '    onOpened: openSessionFromHost = (response) => runViewerUpdate(async () => {');
      s = 'let openSessionFromHost: ((response: SessionResponse) => Promise<void>) | null = null;\n' + s;
      s = replaceOnce(s, "await initCifCore();", `await initCifCore({module_or_path:Uint8Array.from(atob('${wasm}'), c=>c.charCodeAt(0))});`);
    }
    if (a.path === path.join(web, "src/main.ts")) s += `
window.addEventListener('rfd-open-session', (event) => { const id = (event as CustomEvent<string>).detail; void (async()=>{ const response = await api<SessionResponse>('/api/sessions/'+id); if (!openSessionFromHost) throw Error('Studio is still starting'); element('analysis-results').replaceChildren(); await openSessionFromHost(response); window.dispatchEvent(new CustomEvent('rfd-session-opened',{detail:{id}})); })().catch(error=>{log(String(error)); window.dispatchEvent(new CustomEvent('rfd-session-opened',{detail:{id,error:String(error)}}));}); });`;
    if (/\b(localStorage|sessionStorage)\b/.test(s)) {
      s = `import {storage as embeddedStorage} from ${JSON.stringify(bridge)};
` + s;
      s = s.replace(/\b(localStorage|sessionStorage)\b/g, "embeddedStorage");
    }
    return { contents: s, loader: "ts", resolveDir: path.dirname(a.path) };
  });
} };
const entry = `import {initialize} from ${JSON.stringify(bridge)}; initialize().then(()=>import(${JSON.stringify(path.join(web, "src/main.ts"))})).catch(e=>{document.body.textContent='Studio could not start: '+e.message});`;
const result = await build({ stdin: { contents: entry, resolveDir: process.cwd() }, bundle: true, write: false, metafile: true, outdir: "out", minify: true, format: "iife", target: "es2022", platform: "browser", nodePaths: [path.resolve("node_modules")], plugins: [adapter], define: { "import.meta.env.PROD": "false", "process.env.NODE_ENV": '"production"' }, loader: { ".glsl": "text", ".jpg": "dataurl", ".png": "dataurl" }, legalComments: "inline" });
const js = result.outputFiles.find((f) => f.path.endsWith(".js")).text.replace(/<\/script/gi, "<\\/script");
const css = result.outputFiles.filter((f) => f.path.endsWith(".css")).map((f) => f.text).join("\n") + "\n" + await readFile("node_modules/molstar/build/viewer/molstar.css", "utf8");
let html = await readFile(path.join(web, "index.html"), "utf8");
html = html.replace(/<script[^>]*src="[^"]*"[^>]*><\/script>/g, "").replace(/<link[^>]*>/g, "");
html = html.replaceAll("./annotation-studio.svg", "data:image/svg+xml;base64," + (await readFile(path.join(web, "public/annotation-studio.svg"))).toString("base64"));
html = html.replace('<option value="patinae">', '<option disabled value="patinae">');
html = html.replace('href="/guide/"', 'href="https://github.com/RosettaCommons/atomworks-studio/blob/v0.1.0/docs/WEB.md" target="_blank" rel="noopener noreferrer"');
html = html.replace("</head>", () => `<style>${css}
#rfd-generation{flex:none;padding:10px 14px;background:#18191c;border-bottom:1px solid #444;font:12px system-ui} .rfd-generation-row{display:flex;gap:14px;align-items:end}.rfd-generation-row>label{display:grid;gap:5px;flex:1}.rfd-generation-row fieldset{border:0;padding:0;margin:0;flex:2}.rfd-generation-row legend{margin-bottom:6px}.rfd-generation-row fieldset label{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;background:#24262b;border:1px solid #41444c;border-radius:5px;margin-right:5px;cursor:pointer}.rfd-generation-row fieldset label:has(input:checked){border-color:#7094ff;background:#273558}.rfd-generation-row input[type=number]{width:100%;box-sizing:border-box;background:#24262b;color:inherit;border:1px solid #41444c;padding:6px;border-radius:4px}#rfd-generation details{margin:9px 0;padding:7px;background:#24262b;border:1px solid #41444c;border-radius:4px}.rfd-sampling{display:flex;gap:20px;padding-top:10px}.rfd-sampling label{flex:1}.rfd-sampling input{display:block;width:100%;accent-color:#4a80ff}.rfd-sampling output{float:right}#rfd-review{width:100%;background:#2864ed;color:white;border:0;padding:8px;border-radius:4px}#rfd-review:disabled{opacity:.5}@media(max-width:600px){.rfd-generation-row{flex-wrap:wrap}.rfd-generation-row fieldset{flex-basis:100%}.rfd-sampling{flex-direction:column}}#rfd-host{flex:none;padding:8px 12px;border-top:1px solid #555;font:12px system-ui;max-height:38vh;overflow:auto}.rfd-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}#rfd-compute-detail,#rfd-message{font-size:11px;margin:4px 0;color:#bac1cc}#rfd-host input{max-width:220px}#rfd-host label{display:inline-flex;gap:6px;margin:5px}#rfd-chat-prompt{width:100%;height:90px}#rfd-host [hidden]{display:none}</style></head>`);
html = html.replace("</body>", () => `<script>/*LOCAL_CONFIG*/<\/script><script>${js}<\/script></body>`);
await writeFile("assets/studio-upstream.html", html);
await writeFile("assets/studio-upstream.provenance.json", JSON.stringify({ repository: "https://github.com/RosettaCommons/atomworks-studio", tag: "v0.1.0", commit: pin, hooks: ["API transport", "session events", "in-memory storage", "inline CIF WASM", "Molstar-only renderer", "disable PWA", "reuse upstream file opening", "defer download URL cleanup"], sourceEdited: false }, null, 2) + "\n");
await writeFile("assets/STUDIO_LICENSE.md", await readFile(path.join(root, "LICENSE.md")));
console.log(`Built upstream Studio ${(html.length / 1024 / 1024).toFixed(2)} MiB from ${pin}. Source unmodified.`);
const packages = /* @__PURE__ */ new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.includes("node_modules")) continue;
  let dir = path.dirname(path.resolve(input));
  while (dir.includes("node_modules")) {
    try {
      const pkg = JSON.parse(await readFile(path.join(dir, "package.json"), "utf8"));
      if (pkg.name && pkg.version) {
        packages.set(`${pkg.name}@${pkg.version}`, { dir, pkg });
        break;
      }
    } catch {
    }
    dir = path.dirname(dir);
  }
}
let notices = "Third-party code bundled in assets/studio.html.\nGenerated from the esbuild input manifest.\n";
for (const [name, { dir, pkg }] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
  notices += `
${"=".repeat(72)}
${name} | Declared license: ${JSON.stringify(pkg.license)}
`;
  const files = (await readdir(dir)).filter((f) => /^(licen[cs]e|copying|notice)(\.|$)/i.test(f));
  if (!files.length) throw Error(`Missing license file for bundled package ${name}`);
  for (const file of files) notices += `
--- ${file} ---
${await readFile(path.join(dir, file), "utf8")}
`;
}
await writeFile("assets/studio-upstream.NOTICES.txt", notices.split(/\r?\n/).map((line) => line.trimEnd()).join("\n").trimEnd() + "\n");
console.log(`Included license notices for ${packages.size} bundled packages.`);
