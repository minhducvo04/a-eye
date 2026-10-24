import { test } from 'node:test';
import assert from 'node:assert/strict';
import { triggerClient } from './trigger.js';

test('wake starts listening once, acknowledges it, and leaves camera off', async () => {
  const state = { camera: false, listening: false, spoken: [] };
  const requests = [];
  let next;
  const stop = triggerClient({
    session: () => 's', available: () => true, listening: () => state.listening,
    request: async (_, body) => {
      requests.push(body);
      return { wake: { id: 'one', line: 'Keys are in the bowl.' } };
    },
    wake: async line => { state.listening = true; state.spoken.push(line); },
    timer: fn => { next = fn; },
  });
  await new Promise(resolve => setImmediate(resolve));
  await next();
  stop();
  assert.equal(state.camera, false);
  assert.deepEqual(state.spoken, ['Keys are in the bowl.']);
  assert.equal(requests[1].ack, 'one');
  assert.equal(requests[1].listening, true);
});
