// PINPOINT · 2D → 3D walkthrough.
// Swiss DXF plans are extruded from their real layers (WALL, WINDOW, DOOR, ROOM_OUTLINE, FIXTURE); IFC models use the
// tessellated model. The items counted by an answer glow inside the building; walk through it in first person.
import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/OrbitControls.js';
import { EffectComposer } from '/static/vendor/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from '/static/vendor/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from '/static/vendor/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from '/static/vendor/jsm/postprocessing/OutputPass.js';

const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/static/wow.css'; document.head.append(css);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = v => typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en') : v.toFixed(2)) : (v ?? '—');
const ease = t => 1 - Math.pow(1 - t, 3);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

const AMBER = new THREE.Color(1.0, 0.62, 0.12);
const V = { open: false, mode: 'orbit', keys: {}, items: [], sel: null, objs: [], pick: [], labels: [] };

// ------------------------------------------------------------------ DOM
function dom() {
  if (V.root) return;
  const d = document.createElement('div');
  d.id = 'walk'; d.className = 'wk'; d.hidden = true;
  d.innerHTML = `
  <canvas id="wkC"></canvas>
  <div class="wkLabels" id="wkL"></div>
  <div class="wkCross" id="wkCross"><i></i></div>
  <header class="wkTop">
    <div class="wkT"><span class="wkK">2D → 3D</span><b id="wkName">—</b><small id="wkSub"></small></div>
    <button class="wkTgl" id="wkLab" title="Room labels (L)">▦ rooms</button>
    <div class="wkSeg" id="wkSeg"><button data-v="orbit" class="on">◎ Orbit</button><button data-v="walk">🚶 Walk inside</button></div>
    <button class="wkX" id="wkX" title="Close (Esc)">✕</button>
  </header>
  <aside class="wkAns" id="wkAns" hidden>
    <div class="wkQ" id="wkQ"></div>
    <div class="wkV"><b id="wkVal"></b><span id="wkUnit"></span></div>
    <div class="wkM" id="wkMeth"></div>
    <div class="wkItems" id="wkItems"></div>
    <div class="wkNav"><button id="wkPrev">‹ prev</button><span id="wkStep">all</span><button id="wkNext">next ›</button></div>
  </aside>
  <div class="wkMiniW"><canvas id="wkMini" width="440" height="440"></canvas><span>plan · click to teleport</span></div>
  <div class="wkHere" id="wkHere"></div>
  <div class="wkInfo" id="wkInfo"></div>
  <div class="wkHelp" id="wkHelp"></div>
  <div class="wkLoad" id="wkLoad"><div class="wkRing"></div><b id="wkLoadT">Extruding the drawing…</b><small id="wkLoadS"></small></div>
  <footer class="wkFoot">
    <div class="wkStats" id="wkStats"></div>
    <div class="wkAssume" id="wkAssume"></div>
    <div class="wkCredit" id="wkCredit"></div>
  </footer>`;
  document.body.append(d);
  V.root = d;
  const q = s => d.querySelector(s);
  V.$ = q;
  q('#wkX').onclick = close;
  q('#wkSeg').onclick = e => { const b = e.target.closest('button'); if (b) setMode(b.dataset.v); };
  q('#wkLab').onclick = () => { V.roomLabels = !(V.roomLabels ?? !V.items.length); q('#wkLab').classList.toggle('on', V.roomLabels); };
  q('#wkPrev').onclick = () => step(-1);
  q('#wkNext').onclick = () => step(1);
  q('#wkMini').onclick = miniClick;
  addEventListener('keydown', e => {
    if (!V.open) return;
    if (e.target.tagName === 'INPUT') return;
    V.keys[e.code] = true;
    if (e.code === 'Escape') { if (document.pointerLockElement) return; if (V.mode === 'walk') setMode('orbit'); else close(); e.preventDefault(); }
    if (e.code === 'KeyN' || e.code === 'ArrowRight' && V.mode === 'orbit') step(1);
    if (e.code === 'KeyB' || e.code === 'ArrowLeft' && V.mode === 'orbit') step(-1);
    if (e.code === 'KeyL') V.$('#wkLab').click();
    if (e.code === 'KeyF') setMode(V.mode === 'walk' ? 'orbit' : 'walk');
    if (e.code === 'PageUp' || e.code === 'KeyE') storeyStep(1);
    if (e.code === 'PageDown' || e.code === 'KeyQ') storeyStep(-1);
    if (['Space', 'ArrowUp', 'ArrowDown'].includes(e.code)) e.preventDefault();
  });
  addEventListener('keyup', e => { V.keys[e.code] = false; });
  addEventListener('resize', () => V.open && resize());
}

// ------------------------------------------------------------------ renderer
function init() {
  if (V.renderer) return true;
  const canvas = V.$('#wkC');
  try { V.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' }); }
  catch (e) { return false; }
  const R = V.renderer;
  R.setPixelRatio(Math.min(devicePixelRatio, 2));
  R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = 1.0;
  R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFSoftShadowMap;
  V.scene = new THREE.Scene();
  V.scene.background = skyTexture();
  V.scene.fog = new THREE.Fog(0x0b1426, 60, 260);
  V.camera = new THREE.PerspectiveCamera(50, 1, 0.05, 2000);
  V.camera.position.set(0, 40, 0.01);
  V.controls = new OrbitControls(V.camera, canvas);
  V.controls.enableDamping = true; V.controls.dampingFactor = 0.08; V.controls.maxPolarAngle = Math.PI * 0.495;
  V.scene.add(new THREE.HemisphereLight(0xe8efff, 0x2a2016, 1.05));
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.1); sun.position.set(30, 45, 18);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.02;
  V.scene.add(sun); V.scene.add(sun.target); V.sun = sun;
  const fill = new THREE.DirectionalLight(0x8fb4ff, 0.55); fill.position.set(-30, 20, -25); V.scene.add(fill);
  V.eyeLight = new THREE.PointLight(0xfff3e0, 0, 9, 1.6); V.scene.add(V.eyeLight);
  V.ground = new THREE.Mesh(new THREE.CircleGeometry(400, 64), new THREE.MeshStandardMaterial({ color: 0x141c2b, roughness: 1 }));
  V.ground.rotation.x = -Math.PI / 2; V.ground.position.y = -0.24; V.ground.receiveShadow = true; V.scene.add(V.ground);
  V.grid = new THREE.GridHelper(400, 400, 0x24324d, 0x1a2539); V.grid.position.y = -0.235; V.grid.material.transparent = true; V.grid.material.opacity = .5; V.scene.add(V.grid);
  V.world = new THREE.Group(); V.world.rotation.x = -Math.PI / 2; V.scene.add(V.world);   // DXF/IFC Z-up -> three Y-up
  V.composer = new EffectComposer(R);
  V.composer.addPass(new RenderPass(V.scene, V.camera));
  V.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.85, 0.55, 0.92);
  V.composer.addPass(V.bloom);
  V.composer.addPass(new OutputPass());
  V.ray = new THREE.Raycaster();
  // first-person look
  canvas.addEventListener('click', () => { if (V.mode === 'walk' && !document.pointerLockElement) canvas.requestPointerLock?.(); });
  document.addEventListener('pointerlockchange', () => { V.$('#wkCross').classList.toggle('lock', document.pointerLockElement === canvas); help(); });
  let drag = null;
  canvas.addEventListener('mousedown', e => { if (V.mode === 'walk' && !document.pointerLockElement) drag = [e.clientX, e.clientY]; });
  addEventListener('mouseup', () => drag = null);
  addEventListener('mousemove', e => {
    if (!V.open || V.mode !== 'walk') return;
    let dx = 0, dy = 0;
    if (document.pointerLockElement === canvas) { dx = e.movementX; dy = e.movementY; }
    else if (drag) { dx = e.clientX - drag[0]; dy = e.clientY - drag[1]; drag = [e.clientX, e.clientY]; dx *= 1.4; dy *= 1.4; }
    else return;
    V.P.yaw -= dx * 0.0024; V.P.pitch = clamp(V.P.pitch - dy * 0.0024, -1.35, 1.35); V.P.anim = null;
  });
  canvas.addEventListener('dblclick', e => { if (V.mode === 'orbit') pickAt(e, true); });
  canvas.addEventListener('pointermove', e => { if (V.mode === 'orbit') V.mouse = e; });
  loop();
  return true;
}

