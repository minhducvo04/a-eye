import test from 'node:test';
import assert from 'node:assert/strict';
import { confirmation, createApproval } from './family-note.js';

test('only exact spoken send or Send tap confirms; anything else cancels', () => {
  assert.equal(confirmation(' SEND '), 'send');
  for (const text of ['yes', 'send it', 'no', '', 'do not send']) assert.equal(confirmation(text), 'cancel');
});
test('approval waits for completed read aloud; cancelled drafts cannot send', async () => {
  const calls = [];
  const a = createApproval(async (action, data) => { calls.push([action, data]); return {}; });
  a.start({ id: 'fixture' });
  assert.equal(await a.confirm('send'), false);
  assert.equal(calls[0][1].confirmation, 'cancel');
  a.start({ id: 'fixture2' });
  await a.heard();
  assert.equal(await a.confirm('send'), true);
  assert.equal(await a.confirm('send'), false);
  assert.deepEqual(calls.map(x => x[0]), ['send', 'heard', 'send']);
});
