import path from 'node:path';
import { build } from 'esbuild';
import { readFile, writeFile, readdir, access } from 'node:fs/promises';
const result = await build({entryPoints:['ui/app.js'],bundle:true,write:false,metafile:true,minify:true,format:'iife',target:'es2022',platform:'browser',legalComments:'inline',loader:{'.html':'text','.glsl':'text','.jpg':'dataurl','.png':'dataurl'}});
const js=result.outputFiles[0].text.replace(/<\/script/gi,'<\\/script');
const css=(await readFile('node_modules/molstar/build/viewer/molstar.css','utf8')).replace(/\/\*# sourceMappingURL=.*?\*\//g,'');
if (/url\((?!data:)/i.test(css)) throw Error('Viewer CSS contains an external asset');
let html=await readFile('ui/index.html','utf8');
html=html.replace('/*MOLSTAR_CSS*/',()=>css).replace('/*APP_JS*/',()=>js);
await writeFile('assets/studio.html',html);
console.log(`Built self-contained viewer: ${(html.length/1024/1024).toFixed(2)} MiB; no iframe or external scripts.`);

const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.includes('node_modules')) continue;
  let dir = path.dirname(path.resolve(input));
  while (dir.includes('node_modules')) {
    try {
      const pkg = JSON.parse(await readFile(path.join(dir,'package.json'),'utf8'));
      if (pkg.name && pkg.version) { packages.set(`${pkg.name}@${pkg.version}`,{dir,pkg}); break; }
    } catch {}
    dir=path.dirname(dir);
  }
}
let notices = 'Third-party code bundled in assets/studio.html.\nGenerated from the esbuild input manifest.\n';
for (const [name,{dir,pkg}] of [...packages].sort(([a],[b])=>a.localeCompare(b))) {
  notices += `\n${'='.repeat(72)}\n${name} | Declared license: ${JSON.stringify(pkg.license)}\n`;
  const files=(await readdir(dir)).filter(f=>/^(licen[cs]e|copying|notice)(\.|$)/i.test(f));
  if (!files.length) throw Error(`Missing license file for bundled package ${name}`);
  for (const file of files) notices += `\n--- ${file} ---\n${await readFile(path.join(dir,file),'utf8')}\n`;
}
await writeFile('THIRD_PARTY_NOTICES.txt',notices.split(/\r?\n/).map(line=>line.trimEnd()).join('\n').trimEnd()+'\n');
console.log(`Included license notices for ${packages.size} bundled packages.`);