function skyTexture() {
  const c = document.createElement('canvas'); c.width = 4; c.height = 256;
  const g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 0, 256);
  gr.addColorStop(0, '#05080f'); gr.addColorStop(0.55, '#0d1a31'); gr.addColorStop(1, '#1b2c4a');
  g.fillStyle = gr; g.fillRect(0, 0, 4, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

function resize() {
  const w = innerWidth, h = innerHeight;
  V.renderer.setSize(w, h, false); V.composer.setSize(w, h);
  V.bloom.resolution.set(w / 2, h / 2);
  V.camera.aspect = w / h; V.camera.updateProjectionMatrix();
}

// ------------------------------------------------------------------ materials
function plankTexture(base, line, w = 256, n = 8, tiles = false) {
  const c = document.createElement('canvas'); c.width = c.height = w;
  const g = c.getContext('2d'); g.fillStyle = base; g.fillRect(0, 0, w, w);
  g.strokeStyle = line; g.lineWidth = tiles ? 2 : 1.5;
  for (let i = 0; i <= n; i++) {
    g.beginPath(); g.moveTo(0, i * w / n); g.lineTo(w, i * w / n); g.stroke();
    if (tiles) { g.beginPath(); g.moveTo(i * w / n, 0); g.lineTo(i * w / n, w); g.stroke(); }
    else { const o = ((i * 97) % 5) * w / 5; g.beginPath(); g.moveTo(o, i * w / n); g.lineTo(o, (i + 1) * w / n); g.stroke(); }
  }
  if (!tiles) for (let k = 0; k < 900; k++) { g.fillStyle = `rgba(80,50,20,${Math.random() * 0.06})`; g.fillRect(Math.random() * w, Math.random() * w, 30 + Math.random() * 60, 1); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8; return t;
}
let MAT;
function mats() {
  if (MAT) return MAT;
  const oak = plankTexture('#c39a6b', 'rgba(70,40,15,.35)'); oak.repeat.set(0.55, 0.55);
  const tile = plankTexture('#d8dde0', 'rgba(90,100,110,.45)', 256, 8, true); tile.repeat.set(0.42, 0.42);
  const stone = plankTexture('#b9b3a8', 'rgba(60,55,50,.25)', 256, 4, true); stone.repeat.set(0.33, 0.33);
  const deck = plankTexture('#7d6a55', 'rgba(20,12,5,.5)', 256, 10); deck.repeat.set(0.6, 0.6);
  const std = (o) => new THREE.MeshStandardMaterial(Object.assign({ roughness: .85, metalness: 0 }, o));
  MAT = {
    wall: std({ color: 0xf1ede6, roughness: .92 }),
    cap: std({ color: 0x23293a, roughness: .7 }),
    oak: std({ map: oak, roughness: .6 }), tile: std({ map: tile, roughness: .35 }), stone: std({ map: stone, roughness: .8 }),
    deck: std({ map: deck, roughness: .9 }), plain: std({ color: 0xb9b2a6 }),
    ceil: std({ color: 0xf6f4ef, emissive: 0x8a8780, side: THREE.DoubleSide }),
    leaf: std({ color: 0x8f6a45, roughness: .55 }),
    glass: new THREE.MeshPhysicalMaterial({ color: 0x9fd6ff, roughness: .05, metalness: 0, transmission: 0, transparent: true, opacity: .28, depthWrite: false, side: THREE.DoubleSide }),
    frame: std({ color: 0x3b4252, roughness: .4, metalness: .3 }),
    ceramic: std({ color: 0xfafbfc, roughness: .18, metalness: .05 }),
    slab: std({ color: 0x5d636d, roughness: .95 }),
    sheet: new THREE.MeshBasicMaterial({ transparent: true, opacity: 1, side: THREE.DoubleSide, depthWrite: false }),
  };
  return MAT;
}
const FLOOR = [
  [/bad|bain|bagno|dusche|douche|doccia|wc|toilet|sdb|salle d'eau/i, 'tile'],
  [/küche|kueche|cuisine|cucina|kochen/i, 'stone'],
  [/balkon|balcon|loggia|terrass|terrazza|sitzplatz/i, 'deck'],
  [/korridor|flur|gang|entrée|entree|disimpegno|corridoio|treppe|escalier|scala|reduit|réduit|ripostiglio|abstell|vorplatz|hall|dégagement|ingresso|lift|keller|cave|cantina/i, 'stone'],
];
const floorMat = name => { for (const [re, k] of FLOOR) if (re.test(name || '')) return MAT[k]; return MAT.oak; };

// ------------------------------------------------------------------ geometry helpers (DXF metres, Z up)
const shape = (outer, holes) => {
  const s = new THREE.Shape(outer.map(p => new THREE.Vector2(p[0], p[1])));
  (holes || []).forEach(h => s.holes.push(new THREE.Path(h.map(p => new THREE.Vector2(p[0], p[1])))));
  return s;
};
function prism(outer, holes, z0, z1, mat, opts = {}) {
  const g = new THREE.ExtrudeGeometry(shape(outer, holes), { depth: z1 - z0, bevelEnabled: false, curveSegments: 4 });
  g.translate(0, 0, z0);
  const m = new THREE.Mesh(g, mat);
  m.castShadow = opts.cast !== false; m.receiveShadow = true;
  if (opts.info) { m.userData.info = opts.info; V.pick.push(m); }
  V.world.add(m); V.objs.push(m);
  return m;
}
const boxPoly = b => [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];

// ------------------------------------------------------------------ open / close
export async function openWalk({ path, q, name, items, answer, mode, sel } = {}) {
  dom();
  V.root.hidden = false; V.open = true; document.body.classList.add('wkOpen');
  if (!init()) { V.$('#wkLoadT').textContent = 'WebGL is not available in this browser.'; return; }
  resize();
  V.$('#wkLoad').hidden = false; V.$('#wkLoadT').textContent = 'Reading the drawing…'; V.$('#wkLoadS').textContent = '';
  V.$('#wkName').textContent = name || path.split('/').pop();
  const key = path + '|' + (q || '');
  try {
    const g = await (await fetch(`/api/walk?path=${encodeURIComponent(path)}&q=${encodeURIComponent(q || '')}`)).json();
    if (g.detail) throw new Error(g.detail);
    V.$('#wkCredit').innerHTML = g.credit ? `<b>Data:</b> ${esc(g.credit.credit)}${g.credit.licence ? ` · <i>${esc(g.credit.licence)}</i>` : ''}` : '';
    if (V.key !== path) { clearWorld(); V.key = path; V.g = g; if (g.kind === 'swiss') await buildSwiss(g); else await buildIfc(g); }
    let ans = g.answer;
    if (g.kind === 'ifc') ans = answer || (q ? await (await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, question: q }) })).json() : null);
    showAnswer(q, ans);
  } catch (e) {
    V.$('#wkLoadT').textContent = 'No 3D for this drawing'; V.$('#wkLoadS').textContent = String(e.message || e);
    return;
  }
  V.$('#wkLoad').hidden = true;
  setMode('orbit', true);
  if (mode === 'walk') setTimeout(() => setMode('walk', true), 3400);
  if (sel) setTimeout(() => select(+sel), mode === 'walk' ? 5000 : 3600);
  help();
}
export function close() {
  V.open = false; V.root.hidden = true; document.body.classList.remove('wkOpen');
  if (document.pointerLockElement) document.exitPointerLock();
  V.mode = 'orbit';
}
function clearWorld() {
  V.world.clear(); V.objs = []; V.pick = []; V.glow = []; V.items = []; V.sel = null;
  V.$('#wkL').innerHTML = ''; V.labels = []; V.ifc = null; V.coll = null; V.sheetMesh = null;
}

