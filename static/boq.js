// PINPOINT · instant bill of quantities. One click lists every measurable line of a drawing; each line lights up its
// evidence on the drawing (Swiss sheet / IFC plan) or in 3D. Export CSV / PDF. Numbers come only from /api/boq.
const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/static/wow.css'; document.head.append(css);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const NS = 'http://www.w3.org/2000/svg';
const B = { open: false, sel: null, hot: null, t: { s: 1, x: 0, y: 0 } };
const fmtQ = (v, u) => v == null ? '—' : typeof v !== 'number' ? esc(v) : u === 'm³' ? v.toLocaleString('en', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
  : (u === 'm²' || u === 'm') ? v.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : v.toLocaleString('en');

function dom() {
  if (B.root) return;
  const d = document.createElement('div'); d.className = 'bq'; d.hidden = true;
  d.innerHTML = `
  <header class="bqTop">
    <div class="bqT"><span class="wkK">INSTANT BILL OF QUANTITIES</span><b id="bqName">—</b><small id="bqSub"></small></div>
    <div class="bqKpi" id="bqKpi"></div>
    <div class="bqAct">
      <a class="bqBtn" id="bqCsv" download>⬇ CSV</a>
      <a class="bqBtn" id="bqPdf" download>⬇ PDF</a>
      <button class="wkX" id="bqX" title="Close (Esc)">✕</button>
    </div>
  </header>
  <div class="bqBody">
    <section class="bqDraw" id="bqDraw">
      <div class="bqPan" id="bqPan"><img id="bqImg" alt=""><div id="bqSvgHost"></div><svg id="bqOv" class="bqOv"></svg></div>
      <div class="bqMsg" id="bqMsg" hidden></div>
      <div class="bqSel" id="bqSel" hidden></div>
      <div class="bqTools"><button id="bqFit" title="Fit">⤢</button><button id="bq3d" class="hot">Show in 3D</button></div>
      <div class="bqCredit" id="bqCredit"></div>
    </section>
    <section class="bqList">
      <div class="bqFilter"><input id="bqQ" placeholder="Filter lines… (e.g. door, Zimmer, Betoon, m³)"><span id="bqN"></span></div>
      <div class="bqRows" id="bqRows"></div>
    </section>
  </div>
  <div class="wkLoad" id="bqLoad"><div class="wkRing"></div><b>Measuring every element…</b><small>doors · windows · fixtures · room areas · walls · IFC materials</small></div>`;
  document.body.append(d); B.root = d;
  const $ = s => d.querySelector(s); B.$ = $;
  $('#bqX').onclick = close;
  $('#bqFit').onclick = () => fit(selItems());
  $('#bq3d').onclick = to3d;
  $('#bqQ').oninput = () => renderRows();
  addEventListener('keydown', e => {
    if (!B.open || document.body.classList.contains('wkOpen')) return;
    if (e.key === 'Escape') { if (B.sel) select(null); else close(); }
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); stepSel(1); }
    if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); stepSel(-1); }
    if (e.key === '3') to3d();
  }, true);
  // pan / zoom
  const D = $('#bqDraw');
  D.addEventListener('wheel', e => { e.preventDefault(); const r = D.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * 0.0015)); }, { passive: false });
  let drag = null;
  D.addEventListener('pointerdown', e => { if (e.target.closest('button,a')) return; drag = [e.clientX, e.clientY, B.t.x, B.t.y]; D.setPointerCapture(e.pointerId); });
  D.addEventListener('pointermove', e => { if (!drag) return; B.t.x = drag[2] + e.clientX - drag[0]; B.t.y = drag[3] + e.clientY - drag[1]; apply(); });
  D.addEventListener('pointerup', () => drag = null);
}

