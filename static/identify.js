// Component identification: click ANY element (2D sheet, IFC plan, 3D model, walkthrough) -> inspector card.
// Plus "this drawing contains…" parts list whose rows light the elements up. Data: /api/parts, /api/inspect.
import * as THREE from 'three';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const NS = 'http://www.w3.org/2000/svg';
const ID = { on: false, path: null, parts: null, loading: null, sel: null, lit: null, idx: null, mesh: null };
const ICON = { door: '🚪', window: '🪟', wall: '▮', fixture: '🚽', room: '▢', unit: '⌂', IfcDoor: '🚪', IfcWindow: '🪟', IfcWall: '▮', IfcWallStandardCase: '▮',
  IfcSlab: '▭', IfcSpace: '▢', IfcColumn: '▯', IfcBeam: '━', IfcStair: '⊟', IfcStairFlight: '⊟', IfcRailing: '⫼', IfcRoof: '⌂', text: '𝐓', pdf: '✎',
  toilet: '🚽', sink: '◒', shower: '🚿', bathtub: '🛁', sauna_stove: '♨' };
const KIND = { door: 'DOOR', window: 'WINDOW', wall: 'WALL', fixture: 'SANITARY', room: 'SPACE', unit: 'APARTMENT', text: 'PRINTED TEXT', pdf: 'LINEWORK' };
const kindLabel = k => KIND[k] || (k?.startsWith('Ifc') ? k.replace(/^Ifc/, '').replace(/StandardCase$/, '').replace(/([a-z])([A-Z])/g, '$1 $2').toUpperCase() : String(k || '').toUpperCase());
const kindClass = k => ({ IfcDoor: 'door', IfcWindow: 'window', IfcWall: 'wall', IfcWallStandardCase: 'wall', IfcSpace: 'room', IfcSanitaryTerminal: 'fixture', IfcFlowTerminal: 'fixture',
  toilet: 'fixture', sink: 'fixture', shower: 'fixture', bathtub: 'fixture' }[k] || k);

// ------------------------------------------------------------------ DOM
function dom() {
  if ($('#idCard')) return;
  const card = document.createElement('aside'); card.id = 'idCard'; card.className = 'idCard'; card.hidden = true; document.body.append(card);
  const parts = document.createElement('aside'); parts.id = 'idParts'; parts.className = 'idParts'; parts.hidden = true; document.body.append(parts);
  const tip = document.createElement('div'); tip.id = 'idTip'; tip.className = 'idTip'; tip.hidden = true; document.body.append(tip);
  const host = document.querySelector('.top') || document.body;
  const b = document.createElement('button'); b.id = 'idBtn'; b.className = 'wowBtn'; b.type = 'button';
  b.innerHTML = '⌖ Identify'; b.title = 'Click any element to see what it is, its size, properties and source (I)';
  b.onclick = () => toggle();
  const anchor = document.querySelector('#tourBtn'); if (anchor) anchor.before(b); else host.append(b);
}

// ------------------------------------------------------------------ data
const path = () => window.PP?.S?.file?.path || null;
async function loadParts() {
  const p = path(); if (!p) return null;
  if (ID.path === p && ID.parts) return ID.parts;
  if (ID.path === p && ID.loading) return ID.loading;
  ID.path = p; ID.parts = null; ID.idx = null;
  ID.loading = fetch(`/api/parts?path=${encodeURIComponent(p)}`).then(r => r.json()).then(d => {
    if (ID.path !== p) return null;
    ID.parts = d; ID.idx = new Map();
    (d.groups || []).forEach(g => g.types.forEach(t => t.ids.forEach(id => ID.idx.set(id, { g, t }))));
    return d;
  }).catch(e => ({ kind: 'none', why: String(e) }));
  return ID.loading;
}

