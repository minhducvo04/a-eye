import test from 'node:test';
import assert from 'node:assert/strict';
import { pairMode, pairUrl, pairStatus } from './pair.js';
import { qrMatrix } from './qr.js';

test('pair URL preserves token and mode is explicit', () => {
  assert.deepEqual(pairMode('?pair=0123&token=a%26b'), { camera: true, code: '0123', token: 'a&b' });
  assert.equal(pairMode('').camera, false);
  assert.equal(pairMode('?pair=').camera, true);
  assert.equal(pairUrl('https://demo.test', '/agent.html?pair=0123', '?token=a%26b'), 'https://demo.test/agent.html?pair=0123&token=a%26b');
  assert.equal(pairUrl('https://demo.test', '/agent.html?pair=0123', ''), 'https://demo.test/agent.html?pair=0123');
});
test('status distinguishes call and camera', () => {
  assert.equal(pairStatus({ state: 'joined' }), 'Phone camera connected');
  assert.equal(pairStatus({ state: 'joined' }, true), 'Paired');
  assert.equal(pairStatus({ state: 'camera', camera_on: false }), 'Phone camera off');
  assert.equal(pairStatus({ state: 'expired', detail: 'Code expired.' }), 'Code expired.');
  assert.match(pairStatus({ state: 'left' }), /disconnected/);
});
test('QR dimensions, finder patterns and bounded capacity', () => {
  for (const [text, size] of [['hello', 21], ['https://demo.test/agent.html?pair=0123', 29], ['x'.repeat(106), 37]]) {
    const m = qrMatrix(text);
    assert.equal(m.length, size);
    assert.ok(m.every(row => row.length === size && row.every(v => typeof v === 'boolean')));
    for (const [x, y] of [[0, 0], [size - 7, 0], [0, size - 7]]) {
      for (let dy = 0; dy < 7; dy++) for (let dx = 0; dx < 7; dx++) {
        const d = Math.max(Math.abs(dx - 3), Math.abs(dy - 3));
        assert.equal(m[y + dy][x + dx], d !== 2);
      }
    }
  }
  assert.throws(() => qrMatrix('x'.repeat(107)), /too long/);
});

test('phone entry asks only for camera, streams after joined and stops on disconnect', async () => {
  const { bootPairCamera } = await import('./pair.js');
  const saved = new Map();
  const put = (key, value) => { saved.set(key, Object.getOwnPropertyDescriptor(globalThis, key)); Object.defineProperty(globalThis, key, { configurable: true, value }); };
  const children = [], timers = new Map();
  let stopped = 0, requested;
  function element(tag) {
    return { tag, handlers: {}, style: {}, setAttribute() {}, addEventListener(k, fn) { this.handlers[k] = fn; },
      videoWidth: 640, videoHeight: 480, play: async () => {},
      getContext: () => ({ drawImage() {} }), toDataURL: () => 'data:image/jpeg;base64,c3ludGhldGlj' };
  }
  class Socket {
    static OPEN = 1;
    constructor(url) { this.url = String(url); this.handlers = {}; this.messages = []; this.readyState = 1; this.bufferedAmount = 0; Socket.current = this; }
    addEventListener(k, fn) { this.handlers[k] = fn; }
    send(raw) { this.messages.push(JSON.parse(raw)); }
    close() { this.handlers.close(); }
    message(msg) { this.handlers.message({ data: JSON.stringify(msg) }); }
  }
  put('document', { hidden: false, createElement: element, body: { replaceChildren() { children.length = 0; }, append(...nodes) { children.push(...nodes); } } });
  put('location', { href: 'https://demo.test/agent.html?pair=0123&token=test', search: '?pair=0123&token=test', protocol: 'https:' });
  put('window', { addEventListener() {} });
  put('navigator', { mediaDevices: { getUserMedia: async options => { requested = options; return { getTracks: () => [{ stop() { stopped++; } }] }; } } });
  put('WebSocket', Socket);
  put('setInterval', fn => { timers.set(1, fn); return 1; });
  put('clearInterval', id => timers.delete(id));
  try {
    assert.equal(bootPairCamera(), true);
    const [video, button, status] = children;
    assert.equal(button.textContent, 'Start camera');
    await button.handlers.click();
    assert.equal(requested.audio, false);
    const socket = Socket.current;
    assert.match(socket.url, /token=test/);
    socket.handlers.open();
    assert.equal(socket.messages[0].role, 'camera');
    assert.equal(socket.messages[0].pair_code, '0123');
    timers.get(1)();
    assert.equal(socket.messages.length, 1);
    socket.message({ type: 'pair_status', state: 'joined' });
    assert.equal(status.textContent, 'Paired');
    timers.get(1)();
    assert.equal(socket.messages.at(-1).type, 'frame');
    assert.equal(socket.messages.at(-1).jpeg_b64, 'c3ludGhldGlj');
    await button.handlers.click();
    assert.equal(socket.messages.at(-1).on, false);
    assert.equal(stopped, 1);
    await button.handlers.click();
    assert.equal(socket.messages.at(-1).on, true);
    socket.message({ type: 'pair_status', state: 'left' });
    socket.close();
    assert.equal(stopped, 2);
    assert.equal(video.srcObject, null);
    assert.equal(button.disabled, true);
    assert.equal(timers.size, 0);
    assert.ok(socket.messages.every(msg => ['hello', 'frame', 'camera'].includes(msg.type)));
  } finally {
    for (const [key, descriptor] of saved) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  }
});

test("pair request uses the current session id, not the one at setup time", async () => {
  // Seen in the two-page run: agent.js starts a new session id per call, so a captured id was stale.
  const { setupPairCall } = await import("./pair.js");
  const sent = [];
  const listeners = {};
  globalThis.document = { getElementById: (id) => id === "pair-request"
    ? { addEventListener: (_e, fn) => { listeners.click = fn; } } : { textContent: "" } };
  let current = "old";
  setupPairCall((m) => { sent.push(m); return true; }, () => current);
  current = "new";
  listeners.click();
  assert.equal(sent[0].session_id, "new");
  delete globalThis.document;
});
