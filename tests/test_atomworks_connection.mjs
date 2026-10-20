import assert from 'node:assert/strict';
import {test} from 'node:test';
import {connectSavedCompute} from '../integrations/atomworks-studio/host/compute-connection.js';

function harness({connected=true, result={state:'ready',transport:'reachable'}, failure}={}) {
  const calls=[], frames=[], accepted=[];
  let live=true;
  const args={targetId:'saved-brev',session:'draft-session',current:()=>live,
    saveDraft:async()=>{calls.push(['save_draft']);},
    tool:async(name, value)=>{
      calls.push([name,value]);
      if (failure?.name===name) throw Error(failure.message);
      if(name==='get_compute_status')return {selection:{revision:7}};
      if(name==='select_compute')return {state:'ready',name:'A100',kind:'brev',gpu:'cached GPU',transport:'reachable',checked_at:'old',selection:{machine_id:'saved-brev',revision:8}};
      if(name==='inspect_compute_target')return {connected};
      if(name==='refresh_selected_compute_access')return {state:'succeeded'};
      if(name==='check_compute')return result;
      throw Error('Unexpected tool '+name);
    },render:state=>frames.push(state),accept:state=>accepted.push(state)};
  return {args,calls,frames,accepted,leave:()=>{live=false;}};
}
test('Connect preserves the draft, selects the exact saved target, then verifies live readiness',async()=>{
  const h=harness();await connectSavedCompute(h.args);
  assert.deepEqual(h.calls.map(c=>c[0]),['save_draft','get_compute_status','select_compute','inspect_compute_target','check_compute']);
  assert.deepEqual(h.calls[2][1],{target_id:'saved-brev',session_id:'draft-session',expected_revision:7});
  assert.deepEqual(h.frames.map(f=>f.state),['connecting','connecting','checking']);
  assert.ok(h.frames.every(f=>!f.gpu && !f.checked_at));
  assert.ok(h.frames.filter(f=>f.state==='connecting').every(f=>f.transport!=='reachable'));
  assert.equal(h.accepted[0].state,'ready');
});
for (const [reason,state] of [['missing runtime','needs_setup'],['missing weights','needs_setup'],['expired authentication','disconnected'],['stopped machine','disconnected'],['unknown host key','disconnected']]) {
  test(reason+' never becomes Ready or invokes a provisioning/recovery command',async()=>{
    const h=harness({connected:state==='needs_setup',result:{state,detail:reason}});
    await connectSavedCompute(h.args);
    assert.equal(h.accepted[0].state,state);
    assert.equal(h.accepted[0].detail,reason);
    assert.ok(h.frames.every(f=>f.state!=='ready'));
    assert.ok(h.calls.every(([name])=>! /recover|start|create|setup|ownership/.test(name)));
    assert.ok(h.calls.filter(([name])=>name==='refresh_selected_compute_access').length<=1);
  });
}
test('failed connection still refreshes authoritative readiness instead of exposing cached Ready',async()=>{
  const h=harness({connected:false,result:{state:'disconnected'}});
  await connectSavedCompute(h.args);
  assert.ok(h.calls.some(([name])=>name==='check_compute'));
  assert.ok(h.frames.every(f=>f.state==='connecting'));
});
test('unconfigured Brev access uses one session-bound refresh before a strict recheck',async()=>{
  const h=harness({connected:false});
  await connectSavedCompute(h.args);
  assert.deepEqual(h.calls.filter(c=>c[0]==='refresh_selected_compute_access'),[['refresh_selected_compute_access',{session_id:'draft-session',expected_revision:8}]]);
  assert.equal(h.calls.filter(c=>c[0]==='inspect_compute_target').length,2);
});
test('rejected first-use or changed key stops without retrying or invoking readiness',async()=>{
  const h=harness({connected:false,failure:{name:'refresh_selected_compute_access',message:'Host key verification failed'}});
  await assert.rejects(connectSavedCompute(h.args),/Host key/);
  assert.equal(h.calls.at(-1)[0],'refresh_selected_compute_access');
  assert.equal(h.accepted.length,0);
});
test('switching documents after a response prevents retargeting the new document',async()=>{
  for(const boundary of ['get_compute_status','select_compute','inspect_compute_target','check_compute']) {
    const h=harness();const original=h.args.tool;
    h.args.tool=async(...args)=>{const result=await original(...args);if(args[0]===boundary)h.leave();return result;};
    await connectSavedCompute(h.args);
    assert.equal(h.accepted.length,0);
    assert.equal(h.calls.at(-1)[0],boundary);
    assert.ok(h.calls.filter(c=>c[0]==='select_compute').every(c=>c[1].session_id==='draft-session'));
  }
});
test('failed selection never probes or silently falls back to another machine',async()=>{
  const h=harness({failure:{name:'select_compute',message:'Selection changed'}});
  await assert.rejects(connectSavedCompute(h.args),/Selection changed/);
  assert.equal(h.calls.at(-1)[0],'select_compute');assert.equal(h.accepted.length,0);
});