// ------------------------------------------------------------------ Swiss DXF -> 3D
async function buildSwiss(g) {
  mats();
  const H = g.heights;
  const [x0, y0, x1, y1] = g.bbox;
  V.center = [(x0 + x1) / 2, (y0 + y1) / 2];
  V.world.position.set(-V.center[0], 0, V.center[1]);
  V.span = Math.max(x1 - x0, y1 - y0);
  V.$('#wkSub').textContent = `Swiss DXF · ${g.stats.walls} wall bodies · ${g.stats.doors} doors · ${g.stats.windows} windows · ${g.stats.rooms} rooms · ${g.stats.fixtures} sanitary fixtures`;
  V.$('#wkLoadT').textContent = `Extruding ${g.stats.walls} walls, ${g.stats.doors} doors, ${g.stats.windows} windows`;
  V.$('#wkLoadS').textContent = 'from DXF layers WALL · DOOR · WINDOW · ROOM_OUTLINE · FIXTURE';
  V.$('#wkAssume').textContent = `Heights assumed (not in the DXF): storey ${H.storey} m clear · door head ${H.door} m · window sill ${H.sill} m, head ${H.head} m. All plan geometry is from the drawing.`;
  // the real printed sheet under the model
  if (g.sheet) {
    const tex = await blueprint(g.sheet.url).catch(() => null);
    if (tex) {
      tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
      const c = g.sheet.corners, geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute([...c[3], -0.2, ...c[2], -0.2, ...c[1], -0.2, ...c[0], -0.2], 3));
      geo.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
      geo.setIndex([0, 1, 2, 0, 2, 3]);
      const m = MAT.sheet.clone(); m.map = tex; m.opacity = 1;
      V.sheetMesh = new THREE.Mesh(geo, m); V.world.add(V.sheetMesh);
    }
  }
  // slab under the building
  const pad = 0.15;
  V.slab = prism(boxPoly([x0 - pad, y0 - pad, x1 + pad, y1 + pad]), null, -H.slab, -0.005, MAT.slab, { cast: false });
  V.slab.visible = false;
  // floors (+ ceilings for walk mode)
  V.ceil = [];
  g.rooms.forEach(r => {
    const info = { t: 'room', label: `${r.num}${r.name ? ' ' + r.name : ''}`, sub: r.area != null ? `${fmt(r.area)} m² net floor area${r.printed != null ? ` · label ${fmt(r.printed)} m²` : ''}${r.unit ? ` · apartment ${r.unit}` : ''}` : '' };
    const m = prism(r.poly, r.holes, -0.005, 0.0, floorMat(r.name), { cast: false, info }); m.userData.room = r; m.userData.rise = 'floor';
    if (!r.outdoor) { const c = prism(r.poly, r.holes, H.storey, H.storey + 0.02, MAT.ceil, { cast: false }); c.castShadow = false; c.visible = false; V.ceil.push(c); }
  });
  // walls: dark section-cut cap on top, plaster sides
  g.walls.forEach(w => { const m = prism(w.outer, w.holes, 0, H.storey, [MAT.cap, MAT.wall], { info: { t: 'wall', label: 'Wall', sub: 'from DXF layer WALL' } }); m.userData.rise = 'wall'; });
  // doors: lintel over the gap + the drawn leaf
  g.doors.forEach((d, i) => {
    const dinfo = { t: 'door', label: `Door`, sub: `${Math.round(d.width * 100)} cm clear opening (DXF threshold)` };
    let l = prism(d.gap, null, H.door, H.storey - 0.01, MAT.wall, { info: dinfo }); l.userData.rise = 'wall';
    l = prism(d.gap, null, H.storey - 0.01, H.storey, MAT.cap, { info: dinfo, cast: false }); l.userData.rise = 'wall';
    if (d.leaf) { const m = prism(d.leaf, null, 0.01, H.door - 0.02, MAT.leaf, { info: { t: 'door', label: 'Door leaf', sub: `${Math.round(d.width * 100)} cm opening` } }); m.userData.rise = 'wall'; }
  });
  // windows: parapet, glazing, lintel
  g.windows.forEach(w => {
    const info = { t: 'window', label: 'Window', sub: `${Math.round(w.width * 100)} cm wide (DXF frame)` };
    let m = prism(w.poly, null, 0, H.sill, MAT.wall, { info }); m.userData.rise = 'wall';
    m = prism(w.poly, null, H.head, H.storey - 0.01, MAT.wall, { info }); m.userData.rise = 'wall';
    m = prism(w.poly, null, H.storey - 0.01, H.storey, MAT.cap, { info, cast: false }); m.userData.rise = 'wall';
    m = prism(inset(w.poly, 0.12), null, H.sill, H.head, MAT.glass, { info, cast: false }); m.userData.rise = 'wall'; m.renderOrder = 3;
    m = prism(w.poly, null, H.sill - 0.04, H.sill, MAT.frame, { info }); m.userData.rise = 'wall';
  });
  // sanitary fixtures
  const FX = { WC: [0, 0.42], washbasin: [0.78, 0.88], bathtub: [0, 0.56], shower: [0, 0.05] };
  g.fixtures.forEach(f => {
    const [z0, z1] = FX[f.kind] || [0, 0.5];
    const info = { t: 'fixture', label: f.kind, sub: 'FIXTURE layer symbol' };
    let m = prism(boxPoly(shrink(f.bbox, 0.02)), null, z0, z1, MAT.ceramic, { info }); m.userData.rise = 'wall';
    if (f.kind === 'shower') { m = prism(boxPoly(shrink(f.bbox, 0.02)), null, 0.05, 2.0, MAT.glass, { info, cast: false }); m.userData.rise = 'wall'; }
    if (f.kind === 'washbasin') { const c = [(f.bbox[0] + f.bbox[2]) / 2, (f.bbox[1] + f.bbox[3]) / 2]; m = prism(boxPoly([c[0] - .06, c[1] - .06, c[0] + .06, c[1] + .06]), null, 0, 0.78, MAT.ceramic, { info }); m.userData.rise = 'wall'; }
  });
  // room labels (DOM, orbit view)
  g.rooms.forEach(r => {
    if (r.shaft) return;
    const c = centroid(r.poly);
    const d = document.createElement('div'); d.className = 'wkRoom' + (r.outdoor ? ' out' : '');
    d.innerHTML = `<b>${esc(r.num)}</b> ${esc(r.name || '')}<small>${r.area != null ? fmt(r.area) + ' m²' : ''}</small>`;
    V.$('#wkL').append(d); V.labels.push({ el: d, p: [c[0], c[1], 0.05], room: true });
  });
  buildCollision(g);
  V.levels = null;
  V.P = { x: g.spawn[0], y: g.spawn[1], z: 0, eye: 1.62, yaw: 0, pitch: -0.05, bob: 0 };
  facingOpen(V.P);
  V.storeyH = H.storey;
  riseIn();
}
const centroid = p => { let a = 0, x = 0, y = 0; for (let i = 0; i < p.length; i++) { const [x0, y0] = p[i], [x1, y1] = p[(i + 1) % p.length], f = x0 * y1 - x1 * y0; a += f; x += (x0 + x1) * f; y += (y0 + y1) * f; } return a ? [x / (3 * a), y / (3 * a)] : p[0]; };
const shrink = (b, d) => [b[0] + d, b[1] + d, b[2] - d, b[3] - d];
function inset(poly, frac) {   // shrink a thin window rectangle across its short side -> glazing pane in the middle of the wall
  const xs = poly.map(p => p[0]), ys = poly.map(p => p[1]);
  const b = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  const w = b[2] - b[0], h = b[3] - b[1];
  return w < h ? boxPoly([b[0] + w * (0.5 - frac / 0.5 * 0.25), b[1], b[2] - w * (0.5 - frac / 0.5 * 0.25), b[3]]) : boxPoly([b[0], b[1] + h * (0.5 - frac / 0.5 * 0.25), b[2], b[3] - h * (0.5 - frac / 0.5 * 0.25)]);
}

