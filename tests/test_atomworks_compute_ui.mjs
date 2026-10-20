import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements = new Map();
globalThis.window = {localToken:'test'};
globalThis.addEventListener = () => {};
globalThis.document = {getElementById(id) { if(!elements.has(id)) elements.set(id,{dataset:{},textContent:'',hidden:false}); return elements.get(id); }};
const {compute, studioEvent} = await import('../integrations/atomworks-studio/host/bridge.js');
function responses(values) {
  const calls=[];
  globalThis.fetch=async (_url, options) => {
    calls.push(JSON.parse(options.body).name);
    const value=values.shift();
    if(value instanceof Error) throw value;
    return {json:async()=>({structuredContent:value})};
  };
  return calls;
}
test('stale evidence refreshes itself and shows Ready', async()=>{
  const calls=responses([{state:'registered',name:'GPU',kind:'ssh',fingerprint:'stale'},{state:'ready',name:'GPU',kind:'ssh',fingerprint:'stale'}]);
  await compute();
  assert.deepEqual(calls,['get_compute_status','check_compute']);
  assert.equal(elements.get('rfd-compute-label').textContent,'Ready');
});
test('opening the app does not probe unconfigured or freshly checked compute',async()=>{
  const calls=responses([{state:'unregistered'},{state:'ready',name:'GPU',kind:'ssh',fingerprint:'fresh'}]);
  await compute();await compute();
  assert.deepEqual(calls,['get_compute_status','get_compute_status']);
});
test('ownership-required status explains the gate and offers no stop or automatic probe',async()=>{
  const calls=responses([{state:'ownership_required',name:'GPU',kind:'brev',power:'running',selection:{machine_id:'machine'},detail:'Review this installation ownership in chat.'}]);
  await compute();
  assert.deepEqual(calls,['get_compute_status']);
  assert.equal(elements.get('rfd-compute-label').textContent,'Ownership needed');
  assert.equal(elements.get('rfd-compute-detail').textContent,'Review this installation ownership in chat.');
  assert.equal(elements.get('rfd-stop').hidden,true);
});
test('a failed refresh cannot cause a probe on every status poll',async()=>{
  const calls=responses([{state:'registered',name:'GPU',kind:'ssh',fingerprint:'failure'},new Error('offline'),{state:'registered',name:'GPU',kind:'ssh',fingerprint:'failure'}]);
  await compute();
  assert.equal(elements.get('rfd-compute-label').textContent,'Not connected');
  await compute();
  assert.deepEqual(calls,['get_compute_status','check_compute','get_compute_status']);
});
test('overlapping polls share the existing in-flight request',async()=>{
  let finish;let count=0;
  globalThis.fetch=()=>{count++;return new Promise(resolve=>{finish=()=>resolve({json:async()=>({structuredContent:{state:'ready',name:'GPU',kind:'ssh',fingerprint:'overlap'}})});});};
  const first=compute(); await compute(); finish(); await first;
  assert.equal(count,1);
});
test('stop review appears only for running Brev and blocks active work',async()=>{
  responses([
    {state:'ready',name:'GPU',kind:'brev',power:'running',selection:{machine_id:'machine'},fingerprint:'stop-review'},
    {state:'ready',name:'GPU',kind:'brev',power:'running',selection:{machine_id:'machine'},active_jobs:['run'],fingerprint:'stop-review'},
    {state:'ready',name:'GPU',kind:'ssh',power:'unknown',selection:{machine_id:'machine'},fingerprint:'ssh-stop'}
  ]);
  await compute();
  assert.equal(elements.get('rfd-stop').hidden,false);
  assert.equal(elements.get('rfd-stop').disabled,false);
  assert.equal(elements.get('rfd-stop').textContent,'Show stop request');
  await compute();assert.equal(elements.get('rfd-stop').disabled,true);
  await compute();assert.equal(elements.get('rfd-stop').hidden,true);
});

test('late failed check cannot overwrite the newly opened session',async()=>{
  studioEvent('selected','old-session');
  let rejectRequest;
  globalThis.fetch=()=>new Promise((_resolve,reject)=>{rejectRequest=reject;});
  const pending=compute();
  studioEvent('selected','new-session');
  elements.get('rfd-compute-label').textContent='New session';
  rejectRequest(new Error('Old machine unavailable'));
  await pending;
  assert.equal(elements.get('rfd-compute-label').textContent,'New session');
});
