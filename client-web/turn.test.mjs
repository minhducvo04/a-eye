import assert from 'node:assert/strict';
import test from 'node:test';
import { nextTurnState, statusLine, createEarlyFinal } from './turn.js';

test('pipeline stages, timestamps, and server timing', () => {
  let s = nextTurnState(null, { type: 'mic_start' }, 0);
  assert.equal(statusLine(s, 100), 'Hearing 0.1 s');
  s = nextTurnState(s, { type: 'interim', text: 'hello' }, 100);
  assert.match(statusLine(s, 200), /Hearing.*hello/);
  s = nextTurnState(s, { type: 'sent', text: 'hello' }, 300);
  assert.equal(statusLine(s, 400), 'Sent 0.1 s');
  s = nextTurnState(s, { type: 'turn', stage: 'received', turn_id: 'a', at_ms: 99999 }, 500);
  assert.equal(statusLine(s, 600), 'Received 0.1 s');
  for (const [stage, label] of [['transcribing', 'Transcribing'], ['thinking', 'Thinking'], ['backup', 'Brain slow, trying backup'], ['speaking', 'Speaking'], ['done', 'Done'], ['cancelled', 'Cancelled'], ['failed', "Didn't catch that"]]) {
    s = nextTurnState(s, { type: 'turn', stage, turn_id: 'a', at_ms: 99999, typical_ms: 1100 }, 1000);
    assert.ok(statusLine(s, 2800).startsWith(label));
    if (stage === 'thinking') assert.equal(statusLine(s, 2800), 'Thinking 1.8 s · usually 1.1 s');
  }
  s = nextTurnState(s, { type: 'first_text' }, 3000);
  s = nextTurnState(s, { type: 'first_sound' }, 3200);
  s = nextTurnState(s, { type: 'first_sound' }, 3300);
  assert.deepEqual(s.timestamps, { sent: 300, received: 500, first_text: 3000, first_sound: 3200 });
});

test('ack retries once at two seconds and then shows connection problem', () => {
  let s = nextTurnState(null, { type: 'sent', text: 'hello' }, 0);
  s = nextTurnState(s, { type: 'tick' }, 1999);
  assert.equal(s.retries, 0);
  s = nextTurnState(s, { type: 'tick' }, 2000);
  assert.equal(s.retries, 1);
  assert.match(statusLine(s, 2000), /^Not received, retrying/);
  s = nextTurnState(s, { type: 'tick' }, 4000);
  assert.match(statusLine(s, 4000), /^Connection problem/);
  assert.equal(nextTurnState(s, { type: 'tick' }, 9000).retries, 1);
  s = nextTurnState(s, { type: 'closed' }, 9100);
  assert.match(statusLine(s, 9200), /^Connection lost, retrying/);
});