// the printed sheet as a glowing blueprint: dark ink -> cyan light, paper -> transparent (pixels unchanged otherwise)
async function blueprint(url) {
  const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const g = c.getContext('2d'); g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
  for (let i = 0; i < p.length; i += 4) {
    const a = p[i + 3] / 255, lum = (p[i] * .3 + p[i + 1] * .59 + p[i + 2] * .11) / 255;
    const ink = (1 - lum) * a;
    p[i] = 120; p[i + 1] = 220; p[i + 2] = 255; p[i + 3] = Math.min(255, ink * 330);
  }
  g.putImageData(d, 0, 0);
  const t = new THREE.CanvasTexture(c); t.anisotropy = 8; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// walls rise out of the printed sheet: the 2D -> 3D moment
function riseIn() {
  const t0 = performance.now();
  const walls = V.objs.filter(o => o.userData.rise === 'wall');
  const c = V.center;
  walls.forEach(m => { m.geometry.computeBoundingBox(); const b = m.geometry.boundingBox; m.userData.d = Math.hypot((b.min.x + b.max.x) / 2 - c[0], (b.min.y + b.max.y) / 2 - c[1]); m.scale.z = 0.001; });
  const floors = V.objs.filter(o => o.userData.rise === 'floor'); floors.forEach(m => { m.material = m.material; m.visible = false; });
  const maxd = Math.max(1, ...walls.map(m => m.userData.d));
  // camera: straight down (like the 2D sheet), then tilt into a 3/4 view as the walls rise
  const R = V.span * 0.95;
  V.camera.position.set(0.001, R * 1.15, 0.01); V.controls.target.set(0, 0, 0); V.controls.update();
  const camTo = new THREE.Vector3(R * 0.55, R * 0.62, R * 0.72);
  V.rise = now => {
    const t = (now - t0) / 1000;
    if (t > 0.5) floors.forEach(m => m.visible = true);
    walls.forEach(m => { const k = clamp((t - 0.7 - m.userData.d / maxd * 0.9) / 0.8, 0, 1); m.scale.z = Math.max(0.001, ease(k)); });
    if (V.sheetMesh) V.sheetMesh.material.opacity = 1 - 0.45 * clamp((t - 1.2) / 1.2, 0, 1);
    const k = ease(clamp((t - 0.5) / 2.2, 0, 1));
    if (V.mode === 'orbit' && !V.userMoved) { V.camera.position.lerpVectors(new THREE.Vector3(0.001, R * 1.15, 0.01), camTo, k); V.controls.target.set(0, 0, 0); }
    if (t > 3.2) { walls.forEach(m => m.scale.z = 1); V.slab.visible = true; V.rise = null; revealGlow(); }
  };
  V.controls.addEventListener('start', () => V.userMoved = true);
  V.userMoved = false;
}

// ------------------------------------------------------------------ collision grid (top-down raster of blocking geometry)
function buildCollision(g) {
  const [x0, y0, x1, y1] = g.bbox, pad = 3, res = 25;
  const W = Math.ceil((x1 - x0 + 2 * pad) * res), Hh = Math.ceil((y1 - y0 + 2 * pad) * res);
  const c = document.createElement('canvas'); c.width = W; c.height = Hh;
  const ctx = c.getContext('2d'); ctx.fillStyle = '#000';
  const tx = (x, y) => [(x - x0 + pad) * res, (y1 + pad - y) * res];
  const poly = (pts, holes) => { ctx.beginPath(); [pts, ...(holes || [])].forEach(r => { r.forEach((p, i) => { const [a, b] = tx(p[0], p[1]); i ? ctx.lineTo(a, b) : ctx.moveTo(a, b); }); ctx.closePath(); }); ctx.fill('evenodd'); };
  g.walls.forEach(w => poly(w.outer, w.holes));
  g.windows.forEach(w => poly(w.poly));
  g.fixtures.forEach(f => f.kind !== 'shower' && poly(boxPoly(f.bbox)));
  const data = ctx.getImageData(0, 0, W, Hh).data;
  V.coll = { W, H: Hh, res, x0: x0 - pad, y1: y1 + pad, data, canvas: c };
}
function blocked(x, y) {
  const C = V.coll; if (!C) return false;
  const i = Math.floor((x - C.x0) * C.res), j = Math.floor((C.y1 - y) * C.res);
  if (i < 0 || j < 0 || i >= C.W || j >= C.H) return true;
  return C.data[(j * C.W + i) * 4 + 3] > 40;
}
function free(x, y, r = 0.2) {
  if (blocked(x, y)) return false;
  for (let k = 0; k < 8; k++) { const a = k * Math.PI / 4; if (blocked(x + Math.cos(a) * r, y + Math.sin(a) * r)) return false; }
  return true;
}
function facingOpen(P) {   // look along the longest free sight line from the spawn point
  let best = 0, ba = 0;
  for (let k = 0; k < 24; k++) { const a = k / 24 * Math.PI * 2; let d = 0; while (d < 15 && !blocked(P.x + Math.cos(a) * d, P.y + Math.sin(a) * d)) d += 0.1; if (d > best) { best = d; ba = a; } }
  P.yaw = ba;
}
function sightClear(ax, ay, bx, by) {
  const d = Math.hypot(bx - ax, by - ay), n = Math.ceil(d / 0.05);
  for (let i = 1; i < n - 7; i++) if (blocked(ax + (bx - ax) * i / n, ay + (by - ay) * i / n)) return false;
  return true;
}

// ------------------------------------------------------------------ IFC model -> 3D
async function buildIfc(g) {
  mats();
  V.$('#wkLoadT').textContent = 'Tessellating the IFC model…';
  V.$('#wkLoadS').textContent = 'IfcOpenShell geometry · one mesh for the whole building';
  V.$('#wkAssume').textContent = 'Geometry is the IFC model itself (IfcOpenShell tessellation). Doors are walk-through; storeys from IfcBuildingStorey.';
  const buf = await (await fetch(g.mesh)).arrayBuffer();
  const hl = new DataView(buf).getUint32(0, true);
  const H = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl)));
  const nV = H.elements.reduce((a, e) => a + e.nv, 0), nI = H.elements.reduce((a, e) => a + e.ni, 0);
  const P = new Float32Array(buf, 4 + hl, nV * 3), I = new Uint32Array(buf, 4 + hl + nV * 12, nI);
  const C = new Float32Array(nV * 3);
  H.elements.forEach(e => { const c = e.rgb; for (let v = e.v0; v < e.v0 + e.nv; v++) { C[v * 3] = c[0]; C[v * 3 + 1] = c[1]; C[v * 3 + 2] = c[2]; } });
  const pos = new THREE.BufferAttribute(P, 3), col = new THREE.BufferAttribute(C, 3);
  const sub = els => { let n = 0; els.forEach(e => n += e.ni); const idx = new Uint32Array(n); let o = 0; els.forEach(e => { idx.set(I.subarray(e.i0, e.i0 + e.ni), o); o += e.ni; });
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', pos); geo.setAttribute('color', col); geo.setIndex(new THREE.BufferAttribute(idx, 1)); geo.computeVertexNormals(); return geo; };
  const base = H.elements.filter(e => e.cls !== 'IfcSpace');
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .8, flatShading: true, side: THREE.DoubleSide });
  const m = new THREE.Mesh(sub(base), mat); m.castShadow = m.receiveShadow = true; V.world.add(m); V.objs.push(m);
  V.ifcMesh = m;
  const bb = H.bbox;
  V.center = [(bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2];
  V.world.position.set(-V.center[0], 0, V.center[1]);
  V.span = Math.max(bb[3] - bb[0], bb[4] - bb[1], 4);
  // storeys: floor level = 20th percentile of element bottoms
  const st = {};
  H.elements.forEach(e => { let z = 1e9; for (let v = e.v0; v < e.v0 + e.nv; v++) z = Math.min(z, P[v * 3 + 2]); e.zmin = z; if (e.storey) (st[e.storey] = st[e.storey] || []).push(z); });
  V.levels = Object.entries(st).map(([k, zs]) => { zs.sort((a, b) => a - b); return { name: k, z: zs[Math.floor(zs.length * 0.2)], n: zs.length }; }).sort((a, b) => a.z - b.z);
  V.ifc = { H, P, I, sub, byGid: new Map() };
  H.elements.forEach(e => { (V.ifc.byGid.get(e.gid) || V.ifc.byGid.set(e.gid, []).get(e.gid)).push(e); });
  const counts = {}; H.elements.forEach(e => counts[e.cls] = (counts[e.cls] || 0) + 1);
  const top = ['IfcWall', 'IfcWallStandardCase', 'IfcDoor', 'IfcWindow', 'IfcSlab', 'IfcSpace'].filter(k => counts[k]).map(k => `${counts[k]} ${k.replace('Ifc', '').replace('StandardCase', ' (std)')}`);
  V.$('#wkSub').textContent = `IFC ${H.schema || ''} · ${H.elements.length.toLocaleString('en')} elements · ${top.join(' · ')}`;
  V.ground.position.y = bb[2] - 0.05; V.grid.position.y = bb[2] - 0.045;
  const lvl = V.levels.length ? V.levels.reduce((a, b) => b.n > a.n ? b : a) : { z: bb[2], name: null };
  ifcStorey(V.levels.indexOf(lvl));
  const R = V.span * 0.9;
  V.camera.position.set(R * 0.6, (bb[5] - bb[2]) + R * 0.5, R * 0.75); V.controls.target.set(0, (bb[2] + bb[5]) / 2, 0); V.controls.update();
  V.userMoved = false; V.controls.addEventListener('start', () => V.userMoved = true);
  V.rise = null; setTimeout(revealGlow, 300);
}
const BLOCK = /IfcWall|IfcColumn|IfcWindow|IfcCurtainWall|IfcRailing|IfcPlate|IfcMember|IfcFurnishing|IfcFlowTerminal|IfcSanitary|IfcBuildingElementProxy|IfcStair/;
function ifcStorey(i) {
  if (!V.ifc || !V.levels?.length) return;
  i = clamp(i, 0, V.levels.length - 1); V.lvl = i;
  const L = V.levels[i], z0 = L.z, { H, P, I } = V.ifc, bb = H.bbox;
  // raster blocking elements that cross the band 0.3-1.6 m above this floor
  const pad = 2, res = 20, x0 = bb[0] - pad, y1 = bb[4] + pad;
  const W = Math.ceil((bb[3] - bb[0] + 2 * pad) * res), Hh = Math.ceil((bb[4] - bb[1] + 2 * pad) * res);
  if (W * Hh > 4e7) { V.coll = null; return; }
  const c = document.createElement('canvas'); c.width = W; c.height = Hh; const ctx = c.getContext('2d');
  ctx.strokeStyle = ctx.fillStyle = '#000'; ctx.lineWidth = 0.08 * res;
  const tx = (x, y) => [(x - x0) * res, (y1 - y) * res];
  ctx.beginPath();
  H.elements.forEach(e => {
    if (!BLOCK.test(e.cls)) return;
    for (let k = e.i0; k < e.i0 + e.ni; k += 3) {
      const a = I[k], b = I[k + 1], d = I[k + 2];
      const za = P[a * 3 + 2], zb = P[b * 3 + 2], zd = P[d * 3 + 2];
      if (Math.max(za, zb, zd) < z0 + 0.3 || Math.min(za, zb, zd) > z0 + 1.6) continue;
      const p1 = tx(P[a * 3], P[a * 3 + 1]), p2 = tx(P[b * 3], P[b * 3 + 1]), p3 = tx(P[d * 3], P[d * 3 + 1]);
      ctx.moveTo(...p1); ctx.lineTo(...p2); ctx.lineTo(...p3); ctx.closePath();
    }
  });
  ctx.stroke();
  V.coll = { W, H: Hh, res, x0, y1, data: ctx.getImageData(0, 0, W, Hh).data, canvas: c };
  // spawn: centre of the largest IfcSpace on this storey, else the free cell nearest the model centre
  const spaces = H.elements.filter(e => e.cls === 'IfcSpace' && e.storey === L.name);
  let sp = null;
  const box = e => { let b = [1e9, 1e9, -1e9, -1e9]; for (let v = e.v0; v < e.v0 + e.nv; v++) { const x = P[v * 3], y = P[v * 3 + 1]; b = [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)]; } return b; };
  spaces.map(e => ({ e, b: box(e) })).sort((p, q) => (q.b[2] - q.b[0]) * (q.b[3] - q.b[1]) - (p.b[2] - p.b[0]) * (p.b[3] - p.b[1]))
    .some(({ b }) => { const x = (b[0] + b[2]) / 2, y = (b[1] + b[3]) / 2; if (free(x, y)) { sp = [x, y]; return true; } return false; });
  if (!sp) { const cx = V.center[0], cy = V.center[1]; for (let r = 0; r < 40 && !sp; r += 0.5) for (let k = 0; k < 16 && !sp; k++) { const x = cx + Math.cos(k / 16 * 6.283) * r, y = cy + Math.sin(k / 16 * 6.283) * r; if (free(x, y)) sp = [x, y]; } }
  sp = sp || V.center;
  const prev = V.P;
  V.P = { x: sp[0], y: sp[1], z: z0, eye: 1.62, yaw: prev?.yaw || 0, pitch: -0.05, bob: 0 };
  if (!prev) facingOpen(V.P);
  V.storeyH = (V.levels[i + 1]?.z ?? z0 + 3) - z0;
  // cut the model above this storey while walking so the sky is not hidden by upper floors
  V.ifcCut = z0 + Math.max(2.2, Math.min(V.storeyH - 0.05, 3.5));
  if (V.mode === 'walk') applyCut();
  help();
}
function applyCut() {
  if (!V.ifcMesh) return;
  const on = V.mode === 'walk';
  V.clip = V.clip || new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
  V.renderer.localClippingEnabled = true;
  V.ifcMesh.material.clippingPlanes = on ? [V.clip] : [];
  V.clip.constant = on ? V.ifcCut : 1e6;
  V.ifcMesh.material.needsUpdate = true;
}
function storeyStep(d) { if (V.ifc && V.levels?.length > 1) ifcStorey(V.lvl + d); }

