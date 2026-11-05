import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../integrations/atomworks-studio/host/bridge.js',import.meta.url),'utf8')
  .replace(/^import .*;\n/gm,'').replace(/export \{[^}]+\};/,'').replace(/export (?=(?:async )?function)/g,'');
function harness() {
 const elements=new Map(),calls=[];
 const values={'rfd-note':'saved notes','rfd-samples':'1','rfd-seed':'42','rfd-backbone-noise':'0.3','rfd-latent-noise':'0.1'};
 const document={getElementById(id){if(!elements.has(id))elements.set(id,{value:values[id],hidden:true});return elements.get(id);},querySelector(){return {value:'medium'};}};
 const c=vm.createContext({window:{},document,addEventListener(){}});vm.runInContext(source,c);
 c.transport=async(name,args)=>{calls.push({name,args});return {request_id:'a'.repeat(32),sha256:'b'.repeat(64),samples:1,seed:42,generation:{thinking:'medium',backbone_noise:0.3,latent_noise:0.1},issues:[{message:'Missing atoms warning'}]};};
 vm.runInContext("tool=transport; activeSession='editor';",c);
 return {calls,elements,c,run:code=>vm.runInContext(code,c)};
}
test('review freezes a request without querying any compute',async()=>{
 const h=harness();await h.run('reviewDesign()');
 assert.deepEqual(h.calls.map(x=>x.name),['prepare_design_request']);
 assert.match(h.elements.get('rfd-plan-text').textContent,/Missing atoms warning/);
 assert.equal(h.elements.get('rfd-plan').hidden,false);
});
test('failed chat handoff keeps saved request and never starts watching a submitted job',async()=>{
 const h=harness();await h.run('reviewDesign()');h.c.deliver=async()=>false;h.run('ask=deliver');
 await h.run('generateDesign()');
 assert.equal(h.run('watchedRun'),null);assert.equal(h.run('plan.request_id'),'a'.repeat(32));
});
test('repeated Generate uses the same immutable request identity',async()=>{
 const h=harness();await h.run('reviewDesign()');const messages=[];
 h.c.deliver=async text=>{messages.push(text);return true;};h.run('ask=deliver');
 await h.run('generateDesign()');await h.run('generateDesign()');
 assert.equal(messages[0],messages[1]);assert.equal(h.calls.length,1);
 assert.equal(h.run('watchedRun.jobId'),'a'.repeat(32));
});
test('edits during review cannot expose a stale request',async()=>{
 const h=harness();h.c.transport=async()=>{h.run('invalidate()');return {};};h.run('tool=transport');
 await assert.rejects(h.run('reviewDesign()'),/changed during review/);
 assert.equal(h.run('plan'),null);
});
