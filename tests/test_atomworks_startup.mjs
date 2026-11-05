import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../integrations/atomworks-studio/host/bridge.js', import.meta.url), 'utf8')
  .replace(/^import .*;\n/gm, '')
  .replace(/export \{[^}]+\};/, '')
  .replace(/export (?=(?:async )?function)/g, '');

function harness({embedded = true, localToken} = {}) {
  const messages = [], timers = new Map();
  let receive, timerId = 0;
  const window = {localToken};
  const parent = embedded ? {} : window;
  parent.postMessage = message => messages.push(message);
  const context = vm.createContext({
    window, parent,
    addEventListener(type, listener) { if (type === 'message') receive = listener; },
    setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(source, context);
  return {
    messages, timers,
    run: code => vm.runInContext(code, context),
    respond(data, sender = parent) { receive({source: sender, data}); },
  };
}

test('RPC ignores its own request echo and waits for an actual response', async () => {
  const h = harness({embedded: false});
  const result = h.run("rpc('ui/initialize', {})");
  const request = h.messages[0];
  h.respond(request);
  assert.equal(h.run('pending.size'), 1);
  assert.equal(h.timers.size, 1);
  h.respond({jsonrpc: '2.0', id: request.id, result: {hostCapabilities: {message: {}}}});
  assert.deepEqual(await result, {hostCapabilities: {message: {}}});
  assert.equal(h.timers.size, 0);
});

test('RPC ignores notifications, incomplete replies and messages from other sources', async () => {
  const h = harness();
  const result = h.run("rpc('tools/call', {})");
  const {id} = h.messages[0];
  for (const message of [
    {jsonrpc: '2.0', id, method: 'ui/notifications/example'},
    {jsonrpc: '2.0', id, method: 'tools/call', result: 'request'},
    {jsonrpc: '2.0', id},
    {jsonrpc: '1.0', id, result: 'wrong protocol'},
    {jsonrpc: '2.0', id: id + 1, result: 'wrong request'},
  ]) h.respond(message);
  h.respond({jsonrpc: '2.0', id, result: 'wrong source'}, {});
  assert.equal(h.run('pending.size'), 1);
  h.respond({jsonrpc: '2.0', id, result: null});
  assert.equal(await result, null);
});

test('RPC preserves host errors and timeouts', async () => {
  const h = harness();
  const error = h.run("rpc('ui/initialize', {})");
  h.respond({jsonrpc: '2.0', id: h.messages[0].id, error: {code: -32601, message: 'Host unavailable'}});
  await assert.rejects(error, /Host unavailable/);
  const timeout = h.run("rpc('ui/initialize', {})");
  [...h.timers.values()][0]();
  await assert.rejects(timeout, /Host response timed out/);
  assert.equal(h.run('pending.size'), 0);
});

test('standalone HTML gives preview-server instructions before sending any host request', async () => {
  const h = harness({embedded: false});
  await assert.rejects(h.run('initialize()'), /scripts\/preview\.py/);
  assert.equal(h.messages.length, 0);
  assert.equal(h.timers.size, 0);
});

test('local preview skips the MCP host handshake', async () => {
  const h = harness({embedded: false, localToken: 'preview-token'});
  await h.run('initializeHost()');
  assert.equal(h.messages.length, 0);
  assert.equal(h.timers.size, 0);
});

test('embedded startup accepts real capabilities and then notifies the host', async () => {
  const h = harness();
  const startup = h.run('initializeHost()');
  const request = h.messages[0];
  assert.equal(request.method, 'ui/initialize');
  h.respond({jsonrpc: '2.0', id: request.id, result: {hostCapabilities: {message: {}, downloadFile: {}}}});
  await startup;
  assert.deepEqual(h.run('hostCapabilities'), {message: {}, downloadFile: {}});
  assert.equal(h.messages[1].method, 'ui/notifications/initialized');
  assert.equal(h.timers.size, 0);
});

test('embedded startup rejects malformed initialization results without claiming readiness', async () => {
  for (const result of [undefined, null, false, 42, 'invalid', []]) {
    const h = harness();
    const startup = h.run('initializeHost()');
    h.respond({jsonrpc: '2.0', id: h.messages[0].id, result});
    await assert.rejects(startup, /invalid.*initialization response/);
    assert.equal(h.messages.length, 1);
  }
});
