// A-Eye system map: a data-driven three.js scene. Everything shown comes from map-data.json.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/addons/controls/OrbitControls.js';

const params = new URLSearchParams(location.search);
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches || params.get('motion') === 'reduce';
const TONE = {
  device: '#8fb3ff', server: '#6ff0c0', cloud: '#c4a1ff', gpu: '#ff9cb8', memory: '#b6f27a',
  danger: '#ff6b78', building: '#ff9f5a', muted: '#8a95a8', speed: '#74e4ff', cost: '#ffd479', switch: '#dbe4f2',
};
const PULSE_SPEED = REDUCED ? 0.9 : 4.2; // world units per second
const TRAIL = 30;

const data = await (await fetch('map-data.json', { cache: 'no-store' })).json();
const zones = Object.fromEntries(data.zones.map((z) => [z.id, z]));
const nodes = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
const edges = Object.fromEntries(data.edges.map((e) => [e.id, e]));
const toneOf = (n) => n.status === 'building' ? TONE.building : n.tone ? TONE[n.tone] : n.shape === 'switch' ? TONE.switch : zones[n.zone].color;
const isCloud = (n) => n.zone === 'cloud' || !!n.privacy;

// ---------- renderer, camera, controls ----------
const stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x04060c, 1);
stage.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const root = new THREE.Group(); // the whole map; turned upright on narrow screens
scene.add(root);
scene.fog = new THREE.FogExp2(0x04060c, 0.022);
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 300);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.screenSpacePanning = true;
controls.minDistance = 4;
controls.maxDistance = 70;
controls.rotateSpeed = 0.7;

// ---------- shared textures and materials ----------
function glowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.18, 'rgba(255,255,255,.55)');
  grad.addColorStop(0.45, 'rgba(255,255,255,.12)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const GLOW = glowTexture();
const additive = { transparent: true, depthWrite: false, blending: THREE.AdditiveBlending };

const rimMaterial = (color) => new THREE.ShaderMaterial({
  uniforms: { uColor: { value: new THREE.Color(color) }, uPower: { value: 2.2 }, uGain: { value: 1.3 } },
  vertexShader: `varying vec3 vN; varying vec3 vV;
    void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform vec3 uColor; uniform float uPower; uniform float uGain; varying vec3 vN; varying vec3 vV;
    void main(){ float f = pow(1.0 - max(dot(vN, vV), 0.0), uPower); gl_FragColor = vec4(uColor * uGain, f); }`,
  ...additive,
});

// ---------- atmosphere: zone glows, floor rings ----------
for (const z of data.zones) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color: z.color, opacity: 0.075, ...additive }));
  s.position.fromArray(z.center);
  s.scale.setScalar(z.radius * 3.2);
  root.add(s);
}
{
  const floor = new THREE.PolarGridHelper(22, 12, 9, 96, 0x1d2a3f, 0x111a29);
  floor.position.set(-0.5, -10, -2.5);
  window.__floor = floor;
  floor.material.transparent = true;
  floor.material.opacity = 0.32;
  floor.material.depthWrite = false;
  scene.add(floor);
}

// ---------- nodes ----------
const pickables = [];
const nodeObj = {};
for (const n of data.nodes) {
  const color = toneOf(n);
  const g = new THREE.Group();
  g.position.fromArray(n.pos);
  const r = n.size * 0.55;
  const building = n.status === 'building';
  const core = new THREE.Mesh(
    building ? new THREE.IcosahedronGeometry(r, 1) : new THREE.SphereGeometry(r * 0.72, 32, 16),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(color).lerp(new THREE.Color('#ffffff'), building ? 0 : 0.18), wireframe: building, transparent: true, opacity: building ? 0.85 : 1 }),
  );
  const shell = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 16), rimMaterial(color));
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color, opacity: building ? 0.28 : 0.6, ...additive }));
  const baseHalo = n.size * (building ? 3 : 4.4);
  halo.scale.setScalar(baseHalo);
  // a thin orbit ring gives each node a readable 3D axis; dashed when the node is still being built
  const ringPts = new THREE.EllipseCurve(0, 0, r * 1.75, r * 1.75).getPoints(72).map((p) => new THREE.Vector3(p.x, 0, p.y));
  const ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPts),
    building ? new THREE.LineDashedMaterial({ color, dashSize: 0.08, gapSize: 0.07, transparent: true, opacity: 0.8 })
      : new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.32 }));
  if (building) ring.computeLineDistances();
  ring.rotation.x = 0.35;
  const hit = new THREE.Mesh(new THREE.SphereGeometry(Math.max(r * 2.1, 0.55), 12, 8), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }));
  hit.userData = { kind: 'node', id: n.id };
  pickables.push(hit);
  g.add(halo, shell, core, ring, hit);
  root.add(g);
  nodeObj[n.id] = { g, core, shell, halo, ring, baseHalo, flash: 0, color, dim: 1 };

  if (n.cloud_points) {
    // one point per listing; layout is decorative (a flat disc so it reads as a shelf of many items)
    const N = n.cloud_points;
    const pos = new Float32Array(N * 3);
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < N; i++) {
      const a = rnd() * Math.PI * 2;
      const d = 0.75 + Math.pow(rnd(), 0.7) * 1.25;
      pos[i * 3] = Math.cos(a) * d;
      pos[i * 3 + 1] = (rnd() - 0.5) * 0.22 * (2.2 - d);
      pos[i * 3 + 2] = Math.sin(a) * d;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const pts = new THREE.Points(geo, new THREE.PointsMaterial({ color, size: 0.028, sizeAttenuation: true, opacity: 0.55, ...additive }));
    pts.rotation.x = 0.35;
    g.add(pts);
    nodeObj[n.id].cloud = pts;
  }
}

