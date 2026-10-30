import assert from 'node:assert/strict';
import {test} from 'node:test';
globalThis.window={localToken:'test'};globalThis.addEventListener=()=>{};
globalThis.document={body:{inert:false}};
const {nativeFileNavigation,beginNavigation}=await import('../integrations/atomworks-studio/host/bridge.js');
test('native open supersedes pending host preparation and blocks competing navigation',async()=>{
 const previous=beginNavigation();let finish;
 const pending=nativeFileNavigation(()=>new Promise(r=>{finish=r;}));
 while(!finish)await Promise.resolve();
 assert.equal(previous(),false);assert.equal(document.body.inert,true);
 assert.throws(beginNavigation,/Wait for/);
 await assert.rejects(nativeFileNavigation(async()=>{}),/Wait for/);
 finish('opened');assert.equal(await pending,'opened');assert.equal(document.body.inert,false);
});
test('native file failure releases editing and permits next navigation',async()=>{
 await assert.rejects(nativeFileNavigation(async()=>{throw Error('parse failed');}),/parse failed/);
 assert.equal(document.body.inert,false);assert.equal(beginNavigation()(),true);
});
test('native preparation timeout revokes queued commit before unlocking',async()=>{
 const original=setTimeout;let expire,request,finish;
 globalThis.setTimeout=fn=>{expire=fn;return 0;};
 try {
  const pending=nativeFileNavigation(r=>{request=r;return new Promise(resolve=>{finish=resolve;});});
  while(!request)await Promise.resolve();
  const rejected=assert.rejects(pending,/timed out before replacement/);expire();await rejected;
  assert.equal(document.body.inert,false);assert.equal(request.current(),false);assert.equal(request.signal.aborted,true);
  assert.throws(request.beginCommit,/design changed/);finish(false);
 } finally {globalThis.setTimeout=original;}
});
test('native commit deadline does not unlock a viewer still replacing the structure',async()=>{
 const original=setTimeout;let expire,finish;const message={};
 document.getElementById=()=>message;
 globalThis.setTimeout=fn=>{expire=fn;return 0;};
 try {
  const pending=nativeFileNavigation(r=>{r.beginCommit();return new Promise(resolve=>{finish=resolve;});});
  while(!finish)await Promise.resolve();expire();
  assert.equal(document.body.inert,true);assert.match(message.textContent,/still replacing/);
  finish(true);await pending;assert.equal(document.body.inert,false);
 } finally {globalThis.setTimeout=original;}
});
test('an edit finishing during draft save prevents native replacement',async()=>{
 const elements=new Map();let finish,opened=false;
 document.getElementById=id=>{if(!elements.has(id))elements.set(id,{value:'1'});return elements.get(id);};
 document.querySelector=()=>({value:'medium'});
 const {studioEvent}=await import('../integrations/atomworks-studio/host/bridge.js');
 studioEvent('selected','source');
 globalThis.fetch=()=>new Promise(resolve=>{finish=()=>resolve({json:async()=>({structuredContent:{draft_id:'saved'}})});});
 const pending=nativeFileNavigation(async()=>{opened=true;});
 while(!finish)await Promise.resolve();
 studioEvent('changed','source');finish();
 await assert.rejects(pending,/design changed/);
 assert.equal(opened,false);assert.equal(document.body.inert,false);
});