// ------------------------------------------------------------------ answer + glowing evidence
function showAnswer(q, a) {
  const A = V.$('#wkAns');
  V.glow?.forEach(o => V.world.remove(o)); V.glow = [];
  V.labels = V.labels.filter(l => { if (l.item) { l.el.remove(); return false; } return true; });
  V.items = []; V.sel = null;
  if (!a || !q) { A.hidden = true; return; }
  A.hidden = false;
  V.$('#wkQ').textContent = q;
  const isText = a.unit === 'text';
  V.$('#wkVal').textContent = a.value == null ? 'no answer' : isText ? String(a.value).slice(0, 80) : fmt(a.value);
  V.$('#wkUnit').textContent = a.unit === 'count' ? 'found' : (!isText && a.unit) || '';
  V.$('#wkMeth').textContent = a.method || '';
  const items = (a.items || []).map((it, i) => ({ ...it, n: it.n || i + 1 }));
  V.items = items;
  const list = V.$('#wkItems'); list.innerHTML = '';
  items.slice(0, 300).forEach(it => {
    const v = it.value != null && a.unit && a.unit !== 'count' ? `${fmt(it.value)} ${a.unit}` : '';
    const b = document.createElement('button'); b.dataset.n = it.n;
    b.innerHTML = `<span>${it.n}</span>${esc(it.label || it.kind || '')}<i>${esc(v)}</i>`;
    b.onclick = () => select(it.n);
    b.onmouseenter = () => hover(it.n, true); b.onmouseleave = () => hover(it.n, false);
    list.append(b);
  });
  buildGlow(items);
}
const KIND_Z = { door: [0, 2.1], window: [0.9, 2.1], WC: [0, 0.45], basin: [0.7, 0.92], bathtub: [0, 0.6], shower: [0, 2.0] };
function glowMat(op) {
  return new THREE.MeshBasicMaterial({ color: AMBER.clone().multiplyScalar(2.2), transparent: true, opacity: op, depthWrite: false, toneMapped: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending });
}
function buildGlow(items) {
  V.glowData = [];
  items.forEach(it => {
    const grp = new THREE.Group(); grp.visible = false;
    let c, top;
    if (V.ifc && it.gid) {
      const els = [it.gid, ...(it.parts || [])].flatMap(g => V.ifc.byGid.get(g) || []);
      if (!els.length) return;
      const geo = V.ifc.sub(els);
      const core = new THREE.Mesh(geo, glowMat(0.55)); core.renderOrder = 6; grp.add(core);
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: new THREE.Color(3, 2.4, 1.4), toneMapped: false, transparent: true, opacity: .9 }));
      grp.add(e);
      geo.computeBoundingBox(); const b = geo.boundingBox;
      c = [(b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2]; top = b.max.z; it._z = [b.min.z, b.max.z];
    } else if (it.poly || it.bbox) {
      const poly = it.poly ? it.poly.slice(0, -1) : boxPoly(it.bbox);
      const z = KIND_Z[it.kind] || (it.poly ? [0, 0.08] : [0, 1.0]);
      const s = new THREE.ExtrudeGeometry(shape(it.poly ? poly : boxPoly(inflate(it.bbox, 0.04)), it.holes?.map(h => h.slice(0, -1))), { depth: z[1] - z[0], bevelEnabled: false });
      s.translate(0, 0, z[0] + 0.002);
      const core = new THREE.Mesh(s, glowMat(it.poly ? 0.45 : 0.6)); core.renderOrder = 6; grp.add(core);
      const xr = glowMat(it.poly ? 0.08 : 0.28); xr.depthTest = false; const xray = new THREE.Mesh(s, xr); xray.renderOrder = 7; xray.userData.xray = true; grp.add(xray);
      grp.add(new THREE.LineSegments(new THREE.EdgesGeometry(s, 20), new THREE.LineBasicMaterial({ color: new THREE.Color(3, 2.3, 1.2), toneMapped: false, transparent: true, opacity: .95 })));
      if (it.poly) {   // a curtain of light along the room outline
        const cs = new THREE.ExtrudeGeometry(shape(poly, it.holes?.map(h => h.slice(0, -1))), { depth: 1.2, bevelEnabled: false });
        const cm = glowMat(0.07); const curtain = new THREE.Mesh(cs, cm); curtain.renderOrder = 5; curtain.userData.curtain = true; grp.add(curtain);
      }
      const b = it.poly ? bounds(poly) : it.bbox;
      c = it.poly ? centroid(poly) : [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]; top = z[1]; it._z = z;
    } else return;
    // light beacon above the item
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1, 8, 1, true), glowMat(0.55));
    beam.rotation.x = Math.PI / 2; beam.position.set(c[0], c[1], top + 0.5); grp.add(beam); grp.userData.beam = beam;
    V.world.add(grp); V.glow.push(grp);
    const lab = document.createElement('div'); lab.className = 'wkTag'; lab.textContent = it.n; lab.title = it.label || '';
    lab.onclick = () => select(it.n); lab.style.display = 'none';
    V.$('#wkL').append(lab);
    const L = { el: lab, p: [c[0], c[1], Math.max(top, 2.6) + 1.3], pw: it.poly ? 1.2 : ((it._z[0] + it._z[1]) / 2), item: it.n, grp };
    V.labels.push(L);
    V.glowData.push({ it, grp, c, top, L, t0: 0 });
  });
  if (!V.rise) revealGlow();
}
const inflate = (b, d) => [b[0] - d, b[1] - d, b[2] + d, b[3] + d];
const bounds = p => { const xs = p.map(q => q[0]), ys = p.map(q => q[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; };
function revealGlow() {   // items light up one after another
  const now = performance.now();
  (V.glowData || []).forEach((g, i) => { g.t0 = now + Math.min(i * 90, 2200); });
}
function select(n) {
  V.sel = V.sel === n ? null : n;
  V.$('#wkItems').querySelectorAll('button').forEach(b => b.classList.toggle('on', +b.dataset.n === V.sel));
  const btn = V.$(`#wkItems button[data-n="${V.sel}"]`); btn?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  V.$('#wkStep').textContent = V.sel ? `${V.sel} / ${V.items.length}` : 'all';
  const g = V.glowData?.find(d => d.it.n === V.sel);
  if (g) goTo(g);
}
function hover(n, on) { const g = V.glowData?.find(d => d.it.n === n); if (g) g.hot = on; }
function step(d) {
  if (!V.items.length) return;
  const i = V.sel ? V.items.findIndex(x => x.n === V.sel) : -1;
  const k = ((i + d) % V.items.length + V.items.length) % V.items.length;
  V.sel = null; select(V.items[k].n);
}
function goTo(g) {
  const z = g.it._z || [0, 1], cz = (z[0] + z[1]) / 2;
  if (V.mode === 'walk' && g.it.poly) {
    const poly = g.it.poly.slice(0, -1), [cx, cy] = g.c;
    let best = null;
    for (let r = 0.6; r < 6; r += 0.3) for (let k = 0; k < 24; k++) {
      const a = k / 24 * Math.PI * 2, x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
      if (inPoly(x, y, poly) && free(x, y, 0.3) && sightClear(x, y, cx, cy)) best = { x, y };
    }
    if (!best && free(cx, cy)) best = { x: cx, y: cy };
    if (!best) return;
    const yaw = best.x === cx && best.y === cy ? V.P.yaw : Math.atan2(cy - best.y, cx - best.x);
    V.P.anim = { t0: performance.now(), from: { ...V.P }, to: { x: best.x, y: best.y, yaw: unwrap(V.P.yaw, yaw), pitch: -0.18 } };
    return;
  }
  if (V.mode === 'walk') {
    // stand where you can see it: nearest free spot 1.3-2.6 m away with a clear line of sight
    const z0 = V.P.z;
    let best = null;
    for (const r of [1.1, 1.5, 2.0, 2.6, 3.3, 0.8]) {
      for (let k = 0; k < 36; k++) {
        const a = k / 36 * Math.PI * 2, x = g.c[0] + Math.cos(a) * r, y = g.c[1] + Math.sin(a) * r;
        if (free(x, y) && indoors(x, y) && sightClear(x, y, g.c[0], g.c[1])) { const d = Math.hypot(x - V.P.x, y - V.P.y); if (!best || d < best.d) best = { x, y, d }; }
      }
      if (best) break;
    }
    if (!best) return;
    const yaw = Math.atan2(g.c[1] - best.y, g.c[0] - best.x);
    const pitch = Math.atan2((V.ifc ? cz : z0 + cz) - (z0 + 1.62), Math.hypot(g.c[0] - best.x, g.c[1] - best.y));
    V.P.anim = { t0: performance.now(), from: { ...V.P }, to: { x: best.x, y: best.y, yaw: unwrap(V.P.yaw, yaw), pitch } };
  } else {
    const t = new THREE.Vector3(g.c[0], g.c[1], cz).applyMatrix4(V.world.matrixWorld);
    const dir = V.camera.position.clone().sub(V.controls.target).normalize();
    if (dir.y < 0.5) { dir.y = 0.5; dir.normalize(); }
    const d = g.it.poly ? 9 : 6;
    flyOrbit(t.clone().add(dir.multiplyScalar(d)), t);
  }
}
const unwrap = (a, b) => { while (b - a > Math.PI) b -= 2 * Math.PI; while (b - a < -Math.PI) b += 2 * Math.PI; return b; };
function flyOrbit(pos, tgt, ms = 900) {
  V.userMoved = true;
  const p0 = V.camera.position.clone(), t0 = V.controls.target.clone(), s = performance.now();
  V.fly = now => { const k = ease(clamp((now - s) / ms, 0, 1)); V.camera.position.lerpVectors(p0, pos, k); V.controls.target.lerpVectors(t0, tgt, k); if (k >= 1) V.fly = null; };
}

// ------------------------------------------------------------------ modes
function setMode(m, quiet) {
  if (!V.P) return;
  V.$('#wkSeg').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === m));
  const was = V.mode; V.mode = m;
  V.root.classList.toggle('walking', m === 'walk');
  V.controls.enabled = m === 'orbit';
  V.ceil?.forEach(c => c.visible = m === 'walk');
  V.eyeLight.intensity = m === 'walk' ? 0.9 : 0;
  V.bloom.strength = m === 'walk' ? 0.5 : 0.85; V.bloom.threshold = m === 'walk' ? 1.05 : 0.92;
  applyCut();
  if (m === 'walk' && was !== 'walk') {
    // swoop down from the orbit camera to eye height
    const P = V.P, target = new THREE.Vector3(P.x, P.y, P.z + P.eye).applyMatrix4(V.world.matrixWorld);
    V.swoop = { t0: performance.now(), from: V.camera.position.clone(), q0: V.camera.quaternion.clone(), to: target };
    V.camera.near = 0.05; V.camera.fov = 70; V.camera.updateProjectionMatrix();
    V.scene.fog.near = 25; V.scene.fog.far = 120;
    if (!quiet) V.renderer.domElement.requestPointerLock?.();
  }
  if (m === 'orbit' && was === 'walk') {
    if (document.pointerLockElement) document.exitPointerLock();
    V.camera.fov = 50; V.camera.updateProjectionMatrix();
    V.scene.fog.near = 60; V.scene.fog.far = 260;
    const p = V.camera.position.clone();
    const dir = new THREE.Vector3(Math.cos(V.P.yaw), 0, -Math.sin(V.P.yaw));
    flyOrbit(p.clone().add(new THREE.Vector3(0, V.span * 0.6, 0)).sub(dir.multiplyScalar(V.span * 0.4)), p.clone().setY(p.y - 1.5), 1100);
  }
  help();
}
function help() {
  if (!V.root) return;
  const lock = !!document.pointerLockElement;
  const lv = V.levels?.length > 1 ? ` · <b>Q/E</b> storey (${esc(V.levels[V.lvl]?.name || '')})` : '';
  V.$('#wkHelp').innerHTML = V.mode === 'walk'
    ? (lock ? `<b>W A S D</b> walk · <b>mouse</b> look · <b>Shift</b> run · <b>N</b> next glowing item${lv} · <b>Esc</b> release mouse`
            : `<b>Click</b> to look with the mouse (or drag) · <b>W A S D</b> walk · <b>N</b> next item${lv} · <b>Esc</b> back to orbit`)
    : `<b>drag</b> orbit · <b>scroll</b> zoom · <b>right-drag</b> pan · <b>F</b> or <b>Walk inside</b> for first person · <b>← →</b> step items · <b>Esc</b> close`;
}

