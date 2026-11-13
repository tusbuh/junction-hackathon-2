import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/OrbitControls.js';

const $ = s => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const SRC_NAMES = { swiss_dwellings: 'Swiss CAD', ifc_models: 'IFC models', ifc_bench: 'IFC bench', cubicasa5k: 'Finnish scans', opening_design: 'US sheets' };

const S = { cat: [], src: 'swiss_dwellings', file: null, total: 0, n: 0, last: null, view: 'sheet', blue: true };

// ============================================================ catalog / picker
async function boot() {
  S.cat = await (await fetch('/api/catalog')).json();
  renderSources();
  const P = new URLSearchParams(location.search);
  const first = S.cat.find(f => f.path === P.get('path')) || S.cat.find(f => f.path.includes('site1000_bldg2082_floor9385')) || S.cat[0];
  $('#sheetv').classList.toggle('blue', S.blue);
  selectFile(first);
  if (P.get('q')) { $('#q').value = P.get('q'); await ask(); if (P.get('view')) setTimeout(() => setView(P.get('view')), 300); }
}
function renderSources() {
  const counts = {};
  S.cat.forEach(f => counts[f.source] = (counts[f.source] || 0) + 1);
  const box = $('#srcs'); box.innerHTML = '';
  Object.keys(SRC_NAMES).filter(k => counts[k]).forEach(k => {
    const b = el('button', k === S.src ? 'on' : '', `${SRC_NAMES[k]}<i>${counts[k]}</i>`);
    b.onclick = () => { S.src = k; renderSources(); };
    box.append(b);
  });
  renderFiles();
}
function renderFiles() {
  const f = $('#filter').value.toLowerCase();
  const box = $('#files'); box.innerHTML = '';
  S.cat.filter(x => x.source === S.src && (!f || x.path.toLowerCase().includes(f))).slice(0, 400).forEach(x => {
    const b = el('button', S.file === x ? 'on' : '', `<span title="${esc(x.path)}">${esc(x.name)}</span><i>${x.n}q</i>`);
    b.onclick = () => selectFile(x);
    box.append(b);
  });
}
$('#filter').oninput = renderFiles;

function selectFile(f) {
  S.file = f; S.src = f.source; renderSources();
  $('#docName').textContent = f.path.replace(/^data\//, '');
  const chips = $('#chips'); chips.innerHTML = '';
  const seen = new Set();
  f.questions.filter(q => !seen.has(q.q) && seen.add(q.q)).slice(0, 40).forEach(q => {
    const b = el('button', '', esc(q.q)); b.title = q.q;
    b.onclick = () => { $('#q').value = q.q; ask(); };
    chips.append(b);
  });
  $('#q').value = f.questions[0]?.q || '';
  clearResult();
  $('#auditList').hidden = true; $('#auditSum').textContent = '';
  // show the drawing immediately (before any question)
  const isIfc = f.path.endsWith('.ifc');
  $('#tabs [data-t=sheet]').disabled = false;
  if (f.plan) { loadSheet(f.plan.url, 0, 0, true); setView('sheet'); }
  else if (!isIfc) { loadSheet(`/api/sheet?path=${encodeURIComponent(f.path)}`); setView('sheet'); }
  else { $('#sheetEmpty').textContent = 'This source is a 3D model — see the 3D tab.'; showSheet(false); SV.url = null; setView('model'); loadModel(f.path); }
  $('#tabs [data-t=model]').disabled = !(isIfc || f.source === 'ifc_models');
  if (f.source === 'ifc_models' && !isIfc) loadModel(ifcFor(f.path));
}
const ifcFor = p => p.endsWith('.ifc') ? p : p.replace(/_plan-.*$/, '').replace(/\.[^.]+$/, '') + '.ifc';

function clearResult() {
  $('#answer').hidden = true;
  $('#steps').innerHTML = '<li class="muted">How the answer was derived appears here, step by step.</li>';
  $('#ev').innerHTML = ''; $('#evN').textContent = '';
  drawOverlay([]); highlight3d([]);
}

// ============================================================ ask
$('#askForm').onsubmit = e => { e.preventDefault(); ask(); };
async function ask() {
  S.asked = true;
  const q = $('#q').value.trim(); if (!q || !S.file) return;
  const go = $('#go'); go.classList.add('busy');
  const t0 = performance.now();
  const r = await (await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: S.file.path, question: q }) })).json();
  go.classList.remove('busy');
  r.rtt = performance.now() - t0;
  S.last = r; show(r);
}

const fmtEur = v => {
  if (!v) return '€0';
  if (v >= 0.01) return '€' + v.toFixed(3);
  const d = Math.min(10, Math.max(2, 1 - Math.floor(Math.log10(v))));
  return '€' + v.toFixed(d);
};
const fmtVal = v => typeof v === 'number' ? (Number.isInteger(v) ? v.toString() : v.toFixed(2)) : (v ?? '—');

