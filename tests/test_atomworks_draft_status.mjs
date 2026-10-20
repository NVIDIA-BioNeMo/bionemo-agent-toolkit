import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map();
globalThis.window={localToken:'test'};globalThis.addEventListener=()=>{};
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{value:'1'});return elements.get(id);},querySelector:()=>({value:'medium'})};
globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
const {saveDraft,studioEvent}=await import('../integrations/atomworks-studio/host/bridge.js');
async function pendingSave(){let finish;globalThis.fetch=()=>new Promise(resolve=>{finish=()=>resolve({json:async()=>({structuredContent:{draft_id:'saved'}})});});const pending=saveDraft();while(!finish)await Promise.resolve();return {pending,finish};}
test('current save receipt updates status',async()=>{
 studioEvent('selected','a');const p=await pendingSave();p.finish();await p.pending;
 assert.equal(elements.get('rfd-draft-status').textContent,'Draft saved');
});
test('old session save cannot label new session saved',async()=>{
 studioEvent('selected','b');const p=await pendingSave();studioEvent('changed','c');
 p.finish();await p.pending;assert.equal(elements.get('rfd-draft-status').textContent,'Unsaved changes');
});
test('save before newer edits cannot label those edits saved',async()=>{
 studioEvent('selected','d');const p=await pendingSave();studioEvent('changed','d');
 p.finish();await p.pending;assert.equal(elements.get('rfd-draft-status').textContent,'Unsaved changes');
});
