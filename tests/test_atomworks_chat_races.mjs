import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map();
globalThis.window={localToken:'test'};globalThis.addEventListener=()=>{};
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
const {sendScopedChat,studioEvent}=await import('../integrations/atomworks-studio/host/bridge.js');
for(const outcome of ['success','reject','timeout'])test('late chat '+outcome+' does not alter another session',async()=>{
 studioEvent('selected','a');let resolve,reject,calls=0;
 const pending=sendScopedChat('request',()=>{calls++;return new Promise((a,b)=>{resolve=a;reject=b;});});
 studioEvent('selected','b');document.getElementById('rfd-message').textContent='Current session';
 if(outcome==='success')resolve({});else reject(Error(outcome));
 assert.equal(await pending,false);assert.equal(calls,1);
 assert.equal(elements.get('rfd-message').textContent,'Current session');
});
test('same-session rejected delivery remains actionable',async()=>{
 studioEvent('selected','c');await assert.rejects(sendScopedChat('request',async()=>({isError:true})),/Host did not accept/);
});