function show(r) {
  // answer card
  $('#answer').hidden = false;
  $('#answer').style.animation = 'none'; $('#answer').offsetHeight; $('#answer').style.animation = '';
  const isText = r.unit === 'text';
  $('#answer').classList.toggle('text', isText);
  $('#aVal').textContent = r.value == null ? 'no answer' : fmtVal(r.value);
  $('#aUnit').textContent = isText ? '' : r.unit && r.unit !== 'count' ? r.unit : (r.unit === 'count' ? 'found' : '');
  $('#aMethod').textContent = r.method || '';
  const bd = $('#aBadges'); bd.innerHTML = '';
  if ('truth' in r) {
    if (r.correct === true) bd.append(el('span', 'badge ok', `✓ matches ground truth ${esc(fmtVal(r.truth))}`));
    else if (r.correct === false) bd.append(el('span', 'badge bad', `✗ ground truth ${esc(fmtVal(r.truth))}`));
    else if (isText) { const b = el('span', 'badge', 'reference answer ▾'); b.title = String(r.truth); b.style.cursor = 'help'; bd.append(b); }
  }
  const checks = r.items.filter(i => i.check);
  const bad = checks.filter(i => !i.check.ok).length;
  if (checks.length) bd.append(el('span', 'badge ' + (bad ? 'warn' : 'ok'), bad ? `⚠ ${bad}/${checks.length} cross-checks disagree` : `✓ ${checks.length}/${checks.length} cross-checks agree`));
  bd.append(el('span', 'badge cy', `${r.items.length} cited · ${r.router === 'rules' ? 'rule router, 0 LLM' : esc(r.router)}`));
  // receipt
  const st = $('#steps'); st.innerHTML = '';
  (r.steps || []).forEach((s, i) => { const li = el('li', '', esc(s)); li.style.animationDelay = (i * 60) + 'ms'; st.append(li); });
  const ev = $('#ev'); ev.innerHTML = '';
  $('#evN').textContent = r.items.length || '';
  r.items.forEach((it, i) => {
    const warn = it.check && !it.check.ok;
    const sub = it.gid ? `${it.cls || ''} · ${it.gid}` : (it.kind || '');
    let v = it.value != null ? `${fmtVal(it.value)}${r.unit && r.unit !== 'count' ? ' ' + r.unit : ''}` : '';
    if (it.check) v += it.check.what === 'low confidence' ? `<small>low confidence</small>` : `<small>${warn ? '≠' : '='} ${it.check.what ? 'Qto' : 'label'} ${it.check.printed}</small>`;
    const row = el('div', 'e' + (warn ? ' warn' : ''), `<span class="n">${it.n}</span><span class="l">${esc(it.label || it.kind)}<small>${esc(sub)}</small></span><span class="v">${v}</span>`);
    row.style.animationDelay = Math.min(i * 25, 600) + 'ms';
    row.onmouseenter = () => hot(it.n, true); row.onmouseleave = () => hot(it.n, false);
    row.onclick = () => focusItem(it);
    ev.append(row);
  });
  if (r.items.length > 1 && r.unit && r.unit !== 'count' && r.unit !== 'text' && r.value != null) ev.append(el('div', 'sum', `<span>Σ ${r.items.length} items</span><b>${fmtVal(r.value)} ${esc(r.unit)}</b>`));
  // cost meter
  const c = r.cost || {};
  S.total += c.total_eur || 0; S.n++;
  $('#mLast').textContent = fmtEur(c.total_eur);
  $('#mLat').textContent = `${Math.round((c.seconds || 0) * 1000)} ms`;
  $('#mLlm').textContent = c.llm_calls || 0;
  $('#mTot').textContent = fmtEur(S.total); $('#mN').textContent = S.n;
  $('#mVlm').textContent = fmtEur(c.vlm_baseline_eur);
  $('#mSave').textContent = c.total_eur ? `${Math.round(c.vlm_baseline_eur / c.total_eur).toLocaleString('en')}×` : '∞';
  document.querySelectorAll('.meter .m').forEach(m => { m.classList.remove('flash'); m.offsetWidth; m.classList.add('flash'); });
  // views
  const v = r.view || {};
  if (v.kind === 'sheet') { loadSheet(v.url, v.w, v.h).then(() => { drawOverlay(r.items); fitEvidence(); }); setView('sheet'); }
  else if (v.kind === 'model') {
    $('#tabs [data-t=model]').disabled = false;
    if (v.sheet) { $('#tabs [data-t=sheet]').disabled = false; loadSheet(v.sheet.url, v.sheet.w, v.sheet.h, v.sheet.inline).then(() => drawOverlay(r.items)); }
    else { $('#tabs [data-t=sheet]').disabled = true; drawOverlay([]); }
    loadModel(r.model).then(() => highlight3d(r.items, r.storey));
    setView('model');
  } else drawOverlay([]);
}

