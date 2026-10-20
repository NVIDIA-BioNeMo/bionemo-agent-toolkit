import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
import {navigationRequest} from '../integrations/atomworks-studio/host/navigation-request.js';
const source = readFileSync(new URL('../integrations/atomworks-studio/host/bridge.js', import.meta.url),'utf8').replace(/^import \{navigationRequest\} from '\.\/navigation-request\.js';\n/, '').replace(/^import \{connectSavedCompute\} from '\.\/compute-connection\.js';\n/m,'').replace(/export \{[^}]+\};/, '').replace(/export (?=(?:async )?function)/g, '');
function harness() {
  const elements = new Map();
  const el = () => ({dataset:{}, querySelector:()=>null, append(){}, remove(){}, setAttribute(){}, add(){}, value:'0'});
  const context = vm.createContext({navigationRequest,window:{}, addEventListener(){}, clearTimeout(){}, setTimeout(){}, Option:function(){}, document:{createElement:el,getElementById(id){if(!elements.has(id)) elements.set(id,el());return elements.get(id);}}});
  vm.runInContext(source + `
    activeSession='input'; editEpoch=1;
    watchedRun={jobId:'job',session:'input',epoch:1};
    var calls=[], opened=[], state='completed', hook=()=>{}, refreshed=0;
    tool=async(name,args)=>{calls.push(name);await hook(name); if(name==='get_workspace') return {jobs:state==='absent'?[]:[{job_id:'job',status:state}]}; if(name==='check_rfd4_job') return {job_id:'job',status:state}; if(name==='list_results')return {designs:[{index:0}]}; if(name==='open_run_structure')return {session_id:'result'};};
    refreshRuns=async()=>{refreshed++;await hook('refresh');};
    document.getElementById('rfd-runs').querySelector=()=>document.createElement('div');
    saveDraft=async()=>{await hook('save');};
    openStudioSession=async id=>{opened.push(id);};
  `,context);
  return {context, run:code=>vm.runInContext(code,context)};
}
test('completed run retrieves and opens once',async()=>{const h=harness();await h.run('pollRun()');await h.run('pollRun()');assert.equal(h.run('opened.length'),1);assert.equal(h.run('watchedRun'),null);});
test('approval pending and running do not load',async()=>{for(const state of ['absent','running']){const h=harness();h.context.state=state;await h.run('pollRun()');assert.equal(h.run('opened.length'),0);assert.ok(h.run('watchedRun'));}});
test('failed job stops polling',async()=>{const h=harness();h.context.state='failed';await h.run('pollRun()');assert.equal(h.run('watchedRun'),null);assert.equal(h.run('opened.length'),0);});
test('edits or navigation preserve current structure',async()=>{for(const change of ['editEpoch++',"activeSession='other'"]){const h=harness();h.run(change);await h.run('pollRun()');assert.equal(h.run('opened.length'),0);}});
test('edits during retrieval, saving or import prevent replacement',async()=>{for(const stage of ['list_results','save','open_run_structure']){const h=harness();h.context.hook=async name=>{if(name===stage)h.run('editEpoch++');};await h.run('pollRun()');assert.equal(h.run('opened.length'),0);}});
test('new submission during refresh remains watched',async()=>{const h=harness();h.context.hook=async name=>{if(name==='refresh')h.run("watchedRun={jobId:'new',session:'input',epoch:1}");};await h.run('pollRun()');assert.equal(h.run('watchedRun.jobId'),'new');assert.equal(h.run('opened.length'),0);});
test('transient retrieval failure retries without resubmission',async()=>{const h=harness();let fail=true;h.context.hook=async name=>{if(name==='list_results'&&fail){fail=false;throw Error('offline');}};await h.run('pollRun()');assert.ok(h.run('watchedRun'));await h.run('pollRun()');assert.equal(h.run('opened.length'),1);assert.equal(h.run("calls.includes('execute_rfd4_plan')"),false);});
test('concurrent polls do not duplicate retrieval',async()=>{const h=harness();await h.run('Promise.all([pollRun(),pollRun()])');assert.equal(h.run('opened.length'),1);});