// ---------- edges ----------
const edgeObj = {};
const tmpA = new THREE.Vector3();
for (const e of data.edges) {
  const a = new THREE.Vector3().fromArray(nodes[e.from].pos);
  const b = new THREE.Vector3().fromArray(nodes[e.to].pos);
  const d = a.distanceTo(b);
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const side = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3(0, 1, 0)).normalize();
  mid.add(new THREE.Vector3(0, 1, 0).multiplyScalar(d * 0.16 * (e.bend ?? 1))).add(side.multiplyScalar(d * 0.06 * (e.bend ?? 1)));
  const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
  const length = curve.getLength();
  const control = e.kind === 'control';
  const building = e.status === 'building';
  const color = e.tone ? TONE[e.tone] : building ? TONE.building : control ? TONE.switch : toneOf(nodes[e.from]);
  const parts = [];
  if (control || building) {
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(80)),
      new THREE.LineDashedMaterial({ color, dashSize: 0.16, gapSize: 0.14, transparent: true, opacity: control ? 0.42 : 0.7, depthWrite: false }));
    line.computeLineDistances();
    parts.push(line);
  } else {
    const thin = new THREE.Mesh(new THREE.TubeGeometry(curve, 80, 0.016, 6), new THREE.MeshBasicMaterial({ color, opacity: 0.42, ...additive }));
    const glow = new THREE.Mesh(new THREE.TubeGeometry(curve, 80, 0.09, 8), new THREE.MeshBasicMaterial({ color, opacity: 0.07, ...additive }));
    parts.push(thin, glow);
  }
  const hit = new THREE.Mesh(new THREE.TubeGeometry(curve, 40, 0.2, 6), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }));
  hit.userData = { kind: 'edge', id: e.id };
  pickables.push(hit);
  for (const p of parts) root.add(p);
  root.add(hit);
  edgeObj[e.id] = { curve, length, parts, color, baseOpacity: parts.map((p) => p.material.opacity), dim: 1 };
}