// ============================================================ 2D sheet viewer
// Content lives in "user units" (PDF points, image pixels, or the plan SVG's viewBox units).
// SV.vb = [x0, y0, w, h] in user units; SV.k = CSS px per unit inside the pan layer; SV.s/x/y = zoom + pan.
const SV = { s: 1, x: 0, y: 0, vb: [0, 0, 1, 1], k: 1, url: null, items: [], inline: false };
const U2P = (ux, uy) => [SV.x + (ux - SV.vb[0]) * SV.k * SV.s, SV.y + (uy - SV.vb[1]) * SV.k * SV.s];
function showSheet(on) { $('#pan').style.display = on ? '' : 'none'; $('#sheetEmpty').style.display = on ? 'none' : ''; }
function sizeLayers() {
  const W = SV.vb[2] * SV.k, H = SV.vb[3] * SV.k;
  const host = SV.inline ? $('#svgHost') : $('#sheetImg');
  host.style.width = W + 'px'; host.style.height = H + 'px';
  const ov = $('#ov'); ov.setAttribute('viewBox', SV.vb.join(' ')); ov.style.width = W + 'px'; ov.style.height = H + 'px';
}
async function loadSheet(url, w, h, inline) {
  if (SV.url === url) { showSheet(true); return; }
  SV.url = url; SV.inline = !!inline;
  let host = $('#svgHost');
  if (!host) { host = el('div'); host.id = 'svgHost'; host.className = 'svghost'; $('#pan').prepend(host); }
  host.style.display = inline ? '' : 'none'; $('#sheetImg').style.display = inline ? 'none' : '';
  if (inline) {
    host.innerHTML = await (await fetch(url)).text();
    const svg = host.querySelector('svg'); svg.removeAttribute('width'); svg.removeAttribute('height');
    svg.style.width = '100%'; svg.style.height = '100%';
    SV.vb = svg.getAttribute('viewBox').split(/[ ,]+/).map(Number);
    SV.k = 1600 / Math.max(SV.vb[2], SV.vb[3]);
  } else {
    const img = $('#sheetImg');
    await new Promise(res => { img.onload = res; img.src = url; });
    SV.vb = [0, 0, w || img.naturalWidth, h || img.naturalHeight];
    SV.k = 1;
  }
  sizeLayers(); showSheet(true); fitBox([SV.vb[0], SV.vb[1], SV.vb[0] + SV.vb[2], SV.vb[1] + SV.vb[3]], 20, false);
}
function applyT() { $('#pan').style.transform = `translate(${SV.x}px,${SV.y}px) scale(${SV.s})`; placeLabels2d(); }
function fitBox(b, pad = 40, anim = true) {
  const V = $('#sheetv').getBoundingClientRect(); if (!V.width) return;
  const bw = Math.max(b[2] - b[0], 1e-6) * SV.k, bh = Math.max(b[3] - b[1], 1e-6) * SV.k;
  const s = Math.min((V.width - 2 * pad) / bw, (V.height - 2 * pad) / bh, 14);
  const cx = (b[0] - SV.vb[0]) * SV.k + bw / 2, cy = (b[1] - SV.vb[1]) * SV.k + bh / 2;
  const tx = V.width / 2 - s * cx, ty = V.height / 2 - s * cy;
  if (!anim) { Object.assign(SV, { s, x: tx, y: ty }); return applyT(); }
  const a = { s: SV.s, x: SV.x, y: SV.y }, t0 = performance.now(), D = 650;
  const ease = t => 1 - Math.pow(1 - t, 3);
  (function step(now) {
    const t = Math.min(1, (now - t0) / D), e = ease(t);
    SV.s = a.s + (s - a.s) * e; SV.x = a.x + (tx - a.x) * e; SV.y = a.y + (ty - a.y) * e; applyT();
    if (t < 1) requestAnimationFrame(step);
  })(t0);
}
function fitEvidence() {
  const full = [SV.vb[0], SV.vb[1], SV.vb[0] + SV.vb[2], SV.vb[1] + SV.vb[3]];
  if (!SV.items.length) return fitBox(full);
  const b = SV.items.reduce((a, it) => [Math.min(a[0], it.bbox[0]), Math.min(a[1], it.bbox[1]), Math.max(a[2], it.bbox[2]), Math.max(a[3], it.bbox[3])], [1e12, 1e12, -1e12, -1e12]);
  const m = Math.max(b[2] - b[0], b[3] - b[1]) * 0.12 + Math.max(SV.vb[2], SV.vb[3]) * 0.01;
  fitBox([b[0] - m, b[1] - m, b[2] + m, b[3] + m]);
}
$('#fitBtn').onclick = () => S.view === 'sheet' ? fitEvidence() : fit3d();
$('#tglTheme').onclick = () => { S.blue = !S.blue; $('#sheetv').classList.toggle('blue', S.blue); $('#tglTheme').textContent = S.blue ? '◐ blueprint' : '◑ paper'; };
(() => {
  const v = $('#sheetv'); let d = null;
  v.addEventListener('wheel', e => {
    e.preventDefault();
    const r = v.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), s = Math.min(Math.max(SV.s * k, 0.02), 60);
    SV.x = mx - (mx - SV.x) * s / SV.s; SV.y = my - (my - SV.y) * s / SV.s; SV.s = s; applyT();
  }, { passive: false });
  v.addEventListener('pointerdown', e => { if (e.target.closest('.it')) return; d = { x: e.clientX - SV.x, y: e.clientY - SV.y }; v.classList.add('drag'); v.setPointerCapture(e.pointerId); });
  v.addEventListener('pointermove', e => { if (!d) return; SV.x = e.clientX - d.x; SV.y = e.clientY - d.y; applyT(); });
  v.addEventListener('pointerup', () => { d = null; v.classList.remove('drag'); });
})();
const NS = 'http://www.w3.org/2000/svg';
function drawOverlay(items) {
  const ov = $('#ov'); ov.innerHTML = '';
  document.querySelectorAll('#svgHost .gl').forEach(g => g.classList.remove('gl', 'hot'));
  SV.items = [];
  // IFC plan: highlight the plan's own elements by GlobalId (data-guid), no geometric fitting needed
  if (SV.inline) {
    items.filter(i => i.gid).forEach(it => {
      const gs = [it.gid, ...(it.parts || [])].flatMap(g => [...document.querySelectorAll(`#svgHost [data-guid="${CSS.escape(g)}"]`)]);
      if (!gs.length) return;
      let b = [1e12, 1e12, -1e12, -1e12];
      gs.forEach(g => { g.classList.add('gl'); g.dataset.n = it.n; const bb = g.getBBox(); b = [Math.min(b[0], bb.x), Math.min(b[1], bb.y), Math.max(b[2], bb.x + bb.width), Math.max(b[3], bb.y + bb.height)]; });
      if (b[2] > b[0]) SV.items.push({ ...it, bbox: b, kind: it.cls === 'IfcSpace' ? 'room' : it.kind, plan: true });
    });
  } else SV.items = items.filter(i => i.bbox && !i.gid);
  let L = $('#labels2d'); if (!L) { L = el('div', 'labels3d'); L.id = 'labels2d'; $('#sheetv').append(L); }
  L.innerHTML = '';
  const many = SV.items.length > 60;
  SV.items.forEach((it, i) => {
    const warn = it.check && !it.check.ok;
    if (!it.plan) {
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('class', `it ${it.kind || ''}${warn ? ' warn' : ''}`); g.dataset.n = it.n;
      g.style.animationDelay = Math.min(i * 45, 1500) + 'ms';
      let sh;
      if (it.poly) { sh = document.createElementNS(NS, 'polygon'); sh.setAttribute('points', it.poly.map(p => p.join(',')).join(' ')); }
      else {
        const p = Math.max(Math.max(SV.vb[2], SV.vb[3]) * 0.001, Math.min(it.bbox[2] - it.bbox[0], it.bbox[3] - it.bbox[1]) * 0.12);
        sh = document.createElementNS(NS, 'rect');
        sh.setAttribute('x', it.bbox[0] - p); sh.setAttribute('y', it.bbox[1] - p);
        sh.setAttribute('width', it.bbox[2] - it.bbox[0] + 2 * p); sh.setAttribute('height', it.bbox[3] - it.bbox[1] + 2 * p); sh.setAttribute('rx', p);
      }
      sh.setAttribute('class', 'shape'); g.append(sh);
      g.onmouseenter = () => hot(it.n, true); g.onmouseleave = () => hot(it.n, false);
      ov.append(g);
    }
    const txt = it.kind === 'room' && it.value != null ? `${it.n} · ${fmtVal(it.value)} m²` : it.n;
    const lab = el('div', many && it.kind !== 'room' ? 'dot' : '', txt);
    lab.dataset.n = it.n; lab.style.opacity = 0; lab.style.transition = 'opacity .3s'; lab.style.transitionDelay = Math.min(i * 45, 1500) + 200 + 'ms';
    if (warn) lab.style.background = 'var(--bad)';
    L.append(lab); requestAnimationFrame(() => lab.style.opacity = 1);
  });
  placeLabels2d();
}
// getBBox only works once the inline SVG is visible and laid out: retry for a few frames
function redrawPlan(r, tries) {
  requestAnimationFrame(() => {
    drawOverlay(r.items);
    const ok = SV.items.length && SV.items.some(it => it.bbox[2] > it.bbox[0]);
    if (ok) { S.lastDrawn = r; fitEvidence(); } else if (tries < 30) redrawPlan(r, tries + 1);
  });
}
function placeLabels2d() {
  const L = $('#labels2d'); if (!L) return;
  [...L.children].forEach((lab, i) => {
    const it = SV.items[i]; if (!it) return;
    const room = it.kind === 'room';
    const [x, y] = U2P(room ? (it.bbox[0] + it.bbox[2]) / 2 : it.bbox[2], room ? (it.bbox[1] + it.bbox[3]) / 2 : it.bbox[1]);
    lab.style.left = x + 'px'; lab.style.top = y + 'px';
  });
}
function hot(n, on) {
  document.querySelectorAll(`.ov .it[data-n="${n}"], #svgHost .gl[data-n="${n}"]`).forEach(g => g.classList.toggle('hot', on));
  document.querySelectorAll(`#labels2d [data-n="${n}"], #labels3d [data-n="${n}"]`).forEach(g => g.classList.toggle('hot', on));
  document.querySelectorAll('#ev .e').forEach(r => r.classList.toggle('hot', on && r.querySelector('.n').textContent == n));
  if (S.view === 'model') hot3d(on ? n : null);
}
function focusItem(it) {
  const p2 = SV.items.find(x => x.n === it.n);
  if (it.gid && (S.view === 'model' || !p2)) { setView('model'); focus3d(it); return; }
  if (!p2) return;
  setView('sheet');
  const b = p2.bbox, m = Math.max(b[2] - b[0], b[3] - b[1]) * 1.2 + Math.max(SV.vb[2], SV.vb[3]) * 0.01;
  fitBox([b[0] - m, b[1] - m, b[2] + m, b[3] + m]);
  const ov = $('#ov'); const p = document.createElementNS(NS, 'rect');
  p.setAttribute('class', 'pulse'); p.setAttribute('x', b[0]); p.setAttribute('y', b[1]); p.setAttribute('width', b[2] - b[0]); p.setAttribute('height', b[3] - b[1]);
  ov.append(p); setTimeout(() => p.remove(), 2400);
}