export async function openBoq({ path, name }) {
  dom();
  B.root.hidden = false; B.open = true; document.body.classList.add('boqOpen');
  B.$('#bqLoad').hidden = false;
  B.$('#bqName').textContent = name || path.split('/').pop();
  B.path = path; B.name = name;
  B.$('#bqCsv').href = `/api/boq.csv?path=${encodeURIComponent(path)}`;
  B.$('#bqPdf').href = `/api/boq.pdf?path=${encodeURIComponent(path)}`;
  const t0 = performance.now();
  let b;
  try { b = await (await fetch(`/api/boq?path=${encodeURIComponent(path)}`)).json(); }
  catch (e) { b = { kind: 'none', lines: [], why: String(e) }; }
  B.b = b; B.sel = null;
  const ms = performance.now() - t0;
  B.$('#bqLoad').hidden = true;
  B.$('#bqCredit').innerHTML = b.credit ? `<b>Data</b>${b.credit.licence ? ` <i>${esc(b.credit.licence)}</i>` : ''} ${esc(b.credit.credit)}` : '';
  if (b.kind === 'none') {
    B.$('#bqSub').textContent = '';
    B.$('#bqKpi').innerHTML = '';
    B.$('#bqRows').innerHTML = `<div class="bqNone"><b>No bill of quantities for this drawing</b><p>${esc(b.why)}</p></div>`;
    B.$('#bqCsv').hidden = B.$('#bqPdf').hidden = true;
    showDrawing(null);
    return;
  }
  B.$('#bqCsv').hidden = B.$('#bqPdf').hidden = false;
  const nItems = b.lines.reduce((a, l) => a + l.items.length, 0);
  B.$('#bqSub').textContent = `${b.lines.length} lines · ${nItems.toLocaleString('en')} evidence links · measured in ${Math.round(ms)} ms from ${b.kind === 'swiss' ? 'the DXF layers' : 'the IFC model (' + (b.schema || '') + ')'} · 0 LLM calls`;
  B.$('#bqKpi').innerHTML = (b.kpi || []).map((k, i) => `<div style="animation-delay:${i * 70}ms"><b data-v="${typeof k.v === 'number' ? k.v : ''}">${typeof k.v === 'number' ? '0' : esc(k.v ?? '—')}</b><span>${esc(k.u)} ${esc(k.k)}</span></div>`).join('');
  B.$('#bqKpi').querySelectorAll('b[data-v]').forEach(n => { const v = parseFloat(n.dataset.v); if (!isNaN(v)) countUp(n, v, Number.isInteger(v) ? 0 : 2); });
  B.v = {};
  renderRows();
  const vpath = path;
  fetch(`/api/boq_verify?path=${encodeURIComponent(path)}`).then(r => r.json()).then(v => {
    if (B.path !== vpath || !B.open) return;
    B.v = v || {};
    const nl = Object.keys(B.v).length, nq = Object.values(B.v).reduce((a, x) => a + x.length, 0), bad = Object.values(B.v).flat().filter(x => !x.ok).length;
    if (nl) {
      const k = document.createElement('div'); k.className = 'gtK';
      k.innerHTML = `<b>${nl}</b><span>lines = dataset ground truth (${nq} questions${bad ? `, ${bad} off` : ''})</span>`;
      k.title = 'Each verified line has exactly the same evidence elements as a dataset question, and its quantity meets the challenge grading (counts exact, measures within 2%).';
      B.$('#bqKpi').append(k);
    }
    renderRows();
  }).catch(() => { });
  await showDrawing(b);
}
export function close() { B.open = false; B.root.hidden = true; document.body.classList.remove('boqOpen'); }

function countUp(n, to, dp) {
  const t0 = performance.now(), D = 900;
  (function f(now) { const t = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - t, 4); n.textContent = (to * e).toLocaleString('en', { minimumFractionDigits: dp, maximumFractionDigits: dp }); if (t < 1) requestAnimationFrame(f); })(t0);
}