// ---------- pulses: one Points object, glowing heads with fading trails ----------
const ambient = [];
for (const e of data.edges) {
  if (e.kind === 'control' || e.status === 'building') continue;
  const count = REDUCED ? 1 : Math.max(1, Math.round((e.rate ?? 0.5) * (e.main ? 9 : 4))); // reduced motion: one slow pulse per line
  for (let i = 0; i < count; i++) {
    const reverse = e.both && i % 2 === 1;
    ambient.push({ edge: e.id, reverse, t: REDUCED ? 0 : Math.random(), wait: Math.random() * (REDUCED ? 12 : 1.2), flow: false });
  }
}
const flowPackets = [];
let pendingClear = false;
const MAXP = (ambient.length + 4) * TRAIL;
const pPos = new Float32Array(MAXP * 3), pCol = new Float32Array(MAXP * 3), pSize = new Float32Array(MAXP), pAlpha = new Float32Array(MAXP);
const pGeo = new THREE.BufferGeometry();
pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3).setUsage(THREE.DynamicDrawUsage));
pGeo.setAttribute('color', new THREE.BufferAttribute(pCol, 3).setUsage(THREE.DynamicDrawUsage));
pGeo.setAttribute('size', new THREE.BufferAttribute(pSize, 1).setUsage(THREE.DynamicDrawUsage));
pGeo.setAttribute('alpha', new THREE.BufferAttribute(pAlpha, 1).setUsage(THREE.DynamicDrawUsage));
const pMat = new THREE.ShaderMaterial({
  uniforms: { uScale: { value: 400 } },
  vertexShader: `attribute float size; attribute float alpha; attribute vec3 color; uniform float uScale; varying float vA; varying vec3 vC;
    void main(){ vA = alpha; vC = color; vec4 mv = modelViewMatrix * vec4(position,1.0); gl_PointSize = size * uScale / -mv.z; gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `varying float vA; varying vec3 vC;
    void main(){ float d = length(gl_PointCoord - 0.5) * 2.0; float core = exp(-d*d*14.0); float halo = exp(-d*d*3.0) * 0.7;
      float a = (core + halo) * vA; if (a < 0.003) discard; gl_FragColor = vec4(mix(vC, vec3(1.0), core * 0.75) * a, a); }`,
  transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
});
const pulses = new THREE.Points(pGeo, pMat);
pulses.frustumCulled = false;
root.add(pulses);

// ---------- labels (HTML, so text stays crisp and readable) ----------
const labelsEl = document.getElementById('labels');
const labels = [];
function addLabel(kind, id, anchor) {
  const el = document.createElement('div');
  el.className = 'lab ' + kind;
  labelsEl.appendChild(el);
  const l = { kind, id, el, anchor, visible: true };
  labels.push(l);
  return l;
}
for (const z of data.zones) {
  const l = addLabel('zone', z.id, z.label_at ? new THREE.Vector3().fromArray(z.label_at) : new THREE.Vector3(z.center[0], z.center[1] + z.radius * 0.62 + 0.4, z.center[2]));
  l.el.textContent = z.name;
}
for (const n of data.nodes) addLabel('node', n.id, new THREE.Vector3(n.pos[0], n.pos[1] - n.size * 0.62, n.pos[2]));
for (const e of data.edges) addLabel('edge', e.id, edgeObj[e.id].curve.getPoint(0.5));

let mode = ['name', 'speed', 'cost'].includes(params.get('mode')) ? params.get('mode') : 'name';
let selected = null; // {kind, id}
let flow = null;     // flow object
let related = null;  // Set of 'n:id' / 'e:id', or null for all
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function renderLabels() {
  for (const l of labels) {
    if (l.kind === 'zone') continue;
    const item = l.kind === 'node' ? nodes[l.id] : edges[l.id];
    const value = item[mode];
    l.el.className = `lab ${l.kind} m-${mode}`;
    if (l.kind === 'node') {
      const b = item.status === 'building' ? '<span class="b">building</span>' : '';
      const selZone = selected && selected.kind === 'node' ? nodes[selected.id].zone : selected ? nodes[edges[selected.id].from].zone : null;
      const quiet = mode === 'cost' && innerWidth <= 760 && /^\$0/.test(value || '') && item.zone !== selZone;
      if (quiet) l.el.className = `lab ${l.kind} m-name`;
      l.el.innerHTML = mode === 'name' || quiet ? `<span class="v">${esc(item.name)}</span>${b}`
        : `<span class="v">${esc(value || 'not measured')}</span><span class="n">${esc(item.name)}</span>${b}`;
      l.show = true;
    } else {
      const inFocus = related && related.has('e:' + l.id);
      const worthIt = mode === 'name' ? false : mode === 'cost' ? value && value !== '$0' : !!value;
      l.show = (mode === 'name' && inFocus) || (worthIt && (!related || inFocus));
      l.el.innerHTML = `<span class="v">${esc(mode === 'name' ? item.name : value || item.name)}</span>`;
    }
    l.el.classList.toggle('hide', !l.show);
    l.dirty = true;
  }
  const note = document.getElementById('modeNote');
  note.textContent = mode === 'speed' ? data.measured_note : mode === 'cost' ? (innerWidth <= 760 ? 'Name only = $0 (local). Tap a part to see its zone.' : 'Costs are meter estimates; local models cost $0. Open a node for the source.') : '';
}

// ---------- focus: selection and flows dim everything unrelated ----------
function relatedFor(sel) {
  const s = new Set();
  if (!sel) return null;
  if (sel.kind === 'node') {
    s.add('n:' + sel.id);
    for (const e of data.edges) if (e.from === sel.id || e.to === sel.id) { s.add('e:' + e.id); s.add('n:' + e.from); s.add('n:' + e.to); }
  } else {
    const e = edges[sel.id];
    s.add('e:' + e.id); s.add('n:' + e.from); s.add('n:' + e.to);
  }
  return s;
}
function relatedForFlow(f) {
  const s = new Set();
  for (const raw of f.edges) { const e = edges[raw.replace(/^-/, '')]; s.add('e:' + e.id); s.add('n:' + e.from); s.add('n:' + e.to); }
  return s;
}
function applyFocus() {
  related = selected ? relatedFor(selected) : flow ? relatedForFlow(flow) : null;
  for (const [id, o] of Object.entries(nodeObj)) o.dimTarget = !related || related.has('n:' + id) ? 1 : 0.14;
  for (const [id, o] of Object.entries(edgeObj)) o.dimTarget = !related || related.has('e:' + id) ? 1 : 0.08;
  renderLabels();
}

// ---------- side panel ----------
const panel = document.getElementById('panel');
const body = document.getElementById('panelBody');
const tone = (t) => TONE[t] || TONE.muted;

function rangeSvg(w) {
  const W = 320, top = (w.marks || []).length ? 22 : 6, rowH = 36, axisY = top + w.ranges.length * rowH + 4, H = axisY + 22;
  const x = (v) => 14 + ((v - w.min) / (w.max - w.min)) * (W - 40);
  const step = niceStep(w.max - w.min);
  const halo = 'paint-order="stroke" stroke="#0a0f19" stroke-width="5" stroke-linejoin="round"';
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(w.title)}">`;
  for (let v = w.min; v <= w.max + 1e-9; v += step) {
    const last = v + step > w.max + 1e-9;
    s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${axisY}" stroke="rgba(255,255,255,.08)"/>`;
    s += `<text x="${x(v)}" y="${axisY + 14}" fill="#a3afc2" font-size="11" text-anchor="middle">${+v.toFixed(2)}</text>`;
    if (last) s += `<text x="${W - 2}" y="${axisY + 14}" fill="#a3afc2" font-size="11" text-anchor="end">${esc(w.unit)}</text>`;
  }
  // marks first, so range captions (with a dark halo) sit on top of the mark lines
  for (const m of w.marks || []) {
    const c = tone(m.tone), mx = x(m.at);
    s += `<line x1="${mx}" x2="${mx}" y1="${top - 6}" y2="${axisY}" stroke="${c}" stroke-width="2" ${m.tone === 'muted' ? 'stroke-dasharray="3 3"' : ''}/>`;
    s += `<text x="${mx + (mx > W - 110 ? -5 : 5)}" y="${top - 8}" fill="${c === TONE.muted ? '#a3afc2' : c}" font-size="11" font-weight="600" text-anchor="${mx > W - 110 ? 'end' : 'start'}">${esc(m.label)}</text>`;
  }
  w.ranges.forEach((r, i) => {
    const y = top + i * rowH;
    const text = `${r.label}: ${r.from} to ${r.to} ${w.unit}`, end = x(r.from) + text.length * 6.6 > W - 4;
    s += `<rect x="${x(r.from)}" y="${y + 19}" width="${Math.max(3, x(r.to) - x(r.from))}" height="10" rx="5" fill="${tone(r.tone)}"/>`;
    s += `<text x="${end ? Math.min(W - 4, x(r.to)) : x(r.from)}" y="${y + 13}" fill="#e9eef7" font-size="12" text-anchor="${end ? 'end' : 'start'}" ${halo}>${esc(text)}</text>`;
  });
  return s + '</svg>';
}
function niceStep(span) { const raw = span / 5; const p = 10 ** Math.floor(Math.log10(raw)); return [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= raw); }
function barsSvg(w) {
  let s = '';
  for (const g of w.groups) {
    const W = 320, rowH = 24, H = g.items.length * rowH + 20;
    s += `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(g.label)}"><text x="0" y="12" fill="#a3afc2" font-size="11" letter-spacing=".06em">${esc(g.label.toUpperCase())} (${esc(g.unit)})</text>`;
    g.items.forEach((it, i) => {
      const y = 20 + i * rowH, bw = Math.max(2, (it.value / g.max) * 170);
      s += `<text x="0" y="${y + 12}" fill="#e9eef7" font-size="12">${esc(it.label)}</text>`;
      s += `<rect x="96" y="${y + 2}" width="${bw}" height="12" rx="3" fill="${tone(it.tone)}"/>`;
      s += `<text x="${100 + bw}" y="${y + 12}" fill="#e9eef7" font-size="12" font-weight="600">${it.value}${g.unit === '%' ? '%' : ' ' + g.unit}</text>`;
    });
    s += '</svg>';
  }
  return s;
}
function lookHtml(w) {
  if (!w) return '';
  let inner = '';
  if (w.type === 'range') inner = rangeSvg(w);
  else if (w.type === 'bars') inner = barsSvg(w);
  else if (w.type === 'cards') inner = `<div class="cards">${w.cards.map((c) => `<div class="card t-${c.tone || ''}"><b>${esc(c.head)}</b>${esc(c.body)}</div>`).join('')}</div>`;
  else if (w.type === 'scopes') inner = `<div class="scopes">${w.rows.map((r) => `<div class="scope"><i style="background:${tone(r.tone)}"></i><span>${esc(r.label)}<br><small>${esc(r.who)}</small></span><span class="st ${r.status}">${esc(r.status)}</span></div>`).join('')}</div>`;
  else if (w.type === 'switches') inner = w.rows.map((r) => `<div class="sw"><span>${esc(r.label)}</span><small>${esc(r.sends)}</small><button data-go="${r.node}">Show</button></div>`).join('');
  else if (w.type === 'stat') inner = `<div class="stat">${esc(w.value)}<small>${esc(w.unit)}</small></div>`;
  return `<section class="look"><h3>${esc(w.title)}</h3>${inner}${w.foot ? `<p class="foot">${esc(w.foot)}</p>` : ''}</section>`;
}
function nodePanel(n) {
  const links = data.edges.filter((e) => e.from === n.id || e.to === n.id);
  const sw = n.privacy ? `<span class="badge cloud">switch: ${esc(n.privacy)}</span>` : '';
  return `<h2>${esc(n.name)}</h2><p class="kind">${esc(n.kind)}</p>
    <span class="badge ${n.status === 'building' ? 'build' : 'ok'}">${n.status === 'building' ? 'building tonight' : 'working'}</span>
    <span class="badge ${isCloud(n) ? 'cloud' : 'local'}">${isCloud(n) ? 'cloud' : 'local'}</span>${sw}
    ${n.building ? `<p class="note-build">${esc(n.building)}</p>` : ''}
    <p>${esc(n.what)}</p>
    <dl class="kv"><dt>Speed</dt><dd class="sp">${esc(n.speed || 'not measured')}</dd><dt>Cost</dt><dd class="co">${esc(n.cost || 'not measured')}</dd><dt>Where</dt><dd>${esc(zones[n.zone].name)}</dd></dl>
    ${lookHtml(n.look)}
    ${n.facts ? `<ul class="facts">${n.facts.map(([k, v]) => `<li><b>${esc(k)}</b>${esc(v)}</li>`).join('')}</ul>` : ''}
    <p class="sec">Connections</p><div class="links">${links.map((e) => `<button data-edge="${e.id}">${esc(nodes[e.from === n.id ? e.to : e.from].name)}: ${esc(e.name)}</button>`).join('')}</div>
    <p class="sec">Code</p><ul class="code">${n.code.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>`;
}
function edgePanel(e) {
  const a = nodes[e.from], b = nodes[e.to];
  const kind = e.kind === 'control' ? 'Privacy switch' : e.status === 'building' ? 'Data flow, building tonight' : e.both ? 'Data flow, both ways' : 'Data flow';
  return `<h2>${esc(e.name)}</h2><p class="kind">${esc(a.name)} ${e.both ? '&harr;' : '&rarr;'} ${esc(b.name)}</p>
    <span class="badge ${e.status === 'building' ? 'build' : 'ok'}">${e.status === 'building' ? 'building tonight' : kind}</span>
    <p>${esc(e.what)}</p>
    <dl class="kv"><dt>Speed</dt><dd class="sp">${esc(e.speed || 'not measured')}</dd><dt>Cost</dt><dd class="co">${esc(e.cost || (isCloud(b) ? 'see node' : '$0'))}</dd></dl>
    <div class="links"><button data-node="${a.id}">${esc(a.name)}</button><button data-node="${b.id}">${esc(b.name)}</button></div>`;
}
function indexPanel() {
  let s = '<h2>Index</h2><p class="kind">Every part of the map. Pick one to fly to it.</p>';
  for (const z of data.zones) {
    s += `<p class="sec">${esc(z.name)}</p><ul class="index">`;
    for (const n of data.nodes.filter((x) => x.zone === z.id)) {
      s += `<li><button data-node="${n.id}"><i style="background:${toneOf(n)}"></i><span>${esc(n.name)}</span><small class="m-${mode === 'name' ? 'speed' : mode}">${esc(n.status === 'building' ? 'building' : n[mode === 'name' ? 'speed' : mode] || '')}</small></button></li>`;
    }
    s += '</ul>';
  }
  return s + `<p class="sec" style="margin-top:14px">About the numbers</p><p class="kind">${esc(data.measured_note)} ${esc(data.cost_note)}</p>`;
}
function openPanel(html) {
  body.innerHTML = html;
  panel.hidden = false;
  document.body.classList.add('sheet');
  panel.scrollTop = 0;
}
function closePanel() { panel.hidden = true; document.body.classList.remove('sheet'); selected = null; applyFocus(); }
panel.addEventListener('click', (ev) => {
  const t = ev.target.closest('button');
  if (!t) return;
  if (t.dataset.node || t.dataset.go) select({ kind: 'node', id: t.dataset.node || t.dataset.go });
  else if (t.dataset.edge) select({ kind: 'edge', id: t.dataset.edge });
});
document.getElementById('closeBtn').addEventListener('click', closePanel);
document.getElementById('indexBtn').addEventListener('click', () => { selected = null; applyFocus(); openPanel(indexPanel()); });

// ---------- camera framing ----------
const world = (arr) => new THREE.Vector3().fromArray(arr).applyMatrix4(root.matrixWorld);
const home = { target: new THREE.Vector3(), pos: new THREE.Vector3() };
let tween = null;
let panelShift = 0, panelShiftY = 0;
function frame() {
  // Fit by projection: move and zoom until every node sits inside the free area below the header strip.
  const narrow = camera.aspect < 0.8;
  root.rotation.z = narrow ? -Math.PI / 2 : 0;
  root.updateMatrixWorld(true);
  const pts = data.nodes.map((n) => world(n.pos)).concat(data.zones.filter((z) => z.label_at).map((z) => world(z.label_at)));
  const box = new THREE.Box3().setFromPoints(pts);
  const W = innerWidth, H = innerHeight;
  const barBottom = document.querySelector('.bar').getBoundingClientRect().bottom;
  const side = Math.min(95, W * 0.19);
  const safe = { l: side, r: W - side, t: barBottom + 12, b: H - (narrow ? 96 : 104) }; // keeps the legend and its footnote line clear
  const dir = narrow ? new THREE.Vector3(0.1, 0.22, 1).normalize() : new THREE.Vector3(0.16, 0.3, 1).normalize();
  const target = box.getCenter(new THREE.Vector3());
  let dist = 32;
  const vfov = THREE.MathUtils.degToRad(camera.fov);
  camera.clearViewOffset();
  const right = new THREE.Vector3(), up = new THREE.Vector3(), q = new THREE.Vector3();
  for (let i = 0; i < 8; i++) {
    camera.position.copy(target).addScaledVector(dir, dist);
    camera.lookAt(target);
    camera.updateMatrixWorld(true);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) {
      q.copy(p).project(camera);
      const x = (q.x * 0.5 + 0.5) * W, y = (-q.y * 0.5 + 0.5) * H;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    const k = Math.max((x1 - x0) / (safe.r - safe.l), (y1 - y0) / (safe.b - safe.t));
    const perPx = (2 * dist * Math.tan(vfov / 2)) / H;
    right.setFromMatrixColumn(camera.matrixWorld, 0);
    up.setFromMatrixColumn(camera.matrixWorld, 1);
    target.addScaledVector(right, ((x0 + x1) / 2 - (safe.l + safe.r) / 2) * perPx).addScaledVector(up, -((y0 + y1) / 2 - (safe.t + safe.b) / 2) * perPx);
    dist *= Math.pow(k, 0.85);
  }
  home.target.copy(target);
  home.pos.copy(target).addScaledVector(dir, dist);
  window.__floor.position.y = box.min.y - 2.5;
}
function flyTo(target, pos, ms = 700) {
  if (REDUCED) { controls.target.copy(target); if (pos) camera.position.copy(pos); return; }
  tween = { t0: performance.now(), ms, fromT: controls.target.clone(), toT: target.clone(), fromP: camera.position.clone(), toP: pos ? pos.clone() : camera.position.clone().add(target.clone().sub(controls.target)) };
}

function select(sel) {
  flow = null;
  markFlows();
  selected = sel;
  applyFocus();
  if (sel.kind === 'node') {
    openPanel(nodePanel(nodes[sel.id]));
    const p = world(nodes[sel.id].pos);
    const dir = camera.position.clone().sub(controls.target).normalize();
    const dist = Math.min(camera.position.distanceTo(controls.target), innerWidth > 760 ? 21 : 30);
    flyTo(p, p.clone().addScaledVector(dir, dist));
  } else {
    openPanel(edgePanel(edges[sel.id]));
    flyTo(edgeObj[sel.id].curve.getPoint(0.5).applyMatrix4(root.matrixWorld));
  }
  history.replaceState(null, '', `?mode=${mode}&select=${sel.id}`);
}

// ---------- flows ----------
const flowsEl = document.getElementById('flows');
const sayEl = document.getElementById('flowSay');
const defaultSay = sayEl.textContent;
for (const f of data.flows) {
  const b = document.createElement('button');
  b.dataset.flow = f.id;
  b.setAttribute('aria-pressed', 'false');
  b.innerHTML = `<i class="k"></i>${esc(f.name)}`;
  b.addEventListener('click', () => setFlow(flow && flow.id === f.id ? null : f));
  flowsEl.appendChild(b);
}
// headline strip: one sentence and three numbers a judge can read in ten seconds
document.getElementById('tagline').textContent = data.headline.say;
for (const c of data.headline.chips) {
  const b = document.createElement('button');
  b.className = 't-' + c.tone;
  b.textContent = c.text;
  b.addEventListener('click', () => select({ kind: 'node', id: c.node }));
  document.getElementById('chips').appendChild(b);
}
function markFlows() { for (const b of flowsEl.children) b.setAttribute('aria-pressed', String(!!flow && b.dataset.flow === flow.id)); sayEl.textContent = flow ? flow.say : defaultSay; document.body.classList.toggle('flowing', !!flow); }
function setFlow(f, once = false) {
  flow = f;
  selected = null;
  panel.hidden = true;
  document.body.classList.remove('sheet');
  markFlows();
  applyFocus();
  flowPackets.length = 0;
  if (f) flowPackets.push({ step: 0, t: 0, wait: once ? 0.8 : 0.2, once });
}

// ---------- mode switch ----------
const seg = document.querySelectorAll('.seg button');
function setMode(m) {
  mode = m;
  document.body.classList.toggle('cost-mode', m === 'cost');
  seg.forEach((b) => b.setAttribute('aria-checked', String(b.dataset.mode === m)));
  renderLabels();
  if (!panel.hidden && !selected) openPanel(indexPanel());
}
seg.forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));
document.querySelector('.seg').addEventListener('keydown', (ev) => {
  const order = ['name', 'speed', 'cost'];
  const i = order.indexOf(mode);
  if (ev.key === 'ArrowRight') { setMode(order[(i + 1) % 3]); seg[(i + 1) % 3].focus(); }
  if (ev.key === 'ArrowLeft') { setMode(order[(i + 2) % 3]); seg[(i + 2) % 3].focus(); }
});
addEventListener('keydown', (ev) => { if (ev.key === 'Escape') { setFlow(null); closePanel(); flyTo(home.target, home.pos); } });