// ============================================================ tabs
document.querySelectorAll('#tabs [data-t]').forEach(b => b.onclick = () => !b.disabled && setView(b.dataset.t));
function setView(t) {
  S.view = t;
  document.querySelectorAll('#tabs [data-t]').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  $('#sheetv').hidden = t !== 'sheet'; $('#modelv').hidden = t !== 'model';
  $('#tglTheme').style.display = t === 'sheet' ? '' : 'none';
  if (t === 'model') { T.resize(); }
  if (t === 'sheet' && S.last && SV.inline && S.lastDrawn !== S.last) redrawPlan(S.last, 0);
}

// ============================================================ 3D model viewer
const T = { inited: false, path: null, loading: null, hl: [] };
function init3d() {
  if (T.inited) return; T.inited = true;
  const canvas = $('#three');
  T.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  T.renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); T.renderer.localClippingEnabled = true;
  T.renderer.toneMapping = THREE.ACESFilmicToneMapping; T.renderer.toneMappingExposure = 1.05;
  T.scene = new THREE.Scene();
  T.scene.background = new THREE.Color(0x0a1222);
  T.scene.fog = new THREE.Fog(0x0a1222, 200, 900);
  T.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
  T.controls = new OrbitControls(T.camera, canvas); T.controls.enableDamping = true; T.controls.dampingFactor = 0.08;
  T.scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x1a1408, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(60, 120, 80); T.scene.add(sun);
  const fill = new THREE.DirectionalLight(0x88aaff, 0.5); fill.position.set(-80, 40, -60); T.scene.add(fill);
  T.root = new THREE.Group(); T.root.rotation.x = -Math.PI / 2; T.scene.add(T.root);
  T.grid = new THREE.GridHelper(400, 80, 0x2a3a5a, 0x152036); T.scene.add(T.grid);
  T.ray = new THREE.Raycaster();
  new ResizeObserver(() => T.resize()).observe($('#modelv'));
  canvas.addEventListener('click', pick3d);
  (function loop() { requestAnimationFrame(loop); T.controls.update(); if (T.hlMat) T.hlMat.emissiveIntensity = 0.55 + 0.25 * Math.sin(performance.now() / 300); T.renderer.render(T.scene, T.camera); place3dLabels(); })();
}
T.resize = () => {
  if (!T.inited) return;
  const r = $('#modelv').getBoundingClientRect(); if (!r.width) return;
  T.renderer.setSize(r.width, r.height, false); T.camera.aspect = r.width / r.height; T.camera.updateProjectionMatrix();
};
async function loadModel(path) {
  init3d();
  if (T.path === path) return T.loading;
  T.path = path; $('#modelEmpty').style.display = 'none';
  $('#load3d').hidden = false;
  T.loading = (async () => {
    const buf = await (await fetch(`/api/mesh?path=${encodeURIComponent(path)}`)).arrayBuffer();
    if (T.path !== path) return;
    const hl = new DataView(buf).getUint32(0, true);
    const H = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl)));
    const nV = H.elements.reduce((a, e) => a + e.nv, 0), nI = H.elements.reduce((a, e) => a + e.ni, 0);
    const P = new Float32Array(buf, 4 + hl, nV * 3), I = new Uint32Array(buf, 4 + hl + nV * 12, nI);
    T.root.clear();
    T.H = H; T.byGid = new Map(); H.elements.forEach((e, k) => { e.k = k; (T.byGid.get(e.gid) || T.byGid.set(e.gid, []).get(e.gid)).push(e); });
    // per-storey floor level = 20th percentile of its elements' lowest z (robust to tall elements)
    const st = {};
    H.elements.forEach(e => { let z = 1e9; for (let v = e.v0; v < e.v0 + e.nv; v++) z = Math.min(z, P[v * 3 + 2]); if (e.storey) (st[e.storey] = st[e.storey] || []).push(z); });
    T.levels = Object.fromEntries(Object.entries(st).map(([k, zs]) => { zs.sort((a, b) => a - b); return [k, zs[Math.floor(zs.length * 0.2)]]; }));
    const C = new Float32Array(nV * 3);
    H.elements.forEach(e => { const c = e.rgb; for (let v = e.v0; v < e.v0 + e.nv; v++) { C[v * 3] = c[0]; C[v * 3 + 1] = c[1]; C[v * 3 + 2] = c[2]; } });
    T.pos = new THREE.BufferAttribute(P, 3); T.col = new THREE.BufferAttribute(C, 3);
    // base mesh: everything except spaces
    const base = H.elements.filter(e => e.cls !== 'IfcSpace');
    const { geo, map } = subset(base, I);
    T.baseMap = map; T.I = I;
    T.clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
    T.baseMat = new THREE.MeshStandardMaterial({ clippingPlanes: [T.clip], vertexColors: true, roughness: .78, metalness: .02, flatShading: true, side: THREE.DoubleSide, transparent: true, opacity: 1 });
    T.base = new THREE.Mesh(geo, T.baseMat); T.root.add(T.base);
    T.edges = null;
    if (geo.index.count < 4e6) {  // crisp architectural outlines
      T.edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: 0x0b1222, transparent: true, opacity: .35, clippingPlanes: [T.clip] }));
      T.root.add(T.edges);
    }
    const bb = H.bbox; T.bbox = bb;
    T.grid.position.set(0, bb[2] - 0.02, 0);
    T.root.position.set(-(bb[0] + bb[3]) / 2, 0, (bb[1] + bb[4]) / 2);
    T.grid.scale.setScalar(Math.max(bb[3] - bb[0], bb[4] - bb[1]) / 200 * 1.6);
    fit3d(false);
    $('#load3d').hidden = true;
  })();
  return T.loading;
}
function subset(els, I) {
  let n = 0; els.forEach(e => n += e.ni);
  const idx = new Uint32Array(n); const map = []; let o = 0;
  els.forEach(e => { idx.set(I.subarray(e.i0, e.i0 + e.ni), o); map.push([o, e]); o += e.ni; });
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', T.pos); geo.setAttribute('color', T.col); geo.setIndex(new THREE.BufferAttribute(idx, 1));
  return { geo, map };
}
function elemBox(els) {
  const P = T.pos.array, b = [1e9, 1e9, 1e9, -1e9, -1e9, -1e9];
  els.forEach(e => { for (let v = e.v0; v < e.v0 + e.nv; v++) for (let k = 0; k < 3; k++) { const x = P[v * 3 + k]; if (x < b[k]) b[k] = x; if (x > b[k + 3]) b[k + 3] = x; } });
  return b;
}
const toWorld = (x, y, z) => new THREE.Vector3(x, y, z).applyMatrix4(T.root.matrixWorld);
function fit3d(anim = true, box) {
  if (!T.bbox) return;
  T.root.updateMatrixWorld();
  const b = box || (T.hl.length ? elemBox(T.hl.flatMap(h => h.els)) : T.bbox);
  const c = toWorld((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
  const r = Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2], 2) * 0.5;
  const d = r / Math.tan(THREE.MathUtils.degToRad(T.camera.fov / 2)) * 1.25;
  const to = c.clone().add(new THREE.Vector3(0.75, 0.62, 0.95).normalize().multiplyScalar(d));
  T.camera.near = Math.max(0.05, d / 500); T.camera.far = d * 20; T.camera.updateProjectionMatrix();
  T.scene.fog.near = d * 2; T.scene.fog.far = d * 8;
  if (!anim) { T.camera.position.copy(to); T.controls.target.copy(c); return; }
  const p0 = T.camera.position.clone(), t0c = T.controls.target.clone(), t0 = performance.now();
  (function step(now) { const t = Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - t, 3);
    T.camera.position.lerpVectors(p0, to, e); T.controls.target.lerpVectors(t0c, c, e); if (t < 1) requestAnimationFrame(step); })(t0);
}
function highlight3d(items, storey) {
  if (!T.inited || !T.H) { T.hl = []; return; }
  // section cut: like an architectural floor plan, cut the building 1.2 m above the asked storey's floor
  T.cutInfo = null;
  if (T.clip) {
    const z0 = storey != null ? T.levels[storey] : null;
    if (z0 != null) {
      const above = Object.values(T.levels).filter(z => z > z0 + 0.5).sort((a, b) => a - b)[0];
      const cut = z0 + Math.min(1.2, above != null ? (above - z0) * 0.5 : 1.2);
      T.clip.constant = cut; T.cutInfo = `section cut 1.2 m above “${storey}”`;
    } else T.clip.constant = 1e6;
  }
  if (T.hlMesh) { T.root.remove(T.hlMesh); T.hlMesh.geometry.dispose(); T.hlMesh = null; }
  if (T.hlEdges) { T.root.remove(T.hlEdges); T.hlEdges = null; }
  T.hl = items.filter(i => i.gid).map(it => ({ it, els: [it.gid, ...(it.parts || [])].flatMap(g => T.byGid.get(g) || []) })).filter(h => h.els.length);
  const L = $('#labels3d'); L.innerHTML = '';
  if (T.edges) { T.edges.material.color.set(T.hl.length ? 0x6f8fc7 : 0x0b1222); T.edges.material.opacity = T.hl.length ? .22 : .35; }
  if (!T.hl.length) { T.baseMat.opacity = 1; T.baseMat.depthWrite = true; T.hlMat = null; return; }
  T.baseMat.opacity = T.cutInfo ? 0.28 : 0.10; T.baseMat.depthWrite = false;
  const els = T.hl.flatMap(h => h.els);
  const allSpaces = els.every(e => e.cls === 'IfcSpace');
  const { geo, map } = subset(els, T.I); T.hlMap = map;
  T.hlMat = new THREE.MeshStandardMaterial({ color: 0xffb020, emissive: 0xff8a00, emissiveIntensity: .6, roughness: .5, flatShading: true, side: THREE.DoubleSide, transparent: allSpaces, opacity: allSpaces ? .6 : 1 });
  T.hlMesh = new THREE.Mesh(geo, T.hlMat); T.hlMesh.renderOrder = 2; T.root.add(T.hlMesh);
  T.hlEdges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0xfff1c9, transparent: true, opacity: .9 }));
  T.root.add(T.hlEdges);
  T.hl.forEach(h => { const b = elemBox(h.els); h.c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, b[5]]; h.box = b;
    if (T.hl.length <= 400) { const d = el('div', T.hl.length > 40 ? 'dot' : '', h.it.n); d.dataset.n = h.it.n; L.append(d); h.lab = d; } });
  fit3d(true);
}
function place3dLabels() {
  if (S.view !== 'model' || !T.hl.length) return;
  const r = $('#modelv').getBoundingClientRect(); T.root.updateMatrixWorld();
  T.hl.forEach(h => { if (!h.lab) return; const v = toWorld(...h.c).project(T.camera);
    h.lab.style.display = v.z > 1 ? 'none' : ''; h.lab.style.left = ((v.x + 1) / 2 * r.width) + 'px'; h.lab.style.top = ((1 - v.y) / 2 * r.height) + 'px'; });
}
function hot3d(n) {
  if (T.hotMesh) { T.root.remove(T.hotMesh); T.hotMesh.geometry.dispose(); T.hotMesh = null; }
  const h = n == null ? null : T.hl.find(h => h.it.n == n);
  if (!h) return;
  const { geo } = subset(h.els, T.I);
  T.hotMesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xff2d55, transparent: true, opacity: .9, depthTest: false }));
  T.hotMesh.renderOrder = 5; T.root.add(T.hotMesh);
}
function focus3d(it) { const h = T.hl.find(h => h.it.n === it.n); if (h) { fit3d(true, h.box); showPick(h.els[0]); } }
function pick3d(e) {
  const r = e.target.getBoundingClientRect();
  T.ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), T.camera);
  const targets = [T.hlMesh, T.base].filter(Boolean);
  const hit = T.ray.intersectObjects(targets, false)[0];
  if (!hit) { $('#pick').hidden = true; return; }
  const map = hit.object === T.hlMesh ? T.hlMap : T.baseMap, o = hit.faceIndex * 3;
  let lo = 0, hi = map.length - 1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (map[m][0] <= o) lo = m; else hi = m - 1; }
  showPick(map[lo][1]);
}
function showPick(e) {
  const p = $('#pick'); p.hidden = false;
  p.innerHTML = `<b>${esc(e.cls)}</b> ${esc(e.name || '')}<br><code>GlobalId ${esc(e.gid)}</code>${e.storey ? `<br><span class="muted">storey: ${esc(e.storey)}</span>` : ''}`;
}

