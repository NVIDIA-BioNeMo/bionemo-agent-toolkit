import assert from 'node:assert/strict';
import {test} from 'node:test';
const listeners=new Map(),timers=new Map(),elements=new Map();let serial=0,opened;
globalThis.window={localToken:'test'};
globalThis.document={body:{inert:false},getElementById(id){if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
globalThis.addEventListener=(name,fn)=>{if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);};
globalThis.removeEventListener=(name,fn)=>listeners.get(name)?.delete(fn);
globalThis.CustomEvent=class{constructor(type,options){this.type=type;this.detail=options.detail;}};
globalThis.dispatchEvent=e=>{if(e.type==='rfd-open-session')opened=e.detail;for(const fn of listeners.get(e.type)||[])fn(e);};
globalThis.setTimeout=fn=>{timers.set(++serial,fn);return serial;};globalThis.clearTimeout=id=>timers.delete(id);
const {openStudioSession}=await import('../integrations/atomworks-studio/host/bridge.js');
const complete=(request,error)=>dispatchEvent(new CustomEvent('rfd-session-opened',{detail:{id:request.id,requestId:request.requestId,error}}));
test('timeout revokes late precommit replacement',async()=>{
 const pending=openStudioSession('a',()=>true),request=opened;
 const failure=assert.rejects(pending,/timed out/);timers.get(serial)();await failure;
 assert.equal(document.body.inert,false);assert.equal(request.current(),false);assert.throws(request.beginCommit,/design changed/);
});
test('timeout during commit keeps editing locked until completion',async()=>{
 const pending=openStudioSession('b',()=>true),request=opened;request.beginCommit();
 timers.get(serial)();assert.equal(document.body.inert,true);
 assert.match(elements.get('rfd-message').textContent,/still replacing/);
 complete(request);await pending;assert.equal(document.body.inert,false);
});
test('same-session retry ignores previous attempt acknowledgment',async()=>{
 const first=openStudioSession('c',()=>true),old=opened;
 const failure=assert.rejects(first,/timed out/);timers.get(serial)();await failure;
 const second=openStudioSession('c',()=>true),current=opened;
 complete(old);await Promise.resolve();assert.equal(document.body.inert,true);
 current.beginCommit();complete(current);await second;assert.equal(document.body.inert,false);
});