// ---------- picking ----------
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
const tip = document.getElementById('tip');
let down = null;
function pick(ev) {
  const rect = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hits = ray.intersectObjects(pickables, false);
  const node = hits.find((h) => h.object.userData.kind === 'node');
  return (node || hits[0])?.object.userData || null;
}
let hovered = null;
renderer.domElement.addEventListener('pointermove', (ev) => {
  if (ev.pointerType === 'touch') return;
  const h = pick(ev);
  hovered = h;
  renderer.domElement.style.cursor = h ? 'pointer' : 'grab';
  if (!h || down) { tip.hidden = true; return; }
  const item = h.kind === 'node' ? nodes[h.id] : edges[h.id];
  const sub = h.kind === 'node' ? item.kind : `${nodes[item.from].name} ${item.both ? '↔' : '→'} ${nodes[item.to].name}`;
  tip.innerHTML = `<b>${esc(item.name)}</b><span>${esc(sub)}</span>`;
  tip.hidden = false;
  tip.style.left = Math.min(ev.clientX + 14, innerWidth - 270) + 'px';
  tip.style.top = ev.clientY + 14 + 'px';
});
renderer.domElement.addEventListener('pointerleave', () => { tip.hidden = true; hovered = null; });
renderer.domElement.addEventListener('pointerdown', (ev) => { down = { x: ev.clientX, y: ev.clientY }; tween = null; });
renderer.domElement.addEventListener('pointerup', (ev) => {
  if (!down) return;
  const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y);
  down = null;
  if (moved > 6) return;
  const h = pick(ev);
  if (h) select(h);
  else if (selected) closePanel();
});

