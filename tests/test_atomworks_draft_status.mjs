import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map();
globalThis.window={localToken:'test'};globalThis.addEventListener=()=>{};
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{value:'1',dataset:{}});return elements.get(id);},querySelector:()=>({value:'medium'})};
globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
const {saveDraft,studioEvent,saveBeforeRestore,compute}=await import('../integrations/atomworks-studio/host/bridge.js');
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

test('explicit draft restore can recover expired session but not other save failures',async()=>{
 studioEvent('selected','expired');
 globalThis.fetch=async()=>({json:async()=>({isError:true,content:[{type:'text',text:'EDITOR_SESSION_EXPIRED: Restore a saved draft.'}]})});
 assert.equal(await saveBeforeRestore(),true);
 globalThis.fetch=async()=>({json:async()=>({isError:true,content:[{type:'text',text:'Disk full'}]})});
 await assert.rejects(saveBeforeRestore(),/Disk full/);
});

test('compute fingerprint changes do not discard a current save acknowledgment',async()=>{
 studioEvent('selected','compute-save');
 globalThis.fetch=async()=>({json:async()=>({structuredContent:{state:'ready',fingerprint:'before'}})});
 await compute();
 const p=await pendingSave();
 globalThis.fetch=async()=>({json:async()=>({structuredContent:{state:'ready',fingerprint:'after'}})});
 await compute();p.finish();await p.pending;
 assert.equal(elements.get('rfd-draft-status').textContent,'Draft saved');
});
