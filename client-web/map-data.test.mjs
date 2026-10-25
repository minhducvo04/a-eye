// Integrity of the system map data: every link resolves, building work is marked, no invented speed or cost.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const data = JSON.parse(readFileSync(new URL('./map-data.json', import.meta.url)));
const nodes = new Map(data.nodes.map((n) => [n.id, n]));
const edges = new Map(data.edges.map((e) => [e.id, e]));
const zones = new Set(data.zones.map((z) => z.id));

test('ids are unique and every reference resolves', () => {
  assert.equal(nodes.size, data.nodes.length);
  assert.equal(edges.size, data.edges.length);
  for (const n of data.nodes) assert.ok(zones.has(n.zone), n.id);
  for (const e of data.edges) assert.ok(nodes.has(e.from) && nodes.has(e.to), e.id);
  for (const f of data.flows) for (const raw of f.edges) assert.ok(edges.has(raw.replace(/^-/, '')), `${f.id}: ${raw}`);
  for (const n of data.nodes) for (const r of n.look?.rows || []) if (r.node) assert.ok(nodes.has(r.node), r.node);
});

test('every node states a speed and a cost, never blank', () => {
  for (const n of data.nodes) {
    assert.ok(n.speed && n.cost, n.id);
    assert.ok(n.what && n.code?.length, n.id);
  }
});

test('shipped work is marked working: parts shelf, time scope, saved-call recall', () => {
  assert.equal(nodes.get('parts').status, 'working');
  assert.equal(nodes.get('router').building, undefined);
  assert.equal(nodes.get('saved').building, undefined);
  for (const id of ['rt-saved', 'parts-srv']) assert.equal(edges.get(id).status, 'working', id);
  for (const e of data.edges) if (e.status === 'building') {
    for (const f of data.flows) assert.ok(!f.edges.some((x) => x.replace(/^-/, '') === e.id), `${f.id} plays building edge ${e.id}`);
  }
});

test('measured numbers match tonight\'s runs and cloud costs say estimate', () => {
  assert.match(nodes.get('gemini').speed, /0\.6 to 1\.1 s/);
  assert.match(nodes.get('ground').speed, /1\.8 to 2\.3 s/);
  assert.match(nodes.get('safety').speed, /86 ms/);
  assert.match(nodes.get('router').speed, /45\.7 ms/);
  assert.ok(nodes.get('router').facts.some(([, v]) => /86% of 300/.test(v)));
  assert.match(nodes.get('rewind').speed, /35 to 40 s/);
  for (const id of ['gemini', 'rewind']) assert.match(nodes.get(id).cost, /est\./, id);
});

test('final focus: no home-repair words anywhere on the map', () => {
  for (const f of ['map-data.json', 'map.html', 'map.js']) {
    assert.doesNotMatch(readFileSync(new URL('./' + f, import.meta.url), 'utf8'), /\b(sinks?|faucets?|valves?|plumb\w*|hinges?|breakers?)\b/i, f);
  }
  assert.ok(data.flows.some((f) => f.id === 'guest'));
  assert.ok(data.scale.sections.length >= 3);
  for (const [, u] of data.scale.sources) assert.match(u, /^https:\/\//);
  for (const f of data.flows) assert.ok(f.detail && f.detail.latency && f.detail.cost, f.id);
});

test('the $1.40 meter figure appears only in the Cost panel, labelled as the safety meter', () => {
  const { call_cost, ...rest } = data;
  assert.doesNotMatch(JSON.stringify(rest), /1\.40/);
  assert.match(call_cost.meter[1], /1\.40/);
  assert.match(call_cost.meter[0], /counts high on purpose/);
  assert.match(data.headline.chips[2].text, /list price, est\./);
});

test('visible text has no em or en dashes', () => {
  assert.doesNotMatch(readFileSync(new URL('./map-data.json', import.meta.url), 'utf8'), /[–—]/);
  assert.doesNotMatch(readFileSync(new URL('./map.html', import.meta.url), 'utf8'), /[–—]/);
});
