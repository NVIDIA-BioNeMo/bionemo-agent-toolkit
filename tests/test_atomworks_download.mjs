import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../integrations/atomworks-studio/host/bridge.js',import.meta.url),'utf8')
  .replace(/^import \{navigationRequest\} from '\.\/navigation-request\.js';\n/,'')
  .replace(/export \{[^}]+\};/,'').replace(/export (?=(?:async )?function)/g,'');
function harness({local=false,capability=true,result={}}={}) {
 const calls=[],anchors=[],blobs=[],timers=[],revoked=[];
 const context=vm.createContext({window:local?{localToken:'fixture'}:{},addEventListener(){},Blob,Uint8Array,atob,
   setTimeout(fn){timers.push(fn);},document:{createElement(){const a={click(){anchors.push(a);}};return a;}},
   URL:{createObjectURL(blob){blobs.push(blob);return 'blob:fixture';},revokeObjectURL(url){revoked.push(url);}}});
 vm.runInContext(source,context);
 context.reply=async(method,params)=>{calls.push({method,params});if(result instanceof Error)throw result;return result;};
 vm.runInContext(`rpc=reply;hostCapabilities=${JSON.stringify(capability?{downloadFile:{}}:{})}`,context);
 return {calls,anchors,blobs,timers,revoked,run:file=>{context.file=file;return vm.runInContext('downloadFile(file)',context);}};
}
test('embedded CIF uses inline text resource and waits for host acceptance',async()=>{
 const h=harness();await h.run({filename:'design annotated.cif',mimeType:'chemical/x-mmcif',text:'data_科学\n'});
 assert.equal(h.calls[0].method,'ui/download-file');
 assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].params)),{contents:[{type:'resource',resource:{uri:'file:///design%20annotated.cif',mimeType:'chemical/x-mmcif',text:'data_科学\n'}}]});
 assert.equal(h.anchors.length,0);assert.equal(h.blobs.length,0);
});
test('embedded ZIP preserves base64 without creating a browser blob',async()=>{
 const h=harness();await h.run({filename:'results.zip',mimeType:'application/zip',base64:'UEsDBA=='});
 assert.equal(h.calls[0].params.contents[0].resource.blob,'UEsDBA==');assert.equal(h.blobs.length,0);
});
test('unsupported or rejected host never falls back to a sandbox download',async()=>{
 for(const options of [{capability:false},{result:{isError:true}},{result:null},{result:new Error('Host denied')}]){
  const h=harness(options);await assert.rejects(h.run({filename:'x.cif',mimeType:'chemical/x-mmcif',text:'x'}));
  assert.equal(h.anchors.length,0);assert.equal(h.blobs.length,0);
  if(options.capability===false)assert.equal(h.calls.length,0);
 }
});
test('local preview retains browser CIF and ZIP download with delayed URL cleanup',async()=>{
 for(const file of [{filename:'x.cif',mimeType:'chemical/x-mmcif',text:'data_科学'}, {filename:'x.zip',mimeType:'application/zip',base64:'UEsDBA=='}]){
  const h=harness({local:true,capability:false});await h.run(file);
  assert.equal(h.calls.length,0);assert.equal(h.anchors[0].download,file.filename);assert.equal(h.revoked.length,0);
  if(file.text)assert.equal(await h.blobs[0].text(),file.text);
  else assert.deepEqual([...new Uint8Array(await h.blobs[0].arrayBuffer())],[80,75,3,4]);
  h.timers[0]();assert.deepEqual(h.revoked,['blob:fixture']);
 }
});
test('ambiguous contents are refused before host or browser effects',async()=>{
 const h=harness();await assert.rejects(h.run({filename:'x',mimeType:'text/plain',text:'x',base64:'eA=='}));assert.equal(h.calls.length,0);
});
test('resource filename retains spaces and letter x while removing separators',async()=>{
 const h=harness();await h.run({filename:'x folder/a\\b\u0000.cif',mimeType:'chemical/x-mmcif',text:'x'});
 assert.equal(h.calls[0].params.contents[0].resource.uri,'file:///x%20folder_a_b_.cif');
});
test('download waits for host confirmation',async()=>{
 let accept;const response=new Promise(resolve=>{accept=resolve;});const h=harness({result:response});let completed=false;
 const pending=h.run({filename:'x.cif',mimeType:'chemical/x-mmcif',text:'x'}).then(()=>{completed=true;});
 await Promise.resolve();assert.equal(completed,false);accept({});await pending;assert.equal(completed,true);
});
test('ordinary example filename remains unchanged',async()=>{
 const h=harness();await h.run({filename:'example.cif',mimeType:'chemical/x-mmcif',text:'x'});
 assert.equal(h.calls[0].params.contents[0].resource.uri,'file:///example.cif');
});
