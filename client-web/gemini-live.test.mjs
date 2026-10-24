import test from 'node:test';
import assert from 'node:assert/strict';
import { liveSettings } from './gemini-live.js';

test('Live is explicit and needs Google consent outside Private mode', () => {
  assert.equal(liveSettings('general', true, false).allowed, false);
  assert.equal(liveSettings('gemini-live', false, false).allowed, false);
  assert.equal(liveSettings('gemini-live', true, true).allowed, false);
  assert.equal(liveSettings('gemini-live', true, false).allowed, true);
  assert.match(liveSettings('gemini-live', true, false).notice, /audio.*video.*Google/);
});