// ---------- resize ----------
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  pMat.uniforms.uScale.value = (renderer.getDrawingBufferSize(new THREE.Vector2()).y / 2) / Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
  frame();
}
addEventListener('resize', resize);
addEventListener('resize', () => renderLabels());
resize();
let wasNarrow = camera.aspect < 0.8;
addEventListener('resize', () => { const n = camera.aspect < 0.8; if (n !== wasNarrow) { wasNarrow = n; camera.position.copy(home.pos); controls.target.copy(home.target); } });
camera.position.copy(home.pos);
controls.target.copy(home.target);
controls.update();

// ---------- animation ----------
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const cTmp = new THREE.Color();
const white = new THREE.Color('#ffffff');
let last = performance.now();
const frameTimes = [];
window.__map = { frameTimes, ready: false, reduced: REDUCED };

function writePulse(i, edgeId, t, reverse, color, scale, alpha, packet = false) {
  const o = edgeObj[edgeId];
  let n = i;
  for (let k = 0; k < TRAIL; k++) {
    let tt = t - k * (0.2 / o.length);
    if (tt < 0 || tt > 1) { pAlpha[n] = 0; n++; continue; }
    const u = reverse ? 1 - tt : tt;
    o.curve.getPoint(u, tmpA);
    pPos[n * 3] = tmpA.x; pPos[n * 3 + 1] = tmpA.y; pPos[n * 3 + 2] = tmpA.z;
    const fall = 1 - k / TRAIL;
    // ambient: heads 1.6x the first build, thin tails that fade out before the node; the flow packet stays full strength
    pSize[n] = packet ? (k === 0 ? 2.8 : 1.7 * fall + 0.2) * scale : (k === 0 ? 2.4 : 0.8 * fall + 0.08) * scale;
    const ends = packet ? 1 : Math.min(1, tt / 0.1, (1 - tt) / 0.1);
    pAlpha[n] = alpha * ends * (k === 0 ? 1 : (packet ? 0.85 : 0.6) * Math.pow(fall, packet ? 1.6 : 2.2)) * o.dim;
    pCol[n * 3] = color.r; pCol[n * 3 + 1] = color.g; pCol[n * 3 + 2] = color.b;
    n++;
  }
  return n;
}
function arrive(nodeId, power = 1) { nodeObj[nodeId].flash = Math.min(1.4, nodeObj[nodeId].flash + power); }

