import assert from 'node:assert/strict';
import {test} from 'node:test';
globalThis.window={localToken:'test'};
globalThis.addEventListener=()=>{};
const {studioFetch}=await import('../integrations/atomworks-studio/host/bridge.js');
test('successful temporary-session cleanup preserves bodyless 204 response',async()=>{
 let called;
 globalThis.fetch=async(_url,options)=>{called=JSON.parse(options.body);return {json:async()=>({structuredContent:{status:204,text:'',content_type:'text/plain'}})};};
 const r=await studioFetch('/api/v1/sessions/temporary',{method:'DELETE'});
 assert.equal(r.status,204);assert.equal(r.body,null);assert.equal(await r.text(),'');
 assert.deepEqual(called.arguments,{method:'DELETE',path:'/api/v1/sessions/temporary'});
});
test('ordinary editor response content remains intact',async()=>{
 globalThis.fetch=async()=>({json:async()=>({structuredContent:{status:200,text:'{"revision":1}',content_type:'application/json'}})});
 const r=await studioFetch('/api/v1/sessions/existing');assert.deepEqual(await r.json(),{revision:1});
});
