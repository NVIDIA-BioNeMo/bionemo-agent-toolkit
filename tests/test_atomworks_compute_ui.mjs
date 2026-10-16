import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements = new Map();
globalThis.window = {localToken:'test'};
globalThis.addEventListener = () => {};
globalThis.document = {getElementById(id) { if(!elements.has(id)) elements.set(id,{dataset:{},textContent:'',hidden:false}); return elements.get(id); }};
const {compute} = await import('../integrations/atomworks-studio/host/bridge.js');
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
test('a failed refresh cannot cause a probe on every status poll',async()=>{
  const calls=responses([{state:'registered',name:'GPU',kind:'ssh',fingerprint:'failure'},new Error('offline'),{state:'registered',name:'GPU',kind:'ssh',fingerprint:'failure'}]);
  await compute();
  assert.equal(elements.get('rfd-compute-label').textContent,'Disconnected');
  await compute();
  assert.deepEqual(calls,['get_compute_status','check_compute','get_compute_status']);
});
test('overlapping polls share the existing in-flight request',async()=>{
  let finish;let count=0;
  globalThis.fetch=()=>{count++;return new Promise(resolve=>{finish=()=>resolve({json:async()=>({structuredContent:{state:'ready',name:'GPU',kind:'ssh',fingerprint:'overlap'}})});});};
  const first=compute(); await compute(); finish(); await first;
  assert.equal(count,1);
});