// ============================================================ audit: run every dataset question on this drawing
$('#auditBtn').onclick = async () => {
  const f = S.file; if (!f) return;
  const L = $('#auditList'); L.hidden = false; L.innerHTML = '';
  let ok = 0, n = 0, eur = 0; const t0 = performance.now();
  for (const q of f.questions) {
    const r = await (await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: f.path, question: q.q }) })).json();
    if (S.file !== f) return;
    n++; ok += r.correct === true; eur += r.cost?.total_eur || 0;
    const d = el('span', r.correct === true ? 'ok' : r.correct === false ? 'bad' : 'na');
    d.title = `${q.q}\n→ ${fmtVal(r.value)} (truth ${fmtVal(r.truth)})`;
    d.onclick = () => { $('#q').value = q.q; S.last = r; show(r); };
    L.append(d);
    $('#auditSum').innerHTML = `<b>${ok}/${n}</b> correct · ${fmtEur(eur)} total · ${Math.round(performance.now() - t0)} ms`;
  }
};

// ============================================================ scoreboard
$('#sbBtn').onclick = async () => {
  const d = await (await fetch('/api/scoreboard')).json();
  const tot = d.reduce((a, x) => ({ g: a.g + x.graded, c: a.c + x.correct, e: a.e + x.eur, v: a.v + x.vlm_eur, n: a.n + x.total }), { g: 0, c: 0, e: 0, v: 0, n: 0 });
  const names = { swiss_dwellings: ['Swiss CAD floors', 'DXF + vector PDF · EN/DE/FR/IT'], ifc_models: ['IFC building models', 'IFC2x3/IFC4 · EN/ET/DA/DE'],
    cubicasa5k: ['Finnish raster plans', 'PNG scans · EN/FI'], opening_design: ['US drawing sets', 'PDF schedules'], ifc_bench: ['IFC-Bench v2', 'free-text BIM questions'] };
  let h = `<div class="sbtot"><div><label>auto-graded accuracy</label><b style="color:var(--ok)">${(100 * tot.c / Math.max(tot.g, 1)).toFixed(1)}%</b></div>
    <div><label>questions answered</label><b>${tot.n.toLocaleString('en')}</b></div>
    <div><label>total cost (PINPOINT)</label><b style="color:var(--ok)">${fmtEur(tot.e)}</b></div>
    <div><label>frontier VLM, same questions (est.)</label><b style="color:var(--ink2)">${fmtEur(tot.v)}</b></div></div>`;
  d.forEach(x => {
    const p = 100 * x.correct / Math.max(x.graded, 1), nm = names[x.source] || [x.source, ''];
    h += `<div class="sbrow"><div class="src"><b>${nm[0]}</b><small>${nm[1]}</small></div>
      <div><div class="bar"><i style="width:${p}%"></i></div><small class="muted">${Object.entries(x.by_type).map(([t, [a, b]]) => `${t} ${a}/${b}`).join(' · ')}</small></div>
      <div class="pct">${p.toFixed(1)}%</div><div class="k"><b>${x.correct}/${x.graded}</b>correct</div><div class="k"><b>${x.median_ms} ms</b>median (warm)<br>€${(x.eur / Math.max(x.total, 1)).toExponential(1)} / question</div></div>`;
  });
  h += `<p class="sbnote">Counts must match exactly; areas, lengths and volumes within 2% (Stoa's rule). Cost = measured CPU time × €0.04/vCPU-hour, plus LLM tokens when the template-only router is used (0 calls in these runs).
    The VLM estimate prices each sheet at ~1.6k image tokens per 1.15 MP at 200 dpi + prompt/answer tokens at $3/$15 per Mtok. Misses are kept visible: unmatched IFC questions refer to a model (FZK-Haus) whose IFC file is not in the preview set.</p>`;
  $('#sbBody').innerHTML = h; $('#sb').hidden = false;
};
$('#sbX').onclick = () => $('#sb').hidden = true;
$('#sb').onclick = e => { if (e.target.id === 'sb') $('#sb').hidden = true; };

