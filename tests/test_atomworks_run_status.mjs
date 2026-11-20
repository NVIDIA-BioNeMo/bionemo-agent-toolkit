import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';
import {navigationRequest} from '../integrations/atomworks-studio/host/navigation-request.js';
const source=readFileSync(new URL('../integrations/atomworks-studio/host/bridge.js',import.meta.url),'utf8')
  .replace(/^import \{navigationRequest\} from '\.\/navigation-request\.js';\n/,'')
  .replace(/^import \{connectSavedCompute\} from '\.\/compute-connection\.js';\n/m,'').replace(/export \{[^}]+\};/,'').replace(/export (?=(?:async )?function)/g,'');

function harness(jobs, observation) {
  const elements=new Map(),calls=[];
  const element=()=>({dataset:{},children:[],textContent:'',disabled:false,
    append(...items){this.children.push(...items);},replaceChildren(...items){this.children=[...items];}});
  const document={createElement:element,getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);}};
  const context=vm.createContext({navigationRequest,window:{},addEventListener(){},document});
  vm.runInContext(source,context);
  context.transport=async(name,args)=>{
    calls.push({name,args});
    if(name==='get_workspace')return {jobs};
    if(name==='check_rfd4_job'){
      if(observation instanceof Error)throw observation;
      return observation;
    }
    throw Error('Unexpected effect: '+name);
  };
  vm.runInContext('tool=transport',context);
  return {calls,elements,run:code=>vm.runInContext(code,context)};
}

test('Runs shows original machine and queued continuation guidance with no launch action',async()=>{
  const h=harness([{job_id:'job-123456',status:'queued',machine_name:'Dedicated GPU',
    detail:'Ask chat to continue this saved run; do not submit another design.'}]);
  await h.run('refreshRuns()');
  const row=h.elements.get('rfd-runs').children[0];
  assert.equal(row.dataset.jobId,'job-123456');
  assert.match(row.children[0].textContent,/queued.*Dedicated GPU/);
  assert.equal(row.children[1].textContent,'Check status');
  assert.match(row.children[2].textContent,/do not submit another design/);
  assert.deepEqual(h.calls.map(call=>call.name),['get_workspace']);
});

test('Check status presents backend explanation and never executes recovery itself',async()=>{
  const h=harness([{job_id:'job',status:'queued',instance:'original-SSH'}],
    {job_id:'job',status:'queued',detail:'Original worker is unavailable. Continue the saved run in chat.',recovery_action:'recover_queued_rfd4_job'});
  await h.run('refreshRuns()');
  const button=h.elements.get('rfd-runs').children[0].children[1];
  await button.onclick();
  assert.match(h.elements.get('rfd-message').textContent,/Continue the saved run in chat/);
  assert.deepEqual(h.calls.map(call=>call.name),['get_workspace','check_rfd4_job','get_workspace']);
  assert.equal(h.calls[1].args.job_id,'job');assert.equal(button.disabled,false);
});

test('Status transport failure remains visible and check can be retried without a new design',async()=>{
  const h=harness([{job_id:'old',status:'submission_unknown',instance:'original'}],new Error('Trusted SSH access is unavailable'));
  await h.run('refreshRuns()');const button=h.elements.get('rfd-runs').children[0].children[1];
  await button.onclick();
  assert.equal(h.elements.get('rfd-message').textContent,'Trusted SSH access is unavailable');
  assert.equal(button.disabled,false);
  assert.deepEqual(h.calls.map(call=>call.name),['get_workspace','check_rfd4_job']);
});

test('Historical failure remains visible without selecting another machine',async()=>{
  const h=harness([{job_id:'failed',status:'failed',instance:'original',error:'Model exited with code 1'}]);
  await h.run('refreshRuns()');const row=h.elements.get('rfd-runs').children[0];
  assert.match(row.children[0].textContent,/failed.*original/);
  assert.equal(row.children[2].textContent,'Model exited with code 1');
  assert.deepEqual(h.calls.map(call=>call.name),['get_workspace']);
});