test('no speech timeout, mic stop, and failure details', () => {
  let s = nextTurnState(null, { type: 'mic_start' }, 0);
  assert.match(statusLine(nextTurnState(s, { type: 'tick' }, 8000), 8000), /^Didn't catch that, try again/);
  s = nextTurnState(s, { type: 'mic_stop' }, 100);
  assert.equal(statusLine(nextTurnState(s, { type: 'tick' }, 9000), 9000), 'Mic muted');
  s = nextTurnState(s, { type: 'turn', stage: 'failed', detail: 'Try a shorter question' }, 10000);
  assert.match(statusLine(s, 10000), /^Try a shorter question/);
});

function fakeClock() {
  let now = 0, id = 0;
  const tasks = new Map();
  return {
    setTimeout(fn, ms) { tasks.set(++id, { at: now + ms, fn }); return id; },
    clearTimeout(key) { tasks.delete(key); },
    advance(ms) { now += ms; for (const [key, task] of tasks) if (task.at <= now) { tasks.delete(key); task.fn(); } },
  };
}

test('early final uses latest interim at 700ms and never sends a late correction as another turn', () => {
  const clock = fakeClock(), sent = [];
  const early = createEarlyFinal(text => sent.push(text), clock);
  early.interim('place', 'a');
  clock.advance(600);
  early.interim('place the fan', 'a');
  clock.advance(699);
  assert.deepEqual(sent, []);
  clock.advance(1);
  assert.deepEqual(sent, ['place the fan']);
  early.final('Place the fan.', 'a');
  early.final('put the fan over there instead', 'a');
  early.interim('more late words', 'a');
  clock.advance(1000);
  assert.equal(sent.length, 1);
  early.final('new question', 'b');
  assert.deepEqual(sent, ['place the fan', 'new question']);
  early.interim('do not send', 'c');
  early.reset();
  clock.advance(1000);
  assert.equal(sent.length, 2);
});

test('call page toggles camera, keeps voice-only hello, retries text, reconnects, and renders streamed replies', async () => {
  const saved = new Map();
  const put = (key, value) => { saved.set(key, Object.getOwnPropertyDescriptor(globalThis, key)); Object.defineProperty(globalThis, key, { value, configurable: true, writable: true }); };
  const nodes = new Map(), intervals = new Map(), timeouts = new Map();
  let timerId = 0, stops = 0, gets = 0;
  const context = new Proxy({}, { get: (_obj, key) => key === 'measureText' ? () => ({ width: 20 }) : key === 'createRadialGradient' ? () => ({ addColorStop() {} }) : () => {} });
  class Element {
    constructor() { this.handlers = {}; this.attrs = {}; this.children = []; this.style = {}; this.textContent = ''; this.value = ''; this.clientWidth = 390; this.clientHeight = 844; this.width = 320; this.height = 200; const classes = new Set(); this.classList = { add: k => classes.add(k), remove: k => classes.delete(k), contains: k => classes.has(k), toggle: (k, on) => on ? classes.add(k) : classes.delete(k) }; }
    addEventListener(name, fn) { this.handlers[name] = fn; }
    setAttribute(key, value) { this.attrs[key] = value; }
    getAttribute(key) { return this.attrs[key]; }
    removeAttribute(key) { delete this.attrs[key]; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    querySelector() { return null; }
    getContext() { return context; }
    play() { return Promise.resolve(); }
  }
  const node = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  class Socket {
    static OPEN = 1; static CONNECTING = 0; static all = [];
    constructor() { this.readyState = 0; this.handlers = {}; this.messages = []; Socket.all.push(this); }
    addEventListener(name, fn) { this.handlers[name] = fn; }
    send(text) { this.messages.push(JSON.parse(text)); }
    open() { this.readyState = 1; this.handlers.open(); }
    message(data) { this.handlers.message({ data: JSON.stringify(data) }); }
    close() { this.readyState = 3; this.handlers.close(); }
  }
  const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
  put('document', { getElementById: node, createElement: () => new Element(), createTextNode: text => ({ textContent: text }), hidden: false });
  put('window', { isSecureContext: true, innerWidth: 390, innerHeight: 844, devicePixelRatio: 1, matchMedia: () => ({ matches: true }), addEventListener() {}, requestAnimationFrame() { return 1; }, setInterval(fn, ms) { intervals.set(++timerId, { fn, ms }); return timerId; }, clearInterval(id) { intervals.delete(id); }, setTimeout(fn, ms) { timeouts.set(++timerId, { fn, ms }); return timerId; }, clearTimeout(id) { timeouts.delete(id); } });
  put('localStorage', null);
  put('location', { search: '', protocol: 'https:', host: 'example.test' });
  put('navigator', { mediaDevices: { getUserMedia: async () => { gets++; return { getTracks: () => [{ stop() { stops++; } }] }; } } });
  put('SpeechRecognition', class { start() {} stop() {} });
  put('WebSocket', Socket);
  const realNow = Date.now;
  let now = 1000;
  Date.now = () => now;
  try {
    await import('./agent.js');
    node('picker').handlers.click({ target: { closest: () => ({ getAttribute: () => 'general' }) } });
    await settle();
    const socket = Socket.all[0];
    assert.ok(socket);
    socket.open();
    assert.equal(socket.messages[0].camera, false);
    node('start-camera').handlers.click();
    await settle();
    assert.equal(gets, 1);
    assert.equal(socket.messages.at(-1).type, 'camera');
    assert.equal(socket.messages.at(-1).on, true);
    assert.equal([...intervals.values()].filter(t => t.ms === 1000).length, 1);
    node('start-camera').handlers.click();
    assert.equal(stops, 1);
    assert.equal(socket.messages.at(-1).on, false);
    assert.equal([...intervals.values()].filter(t => t.ms === 1000).length, 0);
    node('start-camera').handlers.click();
    await settle();
    assert.equal(gets, 2);
    node('typed').value = 'hello';
    node('composer').handlers.submit({ preventDefault() {} });
    assert.equal(socket.messages.at(-1).type, 'user_text');
    assert.match(node('pipeline').textContent, /^Sent/);
    now += 2000;
    const tick = [...intervals.values()].find(t => t.ms === 100).fn;
    tick();
    assert.equal(socket.messages.filter(m => m.type === 'user_text').length, 2);
    now += 2000;
    tick();
    assert.match(node('pipeline').textContent, /^Connection problem/);
    socket.message({ type: 'turn', stage: 'received', turn_id: 'a', at_ms: 10 });
    socket.message({ type: 'turn', stage: 'thinking', turn_id: 'a', at_ms: 20, typical_ms: 1100 });
    now += 1800;
    tick();
    assert.equal(node('pipeline').textContent, 'Thinking 1.8 s · usually 1.1 s');
    socket.message({ type: 'reply_delta', turn_id: 'a', text: 'Hello' });
    socket.message({ type: 'reply_delta', turn_id: 'a', text: ' there' });
    assert.equal(node('replies').children[0].children[2].textContent, 'Hello there');
    socket.close();
    assert.match(node('pipeline').textContent, /^Connection lost, retrying/);
    const retry = [...timeouts.values()].at(-1);
    assert.equal(retry.ms, 500);
    retry.fn();
    Socket.all[1].open();
    assert.equal(Socket.all[1].messages[0].type, 'hello');
    assert.equal(Socket.all[1].messages[0].camera, true);
    Socket.all[1].close();
    [...timeouts.values()].at(-1).fn();
    Socket.all[2].close();
    assert.equal([...timeouts.values()].at(-1).ms, 1000);
  } finally {
    Date.now = realNow;
    for (const [key, descriptor] of saved) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  }
});

test('a known mic cause replaces the generic failure and clears on speech', () => {
  let s = nextTurnState(undefined, { type: 'mic_start' }, 0);
  s = nextTurnState(s, { type: 'cause', detail: 'No speech detected' }, 10);
  assert.match(statusLine(nextTurnState(s, { type: 'tick' }, 8000), 8000), /^No speech detected/);
  s = nextTurnState(s, { type: 'interim', text: 'hello' }, 20);
  assert.equal(s.cause, '');
  const muted = nextTurnState(nextTurnState(undefined, { type: 'cause', detail: 'Mic blocked' }, 0), { type: 'mic_stop' }, 1);
  assert.equal(statusLine(muted, 2), 'Mic blocked');
});