// ------------------------------------------------------------------ main loop
let last = performance.now(), infoT = 0;
function loop() {
  requestAnimationFrame(loop);
  if (!V.open) return;
  const now = performance.now(), dt = Math.min(0.05, (now - last) / 1000); last = now;
  V.rise?.(now);
  V.fly?.(now);
  if (V.mode === 'walk') walkStep(dt, now); else V.controls.update();
  // glow pulse + staggered reveal
  (V.glowData || []).forEach(g => {
    const on = g.t0 && now >= g.t0;
    g.grp.visible = on; g.L.el.style.display = on ? '' : 'none';
    if (!on) return;
    const age = (now - g.t0) / 1000, pop = age < .5 ? 1 + (1 - ease(age / .5)) * 1.5 : 1;
    const isSel = V.sel === g.it.n, dim = V.sel && !isSel && !g.hot;
    const k = (0.75 + 0.25 * Math.sin(now / 380 + g.it.n)) * pop * (isSel || g.hot ? 1.8 : dim ? 0.35 : 1);
    g.grp.children.forEach((c, i) => { if (c.material) c.material.opacity = Math.min(1, (c.userData.op ??= c.material.opacity) * k); });
    const beam = g.grp.userData.beam; if (beam) { const bh = V.mode === 'walk' ? 0.5 : Math.max(2.6, g.top) + 1.2 - g.top; beam.scale.y = bh * (1 + 0.3 * (pop - 1)); beam.position.z = g.top + beam.scale.y / 2; }
    g.grp.children.forEach(c => { if (c.userData.xray) c.visible = V.mode !== 'walk'; if (c.userData.curtain) c.visible = V.mode !== 'walk'; });
    if (V.mode === 'walk') g.grp.children.forEach(c => { if (c.material && !c.isLineSegments) c.material.opacity = Math.min(c.material.opacity * (g.it.poly ? 0.3 : 0.4), isSel ? 0.22 : 0.16); });
    g.L.el.classList.toggle('on', isSel); g.L.el.classList.toggle('dim', !!dim);
  });
  placeLabels();
  if (now - infoT > 120) { infoT = now; lookInfo(); drawMini(); }
  V.composer.render();
}

