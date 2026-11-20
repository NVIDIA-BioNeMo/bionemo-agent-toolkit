import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map();
globalThis.window={localToken:'test'};
globalThis.addEventListener=()=>{};
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
const {attachImage,studioEvent}=await import('../integrations/atomworks-studio/host/bridge.js');
function file(){let resolve;const promise=new Promise(r=>resolve=r);return {value:{size:1,type:'image/png',arrayBuffer:()=>promise},finish:()=>resolve(new Uint8Array([42]).buffer)};}
test('upload from previous session is discarded',async()=>{
 studioEvent('selected','a');const f=file();const pending=attachImage(f.value);
 studioEvent('selected','b');f.finish();assert.equal(await pending,false);
});
test('reverse completion keeps only newest upload',async()=>{
 studioEvent('selected','c');const a=file(),b=file();
 const first=attachImage(a.value),second=attachImage(b.value);
 b.finish();assert.equal(await second,true);a.finish();assert.equal(await first,false);
});
test('clearing a file supersedes pending upload',async()=>{
 studioEvent('selected','d');const f=file();const pending=attachImage(f.value);
 await attachImage(undefined);f.finish();assert.equal(await pending,false);
});
test('accepted completion invalidates review made during upload',async()=>{
 studioEvent('selected','e');const f=file();const pending=attachImage(f.value);
 elements.get('rfd-plan').hidden=false;f.finish();assert.equal(await pending,true);
 assert.equal(elements.get('rfd-plan').hidden,true);
});
