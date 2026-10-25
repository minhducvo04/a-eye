import test from 'node:test';
import assert from 'node:assert/strict';
import { pastCallLine, renderSplit } from './memory.js';

function page(nativeHls = false) {
  const timers = new Map();
  let next = 0;
  function element(tag) {
    return {
      tag, children: [], style: {}, events: {}, hidden: false,
      append(...children) { for (const c of children) c.parent = this; this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); },
      setAttribute(name, value) { this[name] = value; },
      removeAttribute(name) { delete this[name]; },
      addEventListener(name, fn) { this.events[name] = fn; },
      canPlayType() { return nativeHls ? 'maybe' : ''; },
      play() { this.playing = true; return Promise.resolve(); },
      pause() { this.playing = false; },
      load() {},
    };
  }
  const doc = {
    createElement: element, createElementNS: (_, tag) => element(tag),
    defaultView: {
      setInterval(fn, delay) { timers.set(++next, { fn, delay }); return next; },
      clearInterval(id) { timers.delete(id); },
    },
  };
  const body = element('div');
  const pane = () => body.children[1].children[0];
  return { doc, body, timers, pane };
}

test('found card cycles frames, loops, preserves boxes, and disposes the timer', () => {
  const { doc, body, timers, pane } = page();
  const update = renderSplit(doc, body, { hit: { t_s: 5, frames_b64: ['a', 'b', 'c'], fps: 2,
    objects: [{ label: 'keys', bbox: [0.1, 0.2, 0.3, 0.4] }] }, line: 'Found' });
  const img = pane().children.find(el => el.tag === 'img');
  assert.equal(img.src, 'data:image/jpeg;base64,a');
  const timer = [...timers.values()][0];
  assert.equal(timer.delay, 500);
  timer.fn(); assert.equal(img.src, 'data:image/jpeg;base64,b');
  timer.fn(); assert.equal(img.src, 'data:image/jpeg;base64,c');
  timer.fn(); assert.equal(img.src, 'data:image/jpeg;base64,a');
  assert.equal(pane().children.find(el => el.className === 'rewind-box').style.left, '10%');
  update.dispose();
  assert.equal(timers.size, 0);
});

test('single frame stays still; unsupported HLS uses the existing fallback', () => {
  const { doc, body, timers, pane } = page();
  const update = renderSplit(doc, body, { hit: { t_s: 5, frames_b64: ['a'],
    clip_url: 'https://media.invalid/clip.m3u8' }, line: 'Found' });
  assert.equal(timers.size, 0);
  assert.equal(pane().children.find(el => el.tag === 'img').src, 'data:image/jpeg;base64,a');
  assert.ok(!pane().children.some(el => el.tag === 'video'));
  update.dispose();
});

test('native HLS seeks and loops within the hit; errors restore the flipbook', async () => {
  const { doc, body, timers, pane } = page(true);
  const update = renderSplit(doc, body, { hit: { t_s: 105, start_s: 2, end_s: 8,
    frames_b64: ['a', 'b'], fps: 1, clip_url: 'https://media.invalid/clip.m3u8' }, line: 'Found' });
  const video = pane().children.find(el => el.tag === 'video');
  const img = pane().children.find(el => el.tag === 'img');
  assert.ok(video.muted && video.playsInline);
  video.events.loadedmetadata();
  await Promise.resolve();
  assert.equal(video.currentTime, 2);
  video.events.playing();
  assert.equal(timers.size, 0);
  video.currentTime = 8.1;
  video.events.timeupdate();
  assert.equal(video.currentTime, 2);
  video.events.error();
  assert.equal(video.hidden, true);
  assert.equal(img.hidden, false);
  assert.equal(timers.size, 1);
  update.dispose();
  assert.equal(timers.size, 0);
  assert.equal(video.playing, false);
});

test('past-call hit shows the video at once with a loading line, and labels the moment in that call', async () => {
  const { doc, body, pane } = page(true);
  const update = renderSplit(doc, body, { hit: { t_s: 49, start_s: 0, end_s: 6, past_call: true,
    clip_url: 'https://media.invalid/saved.m3u8' }, line: pastCallLine({ t_s: 49 }) });
  const video = pane().children.find(el => el.tag === 'video');
  const loading = pane().children.find(el => el.className === 'memory-loading');
  assert.equal(video.hidden, false);
  assert.equal(loading.textContent, 'Loading the clip…');
  assert.equal(pastCallLine({ t_s: 49 }), 'From your last call · 0:49 into that call');
  video.events.error();
  assert.equal(loading.textContent, 'Loading the clip…');
  update.dispose();
});

test('hls.js past-call clip: video is in the pane before attach, plays from start_s and drops the loading line', async () => {
  const { doc, body, pane } = page(false);
  const hls = { handlers: {}, attachedInPane: null,
    on(name, fn) { this.handlers[name] = fn; },
    loadSource(url) { this.url = url; },
    attachMedia(video) { this.video = video; this.attachedInPane = Boolean(video.parent && video.parent.children.includes(video)); } };
  globalThis.Hls = class { static isSupported() { return true; } static Events = { MANIFEST_PARSED: 'mp', ERROR: 'err' }; constructor() { return hls; } };
  try {
    const update = renderSplit(doc, body, { hit: { t_s: 52, start_s: 0, end_s: 3, past_call: true,
      clip_url: 'https://media.invalid/saved.m3u8' }, line: pastCallLine({ t_s: 52 }) });
    const video = pane().children.find(el => el.tag === 'video');
    const loading = pane().children.find(el => el.className === 'memory-loading');
    assert.equal(hls.url, 'https://media.invalid/saved.m3u8');
    assert.equal(hls.video, video);
    assert.equal(hls.attachedInPane, true);
    assert.equal(loading.textContent, 'Loading the clip…');
    hls.handlers.mp();
    await Promise.resolve();
    assert.equal(video.currentTime, 0);
    assert.equal(video.playing, true);
    video.events.playing();
    assert.ok(!pane().children.includes(loading), 'loading line removed on playing');
    assert.equal(video.hidden, false);
    video.currentTime = 3.2;
    video.events.timeupdate();
    assert.equal(video.currentTime, 0);
    update.dispose();
    assert.equal(video.playing, false);
  } finally {
    delete globalThis.Hls;
  }
});

test('a browser that says "maybe" to native HLS still streams through hls.js when it is loaded (Chromium answers maybe, then fails)', async () => {
  const { doc, body, pane } = page(true);
  const hls = { handlers: {}, on(name, fn) { this.handlers[name] = fn; }, loadSource(url) { this.url = url; }, attachMedia(video) { this.video = video; } };
  globalThis.Hls = class { static isSupported() { return true; } static Events = { MANIFEST_PARSED: 'mp', ERROR: 'err' }; constructor() { return hls; } };
  try {
    const update = renderSplit(doc, body, { hit: { t_s: 52, start_s: 0, end_s: 3, past_call: true,
      clip_url: 'https://media.invalid/saved.m3u8' }, line: pastCallLine({ t_s: 52 }) });
    const video = pane().children.find(el => el.tag === 'video');
    assert.equal(hls.video, video, 'hls.js attached, not the native src path');
    assert.equal(video.src, undefined);
    update.dispose();
  } finally {
    delete globalThis.Hls;
  }
});