// ------------------------------------------------------------------ table
function renderRows() {
  const q = B.$('#bqQ').value.trim().toLowerCase();
  const R = B.$('#bqRows'); R.innerHTML = '';
  let sec = null, n = 0, i = 0;
  B.b.lines.forEach(l => {
    const gt = B.v?.[l.id];
    if (q && !`${l.id} ${l.desc} ${l.method} ${l.source} ${l.unit} ${gt ? 'verified ground truth gt' : ''}`.toLowerCase().includes(q)) return;
    if (!sec || l.sec[0] !== sec) {
      sec = l.sec[0];
      const h = document.createElement('div'); h.className = 'bqSec';
      const all = B.b.lines.filter(x => x.sec[0] === sec);
      h.innerHTML = `<span>${esc(sec)}</span>${esc(l.sec[1])}<i>${all.length} lines</i>`;
      R.append(h);
    }
    n++;
    const c = l.check;
    const r = document.createElement('div');
    r.className = 'bqRow' + (B.sel === l.id ? ' on' : '') + (l.note === 'derived' ? ' der' : '') + (c && !c.ok ? ' warn' : '');
    r.dataset.id = l.id; r.style.animationDelay = Math.min(i++ * 12, 500) + 'ms';
    r.innerHTML = `<span class="id">${esc(l.id)}</span>
      <span class="d">${esc(l.desc)}${c ? (c.ok ? ` <em class="ok">✓ label ${c.printed}</em>` : ` <em class="bad">≠ label ${c.printed}</em>`) : ''}${l.note === 'derived' ? ' <em class="dv">derived</em>' : ''}${gt ? ` <em class="${gt.every(x => x.ok) ? 'gt' : 'bad'}" title="${esc(gt.map(x => `${x.ok ? '✓' : '✗'} ${x.q}\n   ground truth ${x.truth} · ours ${x.value} · Δ ${x.dev}%`).join('\n'))}">✓ ground truth ${esc(gt[0].truth)}${gt[0].type !== 'count' ? ` · Δ ${gt[0].dev}%` : ''}${gt.length > 1 ? ` · ${gt.length} Qs` : ''}</em>` : ''}
        <small>${esc(l.method)} · <b>${esc(l.source)}</b></small></span>
      <span class="q">${fmtQ(l.qty, l.unit)}<small>${esc(l.unit)}</small></span>
      <span class="ev" title="evidence items">${l.items.length}</span>`;
    r.onmouseenter = () => { B.hot = l.id; draw(); };
    r.onmouseleave = () => { B.hot = null; draw(); };
    r.onclick = () => select(B.sel === l.id ? null : l.id);
    R.append(r);
  });
  B.$('#bqN').textContent = q ? `${n} / ${B.b.lines.length}` : `${B.b.lines.length} lines`;
}
const line = id => B.b?.lines.find(l => l.id === id);
const selItems = () => (line(B.sel)?.items) || [];
function select(id) {
  B.sel = id;
  B.root.querySelectorAll('.bqRow').forEach(r => r.classList.toggle('on', r.dataset.id === id));
  B.root.querySelector(`.bqRow[data-id="${id}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  const l = line(id);
  const S = B.$('#bqSel');
  if (l) {
    S.hidden = false;
    const onPlan = B.b.kind === 'ifc' ? l.items.filter(i => B.guids?.has(i.gid)).length : l.items.length;
    S.innerHTML = `<span class="id">${esc(l.id)}</span><b>${fmtQ(l.qty, l.unit)} ${esc(l.unit)}</b><span>${esc(l.desc)}</span>`
      + (B.b.kind === 'ifc' ? `<small>${onPlan} of ${l.items.length} on this plan${onPlan < l.items.length ? ' · <u>Show in 3D</u> for all' : ''}</small>` : '');
    S.querySelector('u')?.addEventListener('click', to3d);
  } else S.hidden = true;
  draw();
  fit(l ? l.items : null);
}
function stepSel(d) {
  const ids = [...B.root.querySelectorAll('.bqRow')].map(r => r.dataset.id);
  if (!ids.length) return;
  const i = ids.indexOf(B.sel);
  select(ids[(i + d + ids.length) % ids.length]);
}

// ------------------------------------------------------------------ drawing
async function showDrawing(b) {
  const img = B.$('#bqImg'), host = B.$('#bqSvgHost'), ov = B.$('#bqOv'), msg = B.$('#bqMsg');
  img.hidden = true; host.innerHTML = ''; ov.innerHTML = ''; msg.hidden = true; B.guids = null; B.W = B.H = 0;
  B.$('#bq3d').hidden = !b || b.kind === 'none';
  if (!b || b.kind === 'none') { msg.hidden = false; msg.textContent = 'Quantities need vector geometry: open a Swiss DXF plan or an IFC model.'; return; }
  if (b.kind === 'swiss') {
    B.W = b.sheet.w; B.H = b.sheet.h;
    img.hidden = false; img.src = b.sheet.url; img.style.width = B.W + 'px'; img.style.height = B.H + 'px';
    ov.setAttribute('viewBox', `0 0 ${B.W} ${B.H}`); ov.style.width = B.W + 'px'; ov.style.height = B.H + 'px';
    await new Promise(r => { if (img.complete) r(); else { img.onload = r; img.onerror = r; } });
  } else if (b.plan) {
    const txt = await (await fetch(b.plan.url)).text();
    host.innerHTML = txt;
    const svg = host.querySelector('svg');
    const vb = (svg.getAttribute('viewBox') || '0 0 1000 1000').split(/[\s,]+/).map(Number);
    B.vb = vb; B.W = vb[2]; B.H = vb[3];
    svg.setAttribute('width', B.W); svg.setAttribute('height', B.H); svg.style.width = B.W + 'px'; svg.style.height = B.H + 'px';
    B.guids = new Map(); host.querySelectorAll('[data-guid]').forEach(g => B.guids.set(g.dataset.guid, g));
    msg.hidden = false; msg.className = 'bqMsg tag'; msg.textContent = `2D plan: ${b.plan.name || ''} · items on other storeys light up in 3D`;
  } else {
    msg.hidden = false; msg.className = 'bqMsg'; msg.innerHTML = 'This model has no rendered plan sheet in the dataset.<br><b>Click a line, then “Show in 3D”</b> to see its elements glow in the model.';
    return;
  }
  fit(null, false);
}
function apply() { B.$('#bqPan').style.transform = `translate(${B.t.x}px,${B.t.y}px) scale(${B.t.s})`; B.$('#bqOv').style.setProperty('--k', 1 / B.t.s); }
function zoomAt(px, py, f) { const s = Math.min(40, Math.max(0.05, B.t.s * f)); f = s / B.t.s; B.t.x = px - (px - B.t.x) * f; B.t.y = py - (py - B.t.y) * f; B.t.s = s; apply(); }
function boxOf(items) {
  let b = null;
  const grow = (x0, y0, x1, y1) => { b = b ? [Math.min(b[0], x0), Math.min(b[1], y0), Math.max(b[2], x1), Math.max(b[3], y1)] : [x0, y0, x1, y1]; };
  (items || []).forEach(it => {
    if (B.b.kind === 'swiss' && it.bbox) grow(...it.bbox);
    if (B.b.kind === 'ifc' && B.guids?.has(it.gid)) { const r = B.guids.get(it.gid).getBBox?.(); if (r) grow(r.x - B.vb[0], r.y - B.vb[1], r.x - B.vb[0] + r.width, r.y - B.vb[1] + r.height); }
  });
  return b;
}
function fit(items, anim = true) {
  if (!B.W) return;
  const D = B.$('#bqDraw').getBoundingClientRect();
  const bb = boxOf(items) || [0, 0, B.W, B.H];
  const pad = items && boxOf(items) ? 80 : 20;
  const w = Math.max(bb[2] - bb[0], 30), h = Math.max(bb[3] - bb[1], 30);
  const s = Math.min((D.width - 2 * pad) / w, (D.height - 2 * pad - 40) / h, items ? 8 : 99);
  const to = { s, x: D.width / 2 - (bb[0] + w / 2) * s, y: (D.height - 40) / 2 - (bb[1] + h / 2) * s };
  if (!anim) { B.t = to; apply(); return; }
  const from = { ...B.t }, t0 = performance.now();
  const id = (B.anim = (B.anim || 0) + 1);
  (function f(now) { if (id !== B.anim) return; const k = Math.min(1, (now - t0) / 650), e = 1 - Math.pow(1 - k, 3);
    B.t = { s: from.s + (to.s - from.s) * e, x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e }; apply(); if (k < 1) requestAnimationFrame(f); })(t0);
}
function draw() {
  const ov = B.$('#bqOv'); ov.innerHTML = '';
  B.root.querySelectorAll('.bqLit').forEach(n => n.classList.remove('bqLit', 'bqHot'));
  const L = [[line(B.sel), 'sel'], [B.hot !== B.sel ? line(B.hot) : null, 'hot']];
  L.forEach(([l, cls]) => {
    if (!l) return;
    if (B.b.kind === 'swiss') {
      const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'bq-' + cls); ov.append(g);
      const many = l.items.length > 60;
      l.items.forEach((it, i) => {
        let s;
        if (it.poly) { s = document.createElementNS(NS, 'path'); s.setAttribute('d', [it.poly, ...(it.holes || [])].map(r => 'M' + r.map(p => p.join(',')).join('L') + 'Z').join(''));
          s.setAttribute('fill-rule', 'evenodd'); }
        else if (it.bbox) { const [x0, y0, x1, y1] = it.bbox, p = 2; s = document.createElementNS(NS, 'rect');
          s.setAttribute('x', x0 - p); s.setAttribute('y', y0 - p); s.setAttribute('width', x1 - x0 + 2 * p); s.setAttribute('height', y1 - y0 + 2 * p); s.setAttribute('rx', 2); }
        if (!s) return;
        s.style.animationDelay = (cls === 'sel' ? Math.min(i * 25, 700) : 0) + 'ms';
        g.append(s);
        if (cls === 'sel' && !many && it.bbox) {
          const t = document.createElementNS(NS, 'g'); t.setAttribute('class', 'bqNum'); t.style.animationDelay = Math.min(i * 25, 700) + 'ms';
          const cx = it.poly ? (it.bbox[0] + it.bbox[2]) / 2 : it.bbox[2], cy = it.poly ? (it.bbox[1] + it.bbox[3]) / 2 : it.bbox[1];
          t.style.transform = `translate(${cx}px,${cy}px) scale(var(--k))`;
          t.innerHTML = `<circle r="9"/><text dy="3.5">${it.n}</text>`;
          g.append(t);
        }
      });
    } else if (B.guids) {
      l.items.forEach(it => { const n = B.guids.get(it.gid); if (n) n.classList.add('bqLit', cls === 'hot' ? 'bqHot' : 'bqSelEl'); });
    }
  });
}

// ------------------------------------------------------------------ 3D
async function to3d() {
  const l = line(B.sel);
  const m = await import('/static/walk.js');
  if (!l) { m.openWalk({ path: B.path, name: B.name }); return; }
  const answer = { q: `${l.id} · ${l.desc}`, value: l.qty, unit: l.unit === 'pcs' ? 'count' : l.unit, method: `${l.method} · ${l.source}`,
    items: (B.b.kind === 'swiss' ? l.dxf : l.items).map((it, i) => ({ ...it, n: i + 1 })) };
  m.openWalk({ path: B.path, name: B.name, q: answer.q, answer, override: true });
}

window.PPboq = { open: openBoq, close, B };
