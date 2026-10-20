// Test the actual adapted upstream controller with deterministic API faults.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {build} from 'esbuild';
import {adaptSessionFileController} from './host/studio-source.mjs';
const source=process.env.ATOMWORKS_STUDIO_SOURCE;
if(!source)throw Error('Set ATOMWORKS_STUDIO_SOURCE to the pinned public Studio checkout');
const original=await readFile(path.join(source,'packages/web/src/studio/session-file-controller.ts'),'utf8');
const bundle=await build({stdin:{contents:adaptSessionFileController(original,'host-bridge'),loader:'ts',resolveDir:source},bundle:true,write:false,format:'esm',plugins:[{name:'isolated-dependencies',setup(b){
 b.onResolve({filter:/.*/},a=>({path:a.path,namespace:'fixture'}));
 b.onLoad({filter:/.*/,namespace:'fixture'},a=>({contents:
 a.path.endsWith('/api')?'export class ApiError extends Error{}; export const api=(...args)=>globalThis.harness.api(...args); export const apiText=api;':
 a.path.endsWith('/dom')?'export const element=id=>globalThis.harness.elements.get(id);':
 a.path.endsWith('/confirmation')?'export const confirmAction=async()=>false;':
 a.path.endsWith('/authoring-actions')?'export const prepareCifDownload=async()=>null;':
 a.path.endsWith('/persistence')?'export const PENDING_EXAMPLE_KEY="pending";':
 a.path==='host-bridge'?'export const nativeFileNavigation=()=>{throw Error("Use an explicit test navigation token")};':
 'export const inspect_cif=()=>{};'}));
}}]});
const {SessionFileController}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
class Element {
 constructor(tag='div'){this.tag=tag;this.listeners=new Map();this.children=[];this.value='';this.open=false;}
 addEventListener(type,fn){const list=this.listeners.get(type)||[];list.push(fn);this.listeners.set(type,list);}
 removeEventListener(type,fn){this.listeners.set(type,(this.listeners.get(type)||[]).filter(x=>x!==fn));}
 dispatchEvent(event){for(const fn of this.listeners.get(event.type)||[])fn(event);}
 append(child){child.parentElement=this;this.children.push(child);}
 insertBefore(child){this.append(child);}
 setAttribute(){}
 querySelector(selector){return (this.parts??={})[selector]??=new Element(selector);}
 showModal(){this.open=true;}
 close(value){this.returnValue=value;this.open=false;this.dispatchEvent({type:'close'});}
 remove(){this.removed=true;}
}
function fixture(){
 const h={elements:new Map(),dialogs:[],calls:[],opened:0};
 for(const id of ['file-input','combine-input','parse-preset','import-settings','parse-description'])h.elements.set(id,new Element());
 h.elements.get('parse-preset').value='auto';const parent=new Element();parent.append(h.elements.get('import-settings'));
 globalThis.harness=h;globalThis.document={createElement(tag){const e=new Element(tag);if(tag==='dialog')h.dialogs.push(e);return e;},body:new Element()};
 const controller=new SessionFileController({getSessionId:()=> 'original',onOpened:async()=>h.opened++,log:()=>{},runViewerUpdate:fn=>fn()});controller.openGeneration=1;
 return {h,controller,parent};
}
function token(){let active=true;const abort=new AbortController();return {current:()=>active,signal:abort.signal,expire(){active=false;abort.abort();}};}
const file={text:async()=> 'data_test\n_atom_site.id 1'};
{
 const {h,controller}=fixture();let finish;
 h.api=async(route)=>{h.calls.push(route);if(route==='/api/import/inspect')return new Promise(resolve=>{finish=resolve;});throw Error('Unexpected API '+route);};
 const request=token(),work=controller.performOpen(file,1,null,request);
 for(let i=0;i<20&&!finish;i++)await Promise.resolve();assert.ok(finish);
 request.expire();finish({preset:null,message:'Choose how to import'});
 assert.equal(await work,false);assert.equal(h.dialogs.length,0);assert.equal(h.opened,0);assert.deepEqual(h.calls,['/api/import/inspect']);
}
{
 const {h,controller,parent}=fixture();let mode='ambiguous';
 h.api=async(route)=>{h.calls.push(route);if(route==='/api/import/inspect')return mode==='ambiguous'?{preset:null,message:'Choose'}:{preset:'minimal',message:'Preserve'};
 if(route==='/api/sessions')return {session_id:'replacement',structure:{}};throw Error('Unexpected API '+route);};
 const request=token(),work=controller.performOpen(file,1,null,request);
 for(let i=0;i<30&&!h.dialogs[0]?.open;i++)await Promise.resolve();assert.equal(h.dialogs[0].open,true);request.expire();
 assert.equal(await work,false);assert.equal(h.dialogs[0].open,false);assert.equal(h.dialogs[0].removed,true);
 assert.equal(h.elements.get('import-settings').parentElement,parent);assert.equal(h.opened,0);assert.equal(h.calls.filter(x=>x==='/api/sessions').length,0);
 mode='automatic';controller.openGeneration=2;assert.equal(await controller.performOpen(file,2,null,token()),true);
 assert.equal(h.opened,1);assert.equal(h.calls.filter(x=>x==='/api/sessions').length,1);
}
console.log('Passed actual upstream-controller delayed-inspection expiry, dialog expiry, and successful subsequent import.');