// ------------------------------------------------------------------ 2D geometry helpers (sheet user units)
const SV = () => window.PP?.SV;
function scale() {   // parts geometry (PDF pt / image px) -> sheet view user units
  const s = ID.parts?.sheet, v = SV()?.vb; if (!s || !v) return 1;
  return v[2] / s.w;
}
function clientToUser(e) {
  const ov = $('#ov'); const m = ov?.getScreenCTM?.(); if (!m) return null;
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
  return [p.x, p.y];
}
function guidAt(e) {
  for (const n of document.elementsFromPoint(e.clientX, e.clientY)) { const g = n.closest?.('#svgHost [data-guid]'); if (g) return g; }
  return null;
}
function inPoly(x, y, p) { let c = false; for (let i = 0, j = p.length - 1; i < p.length; j = i++) { const [xi, yi] = p[i], [xj, yj] = p[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; }
function segDist(x, y, a, b) { const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1e-9; let t = ((x - a[0]) * dx + (y - a[1]) * dy) / L; t = Math.max(0, Math.min(1, t)); return Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy); }
function polyDist(x, y, p) { if (inPoly(x, y, p)) return 0; let d = 1e12; for (let i = 0, j = p.length - 1; i < p.length; j = i++) d = Math.min(d, segDist(x, y, p[j], p[i])); return d; }
function area(p) { let a = 0; for (let i = 0, j = p.length - 1; i < p.length; j = i++) a += (p[j][0] + p[i][0]) * (p[j][1] - p[i][1]); return Math.abs(a / 2); }
const PRIO = { fixture: 0, toilet: 0, sink: 0, shower: 0, bathtub: 0, sauna_stove: 0, door: 1, window: 2, wall: 3, room: 4 };
function hit2d(e) {
  const P = ID.parts; if (!P?.geo) return null;
  const u = clientToUser(e); if (!u) return null;
  const k = scale(), x = (u[0] - (SV().vb[0] || 0)) / k, y = (u[1] - (SV().vb[1] || 0)) / k;
  const tol = 7 / ((SV().k || 1) * (SV().s || 1)) / k;   // 7 screen px
  let best = null;
  for (const [id, g] of Object.entries(P.geo)) {
    const d = polyDist(x, y, g.poly);
    const lim = g.kind === 'room' ? 0 : tol;
    if (d > lim) continue;
    if (g.holes?.some(h => inPoly(x, y, h))) continue;
    const key = [PRIO[g.kind] ?? 5, d > 0 ? 1 : 0, area(g.poly)];
    if (!best || key[0] < best.key[0] || key[0] === best.key[0] && (key[1] < best.key[1] || key[1] === best.key[1] && key[2] < best.key[2])) best = { id, key, g };
  }
  return best ? best.id : null;
}

// ------------------------------------------------------------------ 2D lighting
function layer() {
  let g = $('#ovId');
  if (!g) { g = document.createElementNS(NS, 'g'); g.id = 'ovId'; $('#ov')?.append(g); }
  return g;
}
function pathD(g) {
  const k = scale(), v = SV()?.vb || [0, 0];
  const ring = r => 'M' + r.map(p => `${(p[0] * k + v[0]).toFixed(2)},${(p[1] * k + v[1]).toFixed(2)}`).join('L') + 'Z';
  return [g.poly, ...(g.holes || [])].map(ring).join(' ');
}
function draw2d() {
  const L = layer(); L.innerHTML = '';
  document.querySelectorAll('#svgHost .idLit,#svgHost .idSel').forEach(n => n.classList.remove('idLit', 'idSel'));
  const ids = ID.lit?.ids || [];
  const geo = ID.parts?.geo;
  ids.forEach(id => {
    if (geo?.[id]) { const p = document.createElementNS(NS, 'path'); p.setAttribute('d', pathD(geo[id])); p.setAttribute('fill-rule', 'evenodd'); p.setAttribute('class', `idL ${geo[id].kind}`); L.append(p); }
    else document.querySelectorAll(`#svgHost [data-guid="${CSS.escape(id)}"]`).forEach(n => n.classList.add('idLit'));
  });
  const s = ID.sel;
  if (s) {
    const g = s.geo || (geo && geo[s.id]);
    if (g?.poly) { const p = document.createElementNS(NS, 'path'); p.setAttribute('d', pathD(g)); p.setAttribute('fill-rule', 'evenodd'); p.setAttribute('class', 'idS'); L.append(p); }
    else document.querySelectorAll(`#svgHost [data-guid="${CSS.escape(s.id)}"]`).forEach(n => n.classList.add('idSel'));
  }
}
function hover2d(id) {
  let h = $('#ovIdHover');
  if (!h) { h = document.createElementNS(NS, 'path'); h.id = 'ovIdHover'; h.setAttribute('class', 'idH'); h.setAttribute('fill-rule', 'evenodd'); }
  const g = id && ID.parts?.geo?.[id];
  if (!g) { h.remove(); return; }
  h.setAttribute('d', pathD(g)); layer().append(h);
}

// ------------------------------------------------------------------ 3D lighting (main model view)
function drop3d() {
  const T = window.PP?.T; const m = ID.mesh; if (!m || !T) return;
  T.root.remove(m); m.geometry.deleteAttribute('position'); m.geometry.dispose(); ID.mesh = null;
}
function light3d(gids, color = 0x38d6ff, op = 0.6) {
  drop3d();
  const T = window.PP?.T; if (!T?.H || !T.byGid || !gids?.length) return;
  const els = gids.flatMap(g => T.byGid.get(g) || []); if (!els.length) return;
  let n = 0; els.forEach(e => n += e.ni);
  const idx = new Uint32Array(n); let o = 0;
  els.forEach(e => { idx.set(T.I.subarray(e.i0, e.i0 + e.ni), o); o += e.ni; });
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', T.pos); geo.setIndex(new THREE.BufferAttribute(idx, 1));
  ID.mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: op, depthTest: false }));
  ID.mesh.renderOrder = 6; T.root.add(ID.mesh);
}
function sync3d() {
  if (ID.parts?.kind !== 'ifc') return drop3d();
  const ids = ID.sel ? [ID.sel.id] : ID.lit?.ids;
  light3d(ids, ID.sel ? 0xff2d55 : 0x38d6ff, ID.sel ? 0.85 : 0.55);
}