function tick(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  frameTimes.push(now - last);
  if (frameTimes.length > 900) frameTimes.shift();
  last = now;

  if (tween) {
    const k = Math.min(1, (now - tween.t0) / tween.ms), e = ease(k);
    controls.target.lerpVectors(tween.fromT, tween.toT, e);
    camera.position.lerpVectors(tween.fromP, tween.toP, e);
    if (k >= 1) tween = null;
  }
  // shift the scene left while the desktop panel is open so the subject is not covered
  // (on phones the bottom sheet covers the lower half, so the scene moves up instead)
  const open = !panel.hidden, wide = innerWidth > 760;
  const wantX = open && wide ? 200 : 0, wantY = open && !wide ? innerHeight * 0.5 - (barEl.getBoundingClientRect().bottom + panel.getBoundingClientRect().top) / 2 : 0;
  panelShift += (wantX - panelShift) * (REDUCED ? 1 : 0.12);
  panelShiftY += (wantY - panelShiftY) * (REDUCED ? 1 : 0.12);
  if (Math.abs(panelShift) > 0.5 || Math.abs(panelShiftY) > 0.5) camera.setViewOffset(innerWidth + panelShift * 2, innerHeight + panelShiftY * 2, panelShift * 2, panelShiftY * 2, innerWidth, innerHeight);
  else camera.clearViewOffset();
  controls.update();

  // dimming
  for (const o of Object.values(nodeObj)) {
    o.dim += ((o.dimTarget ?? 1) - o.dim) * 0.12;
    o.flash *= Math.pow(0.04, dt);
    const hov = hovered && hovered.kind === 'node' && nodeObj[hovered.id] === o ? 1.15 : 1;
    o.halo.scale.setScalar(o.baseHalo * (1 + 1.1 * o.flash) * hov);
    o.halo.material.opacity = Math.min(1, (0.32 + 0.6 * o.flash) * o.dim + 0.05);
    o.core.material.opacity = 0.2 + 0.8 * o.dim;
    o.shell.material.uniforms.uGain.value = (1.0 + 0.8 * o.flash) * o.dim;
    o.ring.material.opacity = 0.32 * o.dim;
    o.ring.rotation.y += dt * (REDUCED ? 0.03 : 0.12);
    if (o.cloud) { o.cloud.rotation.y += dt * (REDUCED ? 0.01 : 0.05); o.cloud.material.opacity = 0.5 * o.dim; }
  }
  for (const [id, o] of Object.entries(edgeObj)) {
    const hov = hovered && hovered.kind === 'edge' && hovered.id === id ? 2.2 : 1;
    o.dim += ((o.dimTarget ?? 1) - o.dim) * 0.12;
    o.parts.forEach((p, i) => { p.material.opacity = Math.min(0.95, o.baseOpacity[i] * o.dim * hov); });
  }

  // pulses
  let n = 0;
  const showAmbient = !flow;
  for (const p of ambient) {
    const e = edges[p.edge], o = edgeObj[p.edge];
    if (p.wait > 0) { p.wait -= dt; n = writePulse(n, p.edge, -1, p.reverse, white, 1, 0); continue; }
    p.t += (dt * PULSE_SPEED) / o.length;
    if (p.t > 1 + 0.2 * TRAIL / o.length) {
      p.t = 0;
      p.wait = (0.2 + Math.random() * (1.1 / (e.rate || 0.5))) * (REDUCED ? 8 : 1);
    }
    if (p.t >= 1 && !p.arrived) { arrive(p.reverse ? e.from : e.to, e.main ? 0.3 : 0.45); p.arrived = true; }
    if (p.t < 1) p.arrived = false;
    cTmp.set(p.reverse ? toneOf(nodes[e.to]) : o.color);
    n = writePulse(n, p.edge, showAmbient ? p.t : -1, p.reverse, cTmp, e.main ? 1.1 : 0.9, showAmbient ? 0.95 : 0);
  }
  for (const fp of flowPackets) {
    const raw = flow.edges[fp.step];
    const id = raw.replace(/^-/, ''), rev = raw.startsWith('-');
    const o = edgeObj[id];
    if (fp.wait > 0) fp.wait -= dt;
    else fp.t += (dt * PULSE_SPEED * 1.1) / o.length;
    if (fp.t >= 1) {
      const e = edges[id];
      arrive(rev ? e.from : e.to, 1);
      fp.step++; fp.t = 0; fp.wait = REDUCED ? 0.3 : 0.12;
      if (fp.step >= flow.edges.length) { fp.step = 0; fp.wait = 1.2; if (fp.once) { pendingClear = true; } }
      continue;
    }
    cTmp.set(TONE.speed).lerp(white, 0.2);
    n = writePulse(n, id, fp.wait > 0 ? -1 : fp.t, rev, cTmp, 1.05, 1, true);
  }
  if (pendingClear) { pendingClear = false; setFlow(null); }
  for (let i = n; i < MAXP; i++) pAlpha[i] = 0;
  for (const k of ['position', 'color', 'size', 'alpha']) pGeo.attributes[k].needsUpdate = true;

  renderer.render(scene, camera);
  placeLabels();
  window.__map.ready = true;
  requestAnimationFrame(tick);
}

