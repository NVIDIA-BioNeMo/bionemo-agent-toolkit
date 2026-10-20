import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map(),radios=['low','medium','high'].map(value=>({value,checked:value==='medium'})),saves=[],requests=[];
const events=new EventTarget();
globalThis.window={localToken:'fixture'};
globalThis.addEventListener=events.addEventListener.bind(events);
globalThis.removeEventListener=events.removeEventListener.bind(events);
globalThis.dispatchEvent=events.dispatchEvent.bind(events);
globalThis.document={body:{inert:false},getElementById(id){
 if(!elements.has(id))elements.set(id,{value:'',hidden:true,dataset:{}});return elements.get(id);
},querySelector:()=>radios.find(r=>r.checked),querySelectorAll:()=>radios};
globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
globalThis.fetch=async(url,options)=>{const request=JSON.parse(options.body);
 if(request.name==='save_draft')saves.push(request.arguments);
 return {json:async()=>({structuredContent:request.name==='get_compute_status'?{state:'unregistered',selection:{revision:0}}:{draft_id:request.arguments.session_id}})};
};
addEventListener('rfd-open-session',event=>requests.push(event.detail));
const {openStudioSession,studioEvent,saveDraft,beginNavigation}=await import('../integrations/atomworks-studio/host/bridge.js');
const settings={samples:3,seed:321,generation:{thinking:'high',backbone_noise:0.2,latent_noise:0.4}};
const metadata=(source,note)=>({source,note,image_base64:'iVBORw0KGgo=',settings});
async function finish(token,source){
 token.beginCommit();studioEvent('ready',token.id);
 // Saving before the viewer acknowledgement must already use the new metadata.
 await saveDraft();const saved=saves.at(-1);
 assert.equal(saved.session_id,token.id);assert.equal(saved.note,source.note);
 assert.equal(saved.image_base64,source.image_base64);
 dispatchEvent(new CustomEvent('rfd-session-opened',{detail:{id:token.id,requestId:token.requestId}}));
 return saved;
}
test('result applies its metadata at ready before any new-session save',async()=>{
 studioEvent('selected','previous');document.getElementById('rfd-note').value='unrelated old note';
 const value=metadata('saved_run','actual result note');
 const opening=openStudioSession('result',beginNavigation(),value);
 const saved=await finish(requests.at(-1),value);await opening;
 assert.deepEqual(saved.settings,settings);assert.equal(document.body.inert,false);
 assert.match(document.getElementById('rfd-generation-origin').textContent,/Saved run settings/);
});
test('draft restore independently applies metadata before new-session save',async()=>{
 studioEvent('selected','old');const value=metadata('saved_draft','restored draft note');
 const opening=openStudioSession('restored',beginNavigation(),value);
 await finish(requests.at(-1),value);await opening;
 assert.equal(document.getElementById('rfd-generation-origin').hidden,true);
});
test('failed load before commit leaves current metadata intact',async()=>{
 studioEvent('selected','keep');document.getElementById('rfd-note').value='keep this note';
 const opening=openStudioSession('bad-result',beginNavigation(),metadata('saved_run','wrong'));
 const token=requests.at(-1);
 dispatchEvent(new CustomEvent('rfd-session-opened',{detail:{id:token.id,requestId:token.requestId,error:'load failed'}}));
 await assert.rejects(opening,/load failed/);await saveDraft();
 assert.equal(saves.at(-1).session_id,'keep');assert.equal(saves.at(-1).note,'keep this note');
});
test('rapid switching rejects a delayed earlier result before replacing metadata',async()=>{
 studioEvent('selected','start');const old=beginNavigation(),current=beginNavigation();
 await assert.rejects(openStudioSession('old-result',old,metadata('saved_run','old')),/design changed/);
 const value=metadata('saved_run','new result');const opening=openStudioSession('new-result',current,value);
 await finish(requests.at(-1),value);await opening;
 assert.equal(saves.at(-1).note,'new result');
});
test('draft restore supersedes delayed result and its metadata',async()=>{
 studioEvent('selected','start');const delayed=beginNavigation();
 const value=metadata('saved_draft','newest restored draft');
 const opening=openStudioSession('draft',beginNavigation(),value);
 await finish(requests.at(-1),value);await opening;
 await assert.rejects(openStudioSession('late-result',delayed,metadata('saved_run','stale')),/design changed/);
 await saveDraft();assert.equal(saves.at(-1).session_id,'draft');assert.equal(saves.at(-1).note,value.note);
});
test('legacy missing metadata clears unrelated note image and settings',async()=>{
 studioEvent('selected','old');const value={source:'unavailable',note:'',image_base64:null,settings:null};
 const opening=openStudioSession('legacy',beginNavigation(),value);
 const saved=await finish(requests.at(-1),value);await opening;
 assert.equal(saved.settings.samples,1);assert.equal(saved.settings.seed,42);
 assert.equal(saved.settings.generation.thinking,'medium');
 assert.match(document.getElementById('rfd-generation-origin').textContent,/no verified saved metadata/);
});
test('invalid metadata fails before navigation or changing current values',async()=>{
 studioEvent('selected','safe');document.getElementById('rfd-note').value='safe';const count=requests.length;
 for (const invalid of [{...settings,seed:-1},0,false,''])
  await assert.rejects(openStudioSession('invalid',beginNavigation(),{...metadata('saved_run','bad'),settings:invalid}),/settings are invalid/);
 assert.equal(requests.length,count);assert.equal(document.getElementById('rfd-note').value,'safe');assert.equal(document.body.inert,false);
});