// ------------------------------------------------------------------ parts drawer
function renderParts() {
  const el = $('#idParts'), P = ID.parts;
  if (!P) { el.innerHTML = `<div class="idPH"><span class="idK">THIS DRAWING CONTAINS</span><div class="idLoad"><i></i> reading the drawing…</div></div>`; return; }
  const cr = P.credit ? `<div class="idCr"><b>Data:</b> ${esc(P.credit.credit)}${P.credit.licence ? ` · <i>${esc(P.credit.licence)}</i>` : ''}</div>` : '';
  if (P.kind === 'none' || !P.groups?.length) {
    el.innerHTML = `<div class="idPH"><span class="idK">THIS DRAWING CONTAINS</span><button class="idX" data-x>✕</button></div>
      <p class="idWhy">${esc(P.why || 'No element objects found.')}</p><p class="idHint">⌖ Click anything on the sheet to identify printed tags and text.</p>${cr}`;
    el.querySelector('[data-x]').onclick = () => toggle(false);
    return;
  }
  const src = { swiss: 'DXF entities', ifc: `IFC ${P.schema || ''} objects`, raster: 'detected symbols' }[P.kind] || '';
  let h = `<div class="idPH"><span class="idK">THIS DRAWING CONTAINS</span><button class="idX" data-x title="Close (I)">✕</button></div>
    <div class="idSum">${P.summary.slice(0, 4).map(esc).join(' · ')}${P.summary.length > 4 ? ' …' : ''}</div>
    <div class="idSrcL">${esc(P.file || '')} · ${esc(src)}</div><div class="idGroups">`;
  P.groups.forEach((g, gi) => {
    const open = ID.openG?.has(g.key) ?? gi < 3;
    h += `<div class="idG${open ? ' open' : ''}" data-g="${gi}">
      <button class="idGH" data-gh="${gi}"><span class="ic k-${kindClass(g.key)}">${ICON[g.key] || '◆'}</span><b>${g.count.toLocaleString('en')}</b><span class="nm">${esc(g.term)}</span>
        <small>${g.types.length > 1 ? g.types.length + ' types' : esc(g.layer)}</small><i class="cv">▸</i></button>
      ${g.warn ? `<div class="idWarn">⚠ ${esc(g.warn)}</div>` : ''}
      <div class="idTs">${g.types.map((t, ti) => `<button class="idT" data-t="${gi}:${ti}"><span class="c">${t.count}×</span><span class="tn">${esc(t.name)}</span></button>`).join('')}</div></div>`;
  });
  h += `</div><p class="idHint">Click a row to light it up · click any element on the drawing${P.kind === 'ifc' || P.kind === 'swiss' ? ' or in 3D' : ''} to inspect it</p>${cr}`;
  el.innerHTML = h;
  el.querySelector('[data-x]').onclick = () => toggle(false);
  el.querySelectorAll('[data-gh]').forEach(b => b.onclick = () => {
    const g = P.groups[+b.dataset.gh]; const box = b.parentElement; box.classList.toggle('open');
    ID.openG = ID.openG || new Set(P.groups.slice(0, 3).map(x => x.key));
    box.classList.contains('open') ? ID.openG.add(g.key) : ID.openG.delete(g.key);
    lightUp({ key: 'g:' + g.key, ids: g.types.flatMap(t => t.ids), label: `${g.count} ${g.term.toLowerCase()}` });
  });
  el.querySelectorAll('[data-t]').forEach(b => b.onclick = () => {
    const [gi, ti] = b.dataset.t.split(':').map(Number); const g = P.groups[gi], t = g.types[ti];
    lightUp({ key: `t:${gi}:${ti}`, ids: t.ids, label: `${t.count}× ${t.name}` });
  });
  markActive();
}
function markActive() {
  document.querySelectorAll('#idParts .idT, #idParts .idGH').forEach(b => b.classList.remove('on'));
  const k = ID.lit?.key; if (!k) return;
  const sel = k.startsWith('t:') ? `#idParts [data-t="${k.slice(2)}"]` : null;
  if (sel) $(sel)?.classList.add('on');
  else { const gi = ID.parts?.groups?.findIndex(g => 'g:' + g.key === k); if (gi >= 0) $(`#idParts [data-gh="${gi}"]`)?.classList.add('on'); }
}
function lightUp(L) {
  ID.lit = ID.lit?.key === L.key ? null : L;
  ID.sel = null; $('#idCard').hidden = true;
  markActive(); draw2d(); sync3d();
  if (ID.lit) fitIds(ID.lit.ids);
}
function fitIds(ids) {
  const PP = window.PP; if (!PP?.SV || PP.S.mode === 'model') return;
  const geo = ID.parts?.geo; const k = scale(), v = SV().vb;
  let b = [1e12, 1e12, -1e12, -1e12];
  ids.forEach(id => {
    const g = geo?.[id];
    if (g) g.poly.forEach(p => { b = [Math.min(b[0], p[0] * k + v[0]), Math.min(b[1], p[1] * k + v[1]), Math.max(b[2], p[0] * k + v[0]), Math.max(b[3], p[1] * k + v[1])]; });
    else document.querySelectorAll(`#svgHost [data-guid="${CSS.escape(id)}"]`).forEach(n => { try { const q = n.getBBox(); b = [Math.min(b[0], q.x), Math.min(b[1], q.y), Math.max(b[2], q.x + q.width), Math.max(b[3], q.y + q.height)]; } catch (e) { } });
  });
  if (b[2] > b[0] && PP.fitBox) PP.fitBox(b, 80);
}

