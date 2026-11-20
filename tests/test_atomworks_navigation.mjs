import assert from 'node:assert/strict';
import {test} from 'node:test';
const elements=new Map();
globalThis.window={localToken:'test'};globalThis.addEventListener=()=>{};
globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
globalThis.setTimeout=()=>1;globalThis.clearTimeout=()=>{};
const {beginNavigation,studioEvent}=await import('../integrations/atomworks-studio/host/bridge.js');
test('new navigation supersedes a delayed earlier request',()=>{
 studioEvent('selected','a');const old=beginNavigation(),current=beginNavigation();
 assert.equal(old(),false);assert.equal(current(),true);
});
test('edits cancel pending navigation',()=>{
 studioEvent('selected','b');const current=beginNavigation();studioEvent('changed','b');assert.equal(current(),false);
});
test('session changes cancel pending navigation',()=>{
 studioEvent('selected','c');const current=beginNavigation();studioEvent('selected','d');assert.equal(current(),false);
});