function walkStep(dt, now) {
  const P = V.P, K = V.keys;
  if (V.swoop) {
    const k = ease(clamp((now - V.swoop.t0) / 1300, 0, 1));
    const eye = new THREE.Vector3(P.x, P.y, P.z + P.eye).applyMatrix4(V.world.matrixWorld);
    V.camera.position.lerpVectors(V.swoop.from, eye, k);
    const q1 = new THREE.Quaternion().setFromEuler(new THREE.Euler(P.pitch, P.yaw - Math.PI / 2, 0, 'YXZ'));
    V.camera.quaternion.slerpQuaternions(V.swoop.q0, q1, k);
    if (k >= 1) V.swoop = null;
    return;
  }
  if (P.anim) {
    const a = P.anim, k = ease(clamp((now - a.t0) / 1100, 0, 1));
    P.x = a.from.x + (a.to.x - a.from.x) * k; P.y = a.from.y + (a.to.y - a.from.y) * k;
    P.yaw = a.from.yaw + (a.to.yaw - a.from.yaw) * k; P.pitch = a.from.pitch + (a.to.pitch - a.from.pitch) * k;
    if (k >= 1) P.anim = null;
  }
  const fwd = (K.KeyW || K.ArrowUp ? 1 : 0) - (K.KeyS || K.ArrowDown ? 1 : 0);
  const side = (K.KeyD ? 1 : 0) - (K.KeyA ? 1 : 0);
  if (K.ArrowLeft) P.yaw += dt * 1.8;
  if (K.ArrowRight) P.yaw -= dt * 1.8;
  if (fwd || side) {
    P.anim = null;
    const sp = (K.ShiftLeft || K.ShiftRight ? 3.4 : 1.5) * dt / Math.hypot(fwd, side);
    const dx = (Math.cos(P.yaw) * fwd + Math.sin(P.yaw) * side) * sp, dy = (Math.sin(P.yaw) * fwd - Math.cos(P.yaw) * side) * sp;
    if (free(P.x + dx, P.y + dy)) { P.x += dx; P.y += dy; }
    else if (free(P.x + dx, P.y)) P.x += dx;
    else if (free(P.x, P.y + dy)) P.y += dy;
    P.bob += dt * (K.ShiftLeft ? 11 : 7.5);
  }
  const bob = Math.sin(P.bob) * 0.022;
  V.camera.position.copy(new THREE.Vector3(P.x, P.y, P.z + P.eye + bob).applyMatrix4(V.world.matrixWorld));
  V.camera.quaternion.setFromEuler(new THREE.Euler(P.pitch, P.yaw - Math.PI / 2, 0, 'YXZ'));
  V.eyeLight.position.copy(V.camera.position);
}

