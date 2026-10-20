import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map(), radios=['low','medium','high'].map(value=>({value,checked:value==='high'})), saves=[];
globalThis.window={localToken:'test'};
globalThis.addEventListener=()=>{};
globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
globalThis.document={body:{inert:false},getElementById(id){if(!elements.has(id))elements.set(id,{value:'1'});return elements.get(id);},querySelector:()=>radios.find(r=>r.checked),querySelectorAll:()=>radios};
globalThis.fetch=async(url,options)=>{const request=JSON.parse(options.body);if(request.name==='save_draft')saves.push(request.arguments);return {json:async()=>({structuredContent:{draft_id:'saved',snapshot_checksum:'a'.repeat(64),session_id:'copy',state:'unregistered'}})};};
const {nativeFileNavigation,studioEvent,saveDraft,attachImage}=await import('../integrations/atomworks-studio/host/bridge.js');
async function prepare(){studioEvent('selected','old');document.getElementById('rfd-note').value='old structure note';document.getElementById('rfd-image').value='old.png';document.getElementById('rfd-seed').value='99';document.getElementById('rfd-samples').value='3';await attachImage({type:'image/png',size:1,arrayBuffer:async()=>new Uint8Array([1]).buffer});}
test('fresh file saves old metadata and resets new-document metadata before autosave',async()=>{
 await prepare();
 await nativeFileNavigation(async request=>{request.beginCommit();studioEvent('ready','new');},{freshDocument:true});
 assert.equal(saves.at(-1).session_id,'old');assert.equal(saves.at(-1).note,'old structure note');assert.equal(saves.at(-1).image_base64,'AQ==');
 await saveDraft();const current=saves.at(-1);assert.equal(current.session_id,'new');assert.equal(current.note,'');assert.equal(current.image_base64,null);assert.equal(current.settings.seed,42);assert.equal(current.settings.samples,1);assert.equal(current.settings.generation.thinking,'medium');assert.equal(document.getElementById('rfd-image').value,'');
});
test('failed preparation leaves the existing metadata intact',async()=>{
 await prepare();await assert.rejects(nativeFileNavigation(async()=>{throw Error('bad CIF');},{freshDocument:true}),/bad CIF/);
 await saveDraft();assert.equal(saves.at(-1).note,'old structure note');assert.equal(saves.at(-1).image_base64,'AQ==');assert.equal(saves.at(-1).settings.seed,99);
});
test('combine keeps the current document notes image and settings',async()=>{
 await prepare();await nativeFileNavigation(async request=>{request.beginCommit();studioEvent('changed','old');});
 await saveDraft();assert.equal(saves.at(-1).note,'old structure note');assert.equal(saves.at(-1).image_base64,'AQ==');assert.equal(saves.at(-1).settings.seed,99);
});

test('combine preparation uses a copied saved session and lost outcome leaves old document selected',async()=>{
 await prepare();let destination;
 await assert.rejects(nativeFileNavigation(async request=>{destination=await request.copySavedSession();throw Error('combine response lost');}),/response lost/);
 assert.equal(destination,'copy');await saveDraft();assert.equal(saves.at(-1).session_id,'old');
 assert.equal(saves.at(-1).note,'old structure note');assert.equal(document.body.inert,false);
});