// ============================================================ guided tour (one showcase per source)
const TOUR = [
  ['data/swiss_dwellings/site1000_bldg2082_floor9385.pdf', 'Wie viele WCs sind auf diesem Grundriss eingezeichnet?'],
  ['data/swiss_dwellings/site1000_bldg2082_floor9385.pdf', 'What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, terraces and other outdoor spaces?'],
  ['data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-04-4-korrus.pdf', "Mitu ust on näidatud korruse „4.korrus“ plaanil?", 'sheet'],
  ['data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-04-4-korrus.pdf', "How many doors are shown on the floor plan of '4.korrus'?", 'model'],
  ['data/ifc_bench/duplex_arc.ifc', 'How many bedrooms are there?'],
  ['data/opening_design/Sports_Complex/Sheets - Current Set/A-801 - Door and Finish Schedules & Wall Types.pdf', 'On sheet A-801 of the Xcel Sports Complex drawings, how many doors in the door schedule are door type B2 (double aluminium door with glazing)?'],
  ['data/cubicasa5k/colorful-11400.png', 'Kuinka monta ikkunaa pohjapiirustuksessa on?'],
];
S.touring = false;
async function tour() {
  if (S.touring) { S.touring = false; $('#tourBtn').textContent = '▶ Tour'; return; }
  S.touring = true; $('#tourBtn').textContent = '■ Stop tour';
  for (const [path, q, view] of TOUR) {
    if (!S.touring) break;
    const f = S.cat.find(x => x.path === path); if (!f) continue;
    selectFile(f); $('#q').value = '';
    for (const ch of q) { if (!S.touring) break; $('#q').value += ch; await new Promise(r => setTimeout(r, 14)); }
    await ask();
    if (view) setTimeout(() => setView(view), 900);
    await new Promise(r => setTimeout(r, 7000));
  }
  S.touring = false; $('#tourBtn').textContent = '▶ Tour';
}
$('#tourBtn').onclick = tour;

boot();