const _v = new THREE.Vector3();
function placeLabels() {
  const w = innerWidth, h = innerHeight, walk = V.mode === 'walk';
  V.world.updateMatrixWorld();
  V.labels.forEach(L => {
    if (L.room && (walk || V.rise || (V.items.length && !V.roomLabels) || (!V.items.length && V.roomLabels === false))) { L.el.style.display = 'none'; return; }
    if (L.item && L.el.style.display === 'none') return;
    _v.set(L.p[0], L.p[1], (L.item && walk ? (V.ifc ? L.pw : V.P.z + L.pw) : (L.p[2] + (V.P && V.ifc && !L.item ? V.P.z : 0)))).applyMatrix4(V.world.matrixWorld);
    const dist = _v.distanceTo(V.camera.position);
    _v.project(V.camera);
    const vis = _v.z < 1 && Math.abs(_v.x) < 1.2 && Math.abs(_v.y) < 1.2 && !(L.room && dist > V.span * 2.2);
    L.el.style.display = vis ? '' : 'none';
    if (!vis) return;
    L.el.style.transform = `translate(${(_v.x + 1) / 2 * w}px, ${(1 - _v.y) / 2 * h}px) translate(-50%,-50%)`;
    if (L.item && walk) L.el.style.opacity = clamp(1.4 - dist / 14, 0.35, 1);
    else L.el.style.opacity = '';
  });
}

// what am I looking at / where am I
function lookInfo() {
  const info = V.$('#wkInfo'), here = V.$('#wkHere');
  if (V.mode !== 'walk' || V.swoop) { info.classList.remove('on'); here.classList.remove('on'); return; }
  V.ray.setFromCamera(new THREE.Vector2(0, 0), V.camera);
  V.ray.far = 12;
  const hit = V.ray.intersectObjects(V.pick, false)[0];
  const glow = V.glowData?.find(g => g.grp.visible && V.ray.intersectObject(g.grp, true).length);
  if (glow) {
    const it = glow.it;
    info.innerHTML = `<span class="n">${it.n}</span><b>${esc(it.label || it.kind)}</b><small>${it.value != null ? esc(fmt(it.value)) + (it.kind === 'room' || it.poly ? ' m² · ' : ' · ') : ''}in the answer${hit ? ' · ' + hit.distance.toFixed(1) + ' m away' : ''}</small>`;
    info.classList.add('on', 'gl');
  } else if (hit && hit.object.userData.info && hit.object.userData.info.t !== 'room' && hit.object.userData.info.t !== 'wall') {
    const i = hit.object.userData.info;
    info.innerHTML = `<b>${esc(i.label)}</b><small>${esc(i.sub || '')} · ${hit.distance.toFixed(1)} m away</small>`;
    info.classList.add('on'); info.classList.remove('gl');
  } else info.classList.remove('on', 'gl');
  // room you stand in
  const r = V.g?.rooms?.find(r => inPoly(V.P.x, V.P.y, r.poly));
  if (r) { here.innerHTML = `<small>you are in</small><b>${esc(r.num)} ${esc(r.name || '')}</b><span>${r.area != null ? fmt(r.area) + ' m²' : ''}${r.unit ? ' · apartment ' + esc(r.unit) : ''}</span>`; here.classList.add('on'); }
  else if (V.ifc && V.levels?.[V.lvl]) { here.innerHTML = `<small>storey</small><b>${esc(V.levels[V.lvl].name)}</b><span>floor at ${V.levels[V.lvl].z.toFixed(2)} m</span>`; here.classList.add('on'); }
  else here.classList.remove('on');
}
const indoors = (x, y) => !V.g?.rooms || V.g.kind !== 'swiss' || V.g.rooms.some(r => !r.outdoor && inPoly(x, y, r.poly));
function inPoly(x, y, p) { let c = false; for (let i = 0, j = p.length - 1; i < p.length; j = i++) { const [xi, yi] = p[i], [xj, yj] = p[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; }

function pickAt(e, fly) {
  const r = V.renderer.domElement.getBoundingClientRect();
  V.ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), V.camera); V.ray.far = 1e4;
  const hit = V.ray.intersectObjects(V.ifcMesh ? [V.ifcMesh, ...V.pick] : V.pick, false)[0];
  if (hit && fly) flyOrbit(V.camera.position.clone().lerp(hit.point, 0.6), hit.point);
}

// ------------------------------------------------------------------ minimap
function drawMini() {
  const cv = V.$('#wkMini'), C = V.coll; if (!C) return;
  const g = cv.getContext('2d'), W = cv.width, Hh = cv.height;
  g.clearRect(0, 0, W, Hh);
  const s = Math.min(W / C.W, Hh / C.H) * 0.98, ox = (W - C.W * s) / 2, oy = (Hh - C.H * s) / 2;
  V.mini = { s, ox, oy };
  g.save(); g.globalAlpha = 0.95;
  g.filter = 'invert(1) brightness(0.85)';
  g.drawImage(C.canvas, ox, oy, C.W * s, C.H * s);
  g.restore();
  const T = (x, y) => [ox + (x - C.x0) * C.res * s, oy + (C.y1 - y) * C.res * s];
  (V.glowData || []).forEach(d => {
    if (!d.grp.visible) return;
    const [a, b] = T(d.c[0], d.c[1]);
    g.fillStyle = V.sel === d.it.n ? '#fff' : '#ffb020'; g.shadowColor = '#ff9a00'; g.shadowBlur = 8;
    g.beginPath(); g.arc(a, b, V.sel === d.it.n ? 6 : 4, 0, 7); g.fill();
  });
  g.shadowBlur = 0;
  if (V.P) {
    const [a, b] = T(V.P.x, V.P.y);
    let yaw = V.P.yaw;
    if (V.mode === 'orbit') { const d = V.controls.target.clone().sub(V.camera.position); yaw = Math.atan2(-d.z, d.x); }
    if (V.mode === 'walk') {
      g.fillStyle = 'rgba(56,214,255,.25)'; g.beginPath(); g.moveTo(a, b); g.arc(a, b, 46, -yaw - 0.6, -yaw + 0.6); g.closePath(); g.fill();
      g.fillStyle = '#38d6ff'; g.beginPath(); g.arc(a, b, 6, 0, 7); g.fill(); g.strokeStyle = '#fff'; g.lineWidth = 2; g.stroke();
    }
  }
}
function miniClick(e) {
  if (!V.mini || !V.coll) return;
  const cv = V.$('#wkMini'), r = cv.getBoundingClientRect();
  const px = (e.clientX - r.left) / r.width * cv.width, py = (e.clientY - r.top) / r.height * cv.height;
  const C = V.coll, x = C.x0 + (px - V.mini.ox) / V.mini.s / C.res, y = C.y1 - (py - V.mini.oy) / V.mini.s / C.res;
  if (!free(x, y)) return;
  V.P.anim = { t0: performance.now(), from: { ...V.P }, to: { x, y, yaw: V.P.yaw, pitch: V.P.pitch } };
  if (V.mode !== 'walk') { V.P.x = x; V.P.y = y; V.P.anim = null; setMode('walk'); }
}

window.PPwalk = { open: openWalk, close, V };