// ------------------------------------------------------------------ inspector card
async function inspect(q, from) {
  const p = q.path || path(); if (!p) return;
  const card = $('#idCard'); dom();
  card.hidden = false; card.classList.add('loading'); card.classList.toggle('over', !!from?.walk);
  if (!card.innerHTML) card.innerHTML = `<div class="idLoad"><i></i> identifying…</div>`;
  const qs = new URLSearchParams({ path: p }); for (const k of ['id', 'x', 'y', 'mx', 'my', 'hint']) if (q[k] != null && q[k] !== '') qs.set(k, q[k]);
  const c = await (await fetch('/api/inspect?' + qs)).json();
  card.classList.remove('loading');
  if (c.none) { card.innerHTML = `<div class="idCH"><span class="idKind">NOTHING HERE</span><button class="idX" data-x>✕</button></div><p class="idWhy">${esc(c.why)}</p>`; card.querySelector('[data-x]').onclick = closeCard; return; }
  ID.sel = { id: c.id, geo: c.geo, dxf: c.dxf, kind: c.kind };
  if (!from?.walk) { draw2d(); sync3d(); }
  renderCard(c, from);
  window.dispatchEvent(new CustomEvent('pp:identified', { detail: { ...c, from } }));
}
function renderCard(c, from) {
  const card = $('#idCard');
  const t = ID.idx?.get(c.id);
  const kc = kindClass(c.kind);
  const big = (c.dims || []).slice(0, 4), rest = (c.dims || []).slice(4);
  const isNA = v => /^not in /.test(v);
  card.innerHTML = `
    <div class="idCH"><span class="idKind k-${kc}"><i>${ICON[c.kind] || '◆'}</i>${esc(kindLabel(c.kind))}</span><span class="idId" title="element id">${esc(c.id)}</span><button class="idX" data-x title="Close (Esc)">✕</button></div>
    <h3 class="idTitle">${esc(c.title)}</h3>
    <div class="idType">${esc(c.type || '')}${t ? ` <span class="idOf">· 1 of ${t.t.count} of this type, ${t.g.count} ${esc(t.g.term.toLowerCase())} in total</span>` : ''}</div>
    ${big.length ? `<div class="idDims">${big.map(d => `<div class="d${isNA(d.v) ? ' na' : ''}" title="${esc(d.how || '')}"><label>${esc(d.k)}</label><b>${esc(d.v)}</b>${d.how ? `<small>${esc(d.how)}</small>` : ''}</div>`).join('')}</div>` : ''}
    ${rest.length || c.props?.length ? `<div class="idSec">Properties</div><dl class="idProps">${[...rest, ...(c.props || [])].map(p => `<dt>${esc(p.k)}</dt><dd>${esc(p.v)}${p.how ? `<small>${esc(p.how)}</small>` : ''}</dd>`).join('')}</dl>` : ''}
    ${(c.notes || []).map(n => `<div class="idNote${/⚠/.test(n) ? ' warn' : ''}">${esc(n)}</div>`).join('')}
    <div class="idSec">Source <span>exact citation</span></div>
    <div class="idCite">${(c.source || []).map(s => `<div><span>${esc(s.k)}</span><code>${esc(s.v)}</code></div>`).join('')}</div>
    <div class="idAct">${t && t.t.count > 1 ? `<button data-all>Light up all ${t.t.count} × ${esc(t.t.name.length > 34 ? t.t.name.slice(0, 32) + '…' : t.t.name)}</button>` : ''}<button data-copy title="Copy the citation">⧉ Copy citation</button></div>
    ${c.credit ? `<div class="idCr"><b>Data:</b> ${esc(c.credit.credit)}${c.credit.licence ? ` · <i>${esc(c.credit.licence)}</i>` : ''}</div>` : ''}`;
  card.querySelector('[data-x]').onclick = closeCard;
  const all = card.querySelector('[data-all]');
  if (all) all.onclick = () => { const gi = ID.parts.groups.indexOf(t.g), ti = t.g.types.indexOf(t.t); if (!ID.on) toggle(true); ID.lit = null; lightUp({ key: `t:${gi}:${ti}`, ids: t.t.ids, label: t.t.name }); };
  card.querySelector('[data-copy]').onclick = e => {
    const txt = `${c.title} (${c.type})\n` + (c.dims || []).map(d => `${d.k}: ${d.v}`).join('\n') + '\n' + (c.source || []).map(s => `${s.k}: ${s.v}`).join('\n');
    navigator.clipboard?.writeText(txt); e.target.textContent = '✓ copied'; setTimeout(() => e.target.textContent = '⧉ Copy citation', 1400);
  };
}
function closeCard() {
  $('#idCard').hidden = true; ID.sel = null; draw2d(); sync3d();
  window.dispatchEvent(new CustomEvent('pp:identified', { detail: null }));
}