const v = new THREE.Vector3();
const RANK = { node: 0, edge: 1, zone: 2 };
const barEl = document.querySelector('.bar');
function placeLabels() {
  const w = innerWidth, h = innerHeight;
  const safeTop = barEl.getBoundingClientRect().bottom + 4;
  const pr = panel.hidden ? null : panel.getBoundingClientRect();
  const safeBottom = pr && w <= 760 ? pr.top - 4 : h;
  const safeRight = pr && w > 760 ? pr.left - 4 : w;
  const live = [];
  for (const l of labels) {
    if (l.kind !== 'zone' && !l.show) continue;
    v.copy(l.anchor).applyMatrix4(root.matrixWorld).project(camera);
    if (v.z > 1 || Math.abs(v.x) > 1.2 || Math.abs(v.y) > 1.2) { l.el.style.opacity = 0; continue; }
    if (l.w === undefined || l.dirty) { l.w = l.el.offsetWidth; l.h = l.el.offsetHeight; l.dirty = false; }
    const key = (l.kind === 'node' ? 'n:' : l.kind === 'edge' ? 'e:' : 'z:') + l.id;
    const inFocus = related ? related.has(key) : true;
    const size = l.kind === 'node' ? nodes[l.id].size : 0;
    l.x = (v.x * 0.5 + 0.5) * w;
    l.y = (-v.y * 0.5 + 0.5) * h + (l.kind === 'edge' ? -10 : 4);
    l.prio = (inFocus ? 0 : 10) + RANK[l.kind] * 2 - size + (selected && key === (selected.kind === 'node' ? 'n:' : 'e:') + selected.id ? -20 : 0);
    l.focus = inFocus;
    live.push(l);
  }
  live.sort((a, b) => a.prio - b.prio);
  const placed = [];
  const overlap = (r) => placed.reduce((sum, q) => sum + Math.max(0, Math.min(r.x1, q.x1) - Math.max(r.x0, q.x0)) * Math.max(0, Math.min(r.y1, q.y1) - Math.max(r.y0, q.y0)), 0);
  for (const l of live) {
    // try below, above, right, left of the anchor before giving up; node labels are never dropped
    const c = l.kind === 'node' ? [[0, 0], [0, -l.h - 30], [l.w / 2 + 20, -l.h / 2 - 12], [-l.w / 2 - 20, -l.h / 2 - 12], [0, 14], [0, -l.h - 44]]
      : l.kind === 'edge' ? [[0, 0], [0, -l.h - 2], [0, l.h + 2]] : [[0, 0]];
    let best = null;
    for (const [dx, dy] of c) {
      const x = l.x + dx, y = l.y + dy;
      const r = { x0: x - l.w / 2 - 3, x1: x + l.w / 2 + 3, y0: y - 2, y1: y + l.h + 2, x, y };
      if (r.y0 < safeTop || r.y1 > safeBottom || r.x1 > safeRight || r.x0 < 0 || r.x1 > w) continue;
      const o = overlap(r);
      if (!best || o < best.o) best = { r, o };
      if (o === 0) break;
    }
    const keep = best && (best.o === 0 || l.kind === 'node');
    l.el.style.opacity = !keep ? 0 : l.kind === 'zone' ? (related ? 0.3 : 0.85) : l.focus ? 1 : 0.16;
    l.el.style.zIndex = l.kind === 'node' ? 2 : 1;
    if (!keep) continue;
    placed.push(best.r);
    l.el.style.transform = `translate(${(best.r.x - l.w / 2).toFixed(1)}px, ${best.r.y.toFixed(1)}px)`;
  }
}

// initial state from the URL (also used for captures)
applyFocus();
setMode(mode);
const startFlow = data.flows.find((f) => f.id === params.get('flow'));
if (startFlow) setFlow(startFlow);
const sel = params.get('select');
if (sel && (nodes[sel] || edges[sel])) { REDUCED || (tween = null); select({ kind: nodes[sel] ? 'node' : 'edge', id: sel }); }
if (params.get('panel') === 'index') openPanel(indexPanel());
// play "Ask a question" once on a plain load to lead the eye (never under reduced motion)
if (!REDUCED && !location.search) setFlow(data.flows.find((f) => f.id === 'ask'), true);
requestAnimationFrame(tick);