// ------------------------------------------------------------------ mode
async function toggle(on = !ID.on) {
  dom();
  ID.on = on; document.body.classList.toggle('idOn', on);
  $('#idBtn')?.classList.toggle('on', on);
  if (!on) { $('#idParts').hidden = true; ID.lit = null; ID.sel = null; $('#idCard').hidden = true; draw2d(); drop3d(); hover2d(null); $('#idTip').hidden = true; return; }
  const sp = $('#splash'); if (sp) sp.hidden = true;
  $('#idParts').hidden = false; renderParts();
  await loadParts(); if (ID.on) renderParts();
}
function onFileChange() {
  const p = path(); if (!p || p === ID.path) return;
  ID.lit = null; ID.sel = null; ID.parts = null; ID.path = null; drop3d();
  $('#idCard') && ($('#idCard').hidden = true);
  if (ID.on) { renderParts(); loadParts().then(() => ID.on && renderParts()); }
  draw2d();
}

function mount() {
  dom();
  setInterval(onFileChange, 700);
  // 2D clicks (pan-aware: a click is a pointer-up within 4 px of its pointer-down)
  const sv = $('#sheetv'); let down = null;
  sv.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; }, true);
  sv.addEventListener('pointerup', async e => {
    if (!ID.on || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    if (e.target.closest('.lb,.minimap,button')) return;
    await loadParts();
    const g = SV()?.inline ? guidAt(e) : null;
    if (g) return inspect({ id: g.dataset.guid });
    const id = hit2d(e);
    if (id) return inspect({ id });
    const u = clientToUser(e); if (!u) return;
    const k = scale(), v = SV().vb;
    inspect({ x: ((u[0] - v[0]) / k).toFixed(2), y: ((u[1] - v[1]) / k).toFixed(2) });
  }, true);
  sv.addEventListener('pointermove', e => {
    if (!ID.on || e.buttons) return;
    const tip = $('#idTip');
    let id = ID.parts?.geo ? hit2d(e) : null, label = null;
    const g = !id && SV()?.inline ? guidAt(e) : null;
    if (id) { const t = ID.idx?.get(id); label = t ? `${t.g.term.replace(/s$/, '')} · ${t.t.name}` : id; }
    else if (g) { const t = ID.idx?.get(g.dataset.guid); label = t ? `${t.g.term.replace(/s$/, '')} · ${t.t.name}` : 'IFC element'; }
    hover2d(id);
    document.querySelectorAll('#svgHost .idHov').forEach(n => n.classList.remove('idHov')); if (g) g.classList.add('idHov');
    if (label) { tip.hidden = false; tip.textContent = label; tip.style.left = e.clientX + 14 + 'px'; tip.style.top = e.clientY + 16 + 'px'; } else tip.hidden = true;
  });
  sv.addEventListener('pointerleave', () => { hover2d(null); $('#idTip').hidden = true; });
  // 3D model view: app.js dispatches pp:pick with the picked element's GlobalId
  addEventListener('pp:pick', e => { if (ID.on && e.detail?.gid) { loadParts(); inspect({ id: e.detail.gid }); } });
  // walkthrough: walk.js dispatches pp:walkpick (Swiss: DXF metres + kind hint; IFC: GlobalId)
  addEventListener('pp:walkpick', e => { const d = e.detail; if (!d) return; loadParts(); inspect({ path: d.path, id: d.gid, mx: d.mx?.toFixed(3), my: d.my?.toFixed(3), hint: d.hint }, { walk: true }); });
  addEventListener('keydown', e => {
    if (e.target.closest?.('input,textarea') || e.metaKey || e.ctrlKey) return;
    if (document.body.classList.contains('wkOpen') || document.body.classList.contains('boqOpen')) { if (e.key === 'Escape' && !$('#idCard').hidden && $('#idCard').classList.contains('over')) closeCard(); return; }
    if (e.key === 'i') toggle();
    if (e.key === 'Escape' && !$('#idCard').hidden) closeCard();
  });
  // keep 2D highlights glued to the sheet when the view changes
  new MutationObserver(() => { if (ID.lit || ID.sel) draw2d(); }).observe($('#ov'), { attributes: true, attributeFilter: ['viewBox'] });
  const P = new URLSearchParams(location.search);
  if (P.get('identify')) setTimeout(function go() {
    if (!window.PP?.S?.file || (window.PP.S.has?.sheet && !SV()?.url)) return setTimeout(go, 300);
    toggle(true).then(() => {
      const id = P.get('iid'); if (id) inspect({ id });
      const lt = P.get('ilit'); if (lt && ID.parts?.groups) { const [gi, ti] = lt.split(':').map(Number); const t = ID.parts.groups[gi]?.types[ti]; if (t) lightUp({ key: `t:${gi}:${ti}`, ids: t.ids, label: t.name }); }
    });
  }, 900);
}
if (document.readyState === 'loading') addEventListener('DOMContentLoaded', mount); else mount();
export { toggle, inspect };
