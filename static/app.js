import * as THREE from 'three';
import { OrbitControls } from '/static/vendor/OrbitControls.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const frame = () => new Promise(r => requestAnimationFrame(r));
const NS = 'http://www.w3.org/2000/svg';
const SRC_NAMES = { swiss_dwellings: 'Swiss CAD', ifc_models: 'IFC models', ifc_bench: 'IFC bench', cubicasa5k: 'Finnish scans', opening_design: 'US sheets' };
const SRC_TAG = { swiss_dwellings: 'DXF+PDF', ifc_models: 'IFC', ifc_bench: 'IFC', cubicasa5k: 'scan', opening_design: 'PDF' };

const S = { cat: [], src: 'swiss_dwellings', file: null, total: 0, n: 0, last: null, mode: 'sheet', blue: true, sel: null, items: [], run: 0,
  has: { sheet: false, model: false } };

const fmtEur = v => {
  if (!v) return '€0';
  if (v >= 0.01) return '€' + v.toFixed(3);
  const d = Math.min(10, Math.max(2, 1 - Math.floor(Math.log10(v))));
  return '€' + v.toFixed(d);
};
const fmtVal = v => typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en') : v.toFixed(2)) : (v ?? '—');

// ============================================================ catalog / library drawer
async function boot() {
  S.cat = await (await fetch('/api/catalog')).json();
  const P = new URLSearchParams(location.search);
  const first = S.cat.find(f => f.path === P.get('path')) || S.cat.find(f => f.path.includes('site1000_bldg2082_floor9385')) || S.cat[0];
  selectFile(first);
  if (P.get('mode')) S.userMode = P.get('mode');
  if (P.get('q')) { $('#q').value = P.get('q'); await ask(); if (P.get('sel')) setTimeout(() => select(+P.get('sel')), 2600); }
  if (P.get('tour')) tour();
  else if (!P.get('q')) splash();
}
async function splash() {
  $('#splash').hidden = false;
  const close = () => $('#splash').hidden = true;
  $('#spTour').onclick = () => { close(); tour(); };
  $('#spTry').onclick = () => { close(); $('#q').focus(); };
  $('#splash').onclick = e => { if (e.target.id === 'splash') close(); };
  try {
    const d = await (await fetch('/api/scoreboard')).json();
    const g = d.reduce((a, x) => a + x.graded, 0), c = d.reduce((a, x) => a + x.correct, 0), n = d.reduce((a, x) => a + x.total, 0);
    const e = d.reduce((a, x) => a + x.eur, 0), v = d.reduce((a, x) => a + x.vlm_eur, 0);
    const ms = d.filter(x => x.total).map(x => x.median_ms).sort((a, b) => a - b);
    countUp($('#spAcc'), 100 * c / Math.max(g, 1), x => x.toFixed(1) + '%');
    countUp($('#spN'), g, x => Math.round(x).toLocaleString('en'));
    $('#spMs').textContent = ms.length ? `${ms[ms.length >> 1] < 1 ? '<1' : Math.round(ms[ms.length >> 1])} ms` : '–';
    countUp($('#spX'), e ? v / e : 0, x => x >= 1e6 ? (x / 1e6).toFixed(1) + 'M×' : Math.round(x).toLocaleString('en') + '×');
  } catch (e) { }
}
function countUp(node, to, fmt, D = 1400) {
  const t0 = performance.now();
  (function step(now) { const t = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - t, 4); node.textContent = fmt(to * e); if (t < 1) requestAnimationFrame(step); })(t0);
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
  S.cat.filter(x => x.source === S.src && (!f || x.path.toLowerCase().includes(f))).slice(0, 500).forEach(x => {
    const b = el('button', S.file === x ? 'on' : '', `<span title="${esc(x.path)}">${esc(x.name)}</span><i>${x.n} q</i>`);
    b.onclick = () => { selectFile(x); openLib(false); };
    box.append(b);
  });
}
function openLib(on) {
  $('#lib').hidden = !on;
  if (on) { S.src = S.file?.source || S.src; renderSources(); setTimeout(() => $('#filter').focus(), 50); }
}
$('#filter').oninput = renderFiles;
$('#docBtn').onclick = () => openLib($('#lib').hidden);
$('#libX').onclick = () => openLib(false);
$('#lib').onclick = e => { if (e.target.id === 'lib') openLib(false); };

const ifcFor = p => p.endsWith('.ifc') ? p : p.replace(/_plan-.*$/, '').replace(/\.[^.]+$/, '') + '.ifc';

function selectFile(f) {
  S.file = f; S.src = f.source;
  $('#docName').textContent = f.name; $('#docName').title = f.path;
  $('#srcTag').textContent = SRC_TAG[f.source] || f.source;
  // suggestions
  const box = $('#chips'); box.innerHTML = '';
  const seen = new Set();
  const qs = f.questions.filter(q => !seen.has(q.q) && seen.add(q.q));
  $('#suggN').textContent = `· ${qs.length}`;
  qs.slice(0, 80).forEach(q => {
    const b = el('button', '', `<i>${esc(q.type)}</i><span>${esc(q.q)}</span>`);
    b.onmousedown = e => { e.preventDefault(); $('#q').value = q.q; $('#sugg').hidden = true; $('#q').blur(); ask(); };
    box.append(b);
  });
  $('#q').value = qs[0]?.q || '';
  clearResult();
  $('#auditList').hidden = true; $('#auditSum').textContent = '';
  // show the drawing straight away
  const isIfc = f.path.endsWith('.ifc');
  S.has = { sheet: !isIfc, model: isIfc || f.source === 'ifc_models' };
  if (f.plan) loadSheet(f.plan.url, 0, 0, true);
  else if (!isIfc) loadSheet(`/api/sheet?path=${encodeURIComponent(f.path)}`);
  else { SV.url = null; showSheet(false); S.has.sheet = false; }
  if (S.has.model) loadModel(ifcFor(f.path));
  setMode(S.has.sheet && S.has.model ? (S.userMode || 'split') : S.has.model ? 'model' : 'sheet');
  updateModeButtons();
}

function clearResult() {
  S.run++; S.items = []; S.sel = null;
  $('#answer').hidden = true;
  $('#steps').innerHTML = '<li class="muted">Every step of the derivation appears here.</li>';
  $('#ev').innerHTML = ''; $('#evN').textContent = '';
  drawOverlay([]); highlight3d([]);
}

// ============================================================ ask
$('#askForm').onsubmit = e => { e.preventDefault(); $('#sugg').hidden = true; $('#q').blur(); ask(); };
$('#q').onfocus = () => { $('#sugg').hidden = !$('#chips').children.length; };
$('#q').onblur = () => setTimeout(() => $('#sugg').hidden = true, 120);
$('#q').oninput = () => {
  const t = $('#q').value.toLowerCase();
  [...$('#chips').children].forEach(b => b.style.display = !t || b.textContent.toLowerCase().includes(t) ? '' : 'none');
};

async function ask() {
  $('#splash').hidden = true;
  const q = $('#q').value.trim(); if (!q || !S.file) return;
  const go = $('#go'); go.classList.add('busy');
  const t0 = performance.now();
  const r = await (await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: S.file.path, question: q }) })).json();
  go.classList.remove('busy');
  r.rtt = performance.now() - t0; r.q = q;
  S.last = r;
  await show(r);
}

async function show(r) {
  const run = ++S.run;
  S.sel = null; S.items = r.items || []; S.revealed = false;
  const isText = r.unit === 'text';
  const A = $('#answer');
  A.hidden = false; A.style.animation = 'none'; A.offsetHeight; A.style.animation = '';
  A.classList.toggle('text', isText);
  A.classList.toggle('noval', r.value == null);
  $('#aQ').textContent = r.q || '';
  $('#aVal').textContent = r.value == null ? 'no answer' : isText ? r.value : '0';
  $('#aUnit').textContent = isText ? '' : r.unit && r.unit !== 'count' ? r.unit : (r.unit === 'count' ? 'found' : '');
  $('#aMethod').textContent = r.method || '';
  const bd = $('#aBadges'); bd.innerHTML = '';
  $('#stepper').hidden = S.items.length < 1;
  updateStepper();
  // receipt
  const st = $('#steps'); st.innerHTML = '';
  (r.steps || []).forEach((s, i) => { const li = el('li', '', esc(s)); li.style.animationDelay = (i * 70) + 'ms'; st.append(li); });
  $('#rSub').textContent = r.router === 'rules' || !r.router ? 'rule router · 0 LLM calls' : r.router;
  const ev = $('#ev'); ev.innerHTML = '';
  $('#evN').textContent = S.items.length || '';
  S.items.forEach((it, i) => {
    const warn = it.check && !it.check.ok;
    const sub = it.gid ? `${it.cls || ''} · ${it.gid}` : (it.kind || '');
    let v = it.value != null ? `${fmtVal(it.value)}${r.unit && r.unit !== 'count' && r.unit !== 'text' ? ' ' + r.unit : ''}` : '';
    if (it.check) v += it.check.what === 'low confidence' ? `<small>low confidence</small>` : `<small>${warn ? '≠' : '='} ${it.check.what ? 'Qto' : 'label'} ${it.check.printed}</small>`;
    const row = el('div', 'e' + (warn ? ' warn' : ''), `<span class="n">${it.n}</span><span class="l">${esc(it.label || it.kind)}<small>${esc(sub)}</small></span><span class="v">${v}</span>`);
    row.dataset.n = it.n;
    row.style.animationDelay = Math.min(i * 22, 600) + 'ms';
    row.onmouseenter = () => hot(it.n, true); row.onmouseleave = () => hot(it.n, false);
    row.onclick = () => select(it.n);
    ev.append(row);
  });
  if (S.items.length > 1 && r.unit && r.unit !== 'count' && r.unit !== 'text' && r.value != null) ev.append(el('div', 'sum', `<span>Σ ${S.items.length} items</span><b>${fmtVal(r.value)} ${esc(r.unit)}</b>`));
  // cost meter
  const c = r.cost || {};
  S.total += c.total_eur || 0; S.n++;
  $('#mLast').textContent = fmtEur(c.total_eur);
  $('#mLat').textContent = `${Math.round((c.seconds || 0) * 1000)} ms`;
  $('#mLlm').textContent = c.llm_calls || 0;
  $('#mVlm').textContent = fmtEur(c.vlm_baseline_eur);
  $('#mSave').textContent = c.total_eur ? `${Math.round(c.vlm_baseline_eur / c.total_eur).toLocaleString('en')}×` : '∞';
  const m = $('#meter'); m.classList.remove('flash'); m.offsetWidth; m.classList.add('flash');

  // ---- views
  const v = r.view || {};
  if (v.kind === 'sheet') {
    S.has = { sheet: true, model: false };
    await loadSheet(v.url, v.w, v.h);
    setMode('sheet');
  } else if (v.kind === 'model') {
    S.has = { sheet: !!v.sheet, model: true };
    const jobs = [loadModel(r.model)];
    if (v.sheet) jobs.push(loadSheet(v.sheet.url, v.sheet.w, v.sheet.h, v.sheet.inline));
    else { SV.url = null; showSheet(false); }
    setMode(v.sheet ? (S.userMode || 'split') : 'model');
    await Promise.all(jobs);
  }
  updateModeButtons();
  if (run !== S.run) return;
  highlight3d(S.items, r.storey);
  await frame();
  if (S.mode !== 'model') { drawOverlay(S.items); if (SV.inline && !SV.items.length) await waitPlan(run); }
  if (run !== S.run) return;
  addBadges(r);
  const fits = [];
  if (S.mode !== 'model' && S.has.sheet) fits.push(fitEvidence());
  if (S.mode !== 'sheet' && S.has.model) fits.push(fit3d(true));
  await Promise.all(fits);
  if (run !== S.run) return;
  await reveal(r, run);
}

function addBadges(r) {
  const bd = $('#aBadges'); bd.innerHTML = '';
  const isText = r.unit === 'text';
  if ('truth' in r) {
    if (r.correct === true) bd.append(el('span', 'badge ok', `✓ ground truth ${esc(fmtVal(r.truth))}`));
    else if (r.correct === false) bd.append(el('span', 'badge bad', `✗ ground truth ${esc(fmtVal(r.truth))}`));
    else if (isText) { const b = el('span', 'badge', 'reference answer ▾'); b.title = String(r.truth); b.style.cursor = 'help'; bd.append(b); }
  }
  const cf = r.receipt?.confidence;
  if (cf) { const b = el('span', 'badge ' + ({ green: 'ok', amber: 'warn', red: 'bad' }[cf.colour] || ''), `● confidence ${esc(cf.level)}`); b.title = (cf.why || []).join('\n'); bd.append(b); }
  const checks = S.items.filter(i => i.check);
  const bad = checks.filter(i => !i.check.ok).length;
  if (checks.length) bd.append(el('span', 'badge ' + (bad ? 'warn' : 'ok'), bad ? `⚠ ${bad}/${checks.length} cross-checks disagree` : `✓ ${checks.length}/${checks.length} cross-checks agree`));
  bd.append(el('span', 'badge cy', `${S.items.length} cited · ${r.router === 'rules' || !r.router ? '0 LLM' : esc(r.router)}`));
}

// ---- the reveal: a scan line sweeps the evidence; each item lights up as it passes and the counter ticks up
async function reveal(r, run) {
  const A = $('#answer'), val = $('#aVal');
  const isNum = typeof r.value === 'number' && r.unit !== 'text';
  const sumMode = isNum && r.unit !== 'count' && S.items.length && S.items.every(i => typeof i.value === 'number');
  const final = () => { if (isNum) val.textContent = fmtVal(r.value); A.classList.remove('counting'); };
  if (!S.items.length) { final(); return; }
  const by2d = new Map(SV.items.map(it => [it.n, it]));
  const order = [...S.items].map(it => {
    const b = by2d.get(it.n)?.bbox; const h = T.hl.find(h => h.it.n === it.n);
    return { it, x: b ? (b[0] + b[2]) / 2 : h ? h.c[0] : 0 };
  }).sort((a, b) => a.x - b.x);
  const xs = order.map(o => o.x), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const D = Math.min(2600, Math.max(900, 350 + S.items.length * 70));
  if (isNum) A.classList.add('counting');
  let scan = null;
  if (S.mode !== 'model' && SV.items.length && !SV.inline) scan = makeScan(x0, x1);
  else if (S.mode !== 'model' && SV.items.length) scan = makeScan(x0, x1);
  let k = 0, acc = 0; const t0 = performance.now();
  await new Promise(res => {
    (function step(now) {
      if (run !== S.run) { scan?.remove(); return res(); }
      const t = Math.min(1, (now - t0) / D), e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const x = x0 + (x1 - x0 + 1e-9) * e;
      while (k < order.length && (order[k].x <= x + 1e-9 || t >= 1)) {
        const it = order[k].it; revealItem(it.n); k++;
        if (sumMode) acc += it.value;
      }
      if (isNum) val.textContent = sumMode ? acc.toFixed(2) : k.toLocaleString('en');
      scan?.at(x, t);
      if (t < 1) requestAnimationFrame(step); else { scan?.done(); res(); }
    })(t0);
  });
  if (run !== S.run) return;
  final();
  S.revealed = true;
}
function makeScan(x0, x1) {
  const g = $('#ovFx'); g.innerHTML = '';
  const b = SV.items.reduce((a, it) => [Math.min(a[0], it.bbox[0]), Math.min(a[1], it.bbox[1]), Math.max(a[2], it.bbox[2]), Math.max(a[3], it.bbox[3])], [1e12, 1e12, -1e12, -1e12]);
  const m = Math.max(b[3] - b[1], b[2] - b[0]) * 0.08 + 2;
  const y0 = b[1] - m, h = b[3] - b[1] + 2 * m, band = Math.max((x1 - x0) * 0.25, (b[2] - b[0]) * 0.1, 4);
  const grp = document.createElementNS(NS, 'g'); grp.setAttribute('class', 'scan');
  const rect = document.createElementNS(NS, 'rect'); rect.setAttribute('y', y0); rect.setAttribute('height', h); rect.setAttribute('width', band); rect.setAttribute('fill', 'url(#scanG)');
  const line = document.createElementNS(NS, 'line'); line.setAttribute('class', 'scanline'); line.setAttribute('y1', y0); line.setAttribute('y2', y0 + h);
  grp.append(rect, line); g.append(grp);
  return {
    at(x, t) { rect.setAttribute('x', x - band); line.setAttribute('x1', x); line.setAttribute('x2', x); grp.style.opacity = t > .9 ? (1 - t) * 10 : 1; },
    done() { grp.remove(); }, remove() { grp.remove(); },
  };
}
function revealItem(n) {
  $$(`#ovItems .it[data-n="${n}"]`).forEach(g => g.classList.add('on'));
  $$(`#labels2d .lb[data-n="${n}"], #labels3d .lb[data-n="${n}"]`).forEach(l => l.classList.add('on'));
  $$(`#svgHost .gl[data-n="${n}"]`).forEach(g => g.classList.remove('pre'));
  const h = T.hl.find(h => h.it.n === n); if (h) h.shown = true;
  revealed3d();
}

// ============================================================ selection (click a number → zoom both views)
function select(n) {
  if (n == null || !S.items.length) return clearSel();
  const N = S.items.length;
  n = ((n - 1 + N) % N) + 1;
  S.sel = n;
  const it = S.items.find(i => i.n === n);
  $$('.sel').forEach(e => e.classList.remove('sel'));
  $('#ov').classList.add('focus'); $('#labels2d').classList.add('focus'); $('#labels3d').classList.add('focus');
  $$(`#ovItems .it[data-n="${n}"], #labels2d .lb[data-n="${n}"], #labels3d .lb[data-n="${n}"], #svgHost .gl[data-n="${n}"], #receipt [data-n="${n}"]`).forEach(e => e.classList.add('sel', 'on'));
  $(`#receipt [data-n="${n}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  const p2 = SV.items.find(x => x.n === n);
  if (p2 && S.mode !== 'model') {
    const b = p2.bbox, m = Math.max(b[2] - b[0], b[3] - b[1]) * 1.6 + Math.max(SV.vb[2], SV.vb[3]) * 0.015;
    fitBox([b[0] - m, b[1] - m, b[2] + m, b[3] + m]);
    const fx = $('#ovFx'); fx.innerHTML = '';
    const p = document.createElementNS(NS, 'rect');
    p.setAttribute('class', 'pulse'); p.setAttribute('x', b[0]); p.setAttribute('y', b[1]); p.setAttribute('width', b[2] - b[0]); p.setAttribute('height', b[3] - b[1]);
    fx.append(p);
  }
  if (it?.gid && S.has.model) { sel3d(n); if (S.mode !== 'sheet') focus3d(n); }
  else if (it?.gid && !p2 && S.has.model) { setMode('model'); focus3d(n); }
  updateStepper();
}
function clearSel() {
  S.sel = null;
  $$('.sel').forEach(e => e.classList.remove('sel'));
  $('#ov').classList.remove('focus'); $('#labels2d').classList.remove('focus'); $('#labels3d').classList.remove('focus');
  $('#ovFx').innerHTML = ''; $('#pick').hidden = true;
  sel3d(null);
  updateStepper();
  if (S.mode !== 'model') fitEvidence();
  if (S.mode !== 'sheet') fit3d(true);
}
function updateStepper() {
  const N = S.items.length;
  $('#stepTxt').innerHTML = S.sel ? `<b>${S.sel}</b> / ${N}` : `all ${N}`;
}
$('#prevBtn').onclick = () => select(S.sel ? S.sel - 1 : S.items.length);
$('#nextBtn').onclick = () => select(S.sel ? S.sel + 1 : 1);
$('#allBtn').onclick = clearSel;
document.addEventListener('keydown', e => {
  const typing = e.target.matches('input, textarea');
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openLib($('#lib').hidden); return; }
  if (e.key === 'Escape') { if (!$('#lib').hidden) return openLib(false); if (!$('#sb').hidden) return $('#sb').hidden = true; if (typing) return e.target.blur(); return clearSel(); }
  if (typing) return;
  if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
  else if (e.key === 'ArrowRight' || e.key === 'j') { e.preventDefault(); $('#nextBtn').click(); }
  else if (e.key === 'ArrowLeft' || e.key === 'k') { e.preventDefault(); $('#prevBtn').click(); }
  else if (e.key === '1') setMode('sheet', true); else if (e.key === '2') setMode('split', true); else if (e.key === '3') setMode('model', true);
});

function hot(n, on) {
  $$(`#ovItems .it[data-n="${n}"], #svgHost .gl[data-n="${n}"], #labels2d .lb[data-n="${n}"], #labels3d .lb[data-n="${n}"], #receipt [data-n="${n}"]`).forEach(g => g.classList.toggle('hot', on));
  hot3d(on ? n : null);
}

// ============================================================ modes (2D / split / 3D)
$$('#modes button').forEach(b => b.onclick = () => !b.disabled && setMode(b.dataset.m, true));
function updateModeButtons() {
  const { sheet, model } = S.has;
  $('#modes [data-m=sheet]').disabled = !sheet;
  $('#modes [data-m=model]').disabled = !model;
  $('#modes [data-m=split]').disabled = !(sheet && model);
  $('#tglTheme').disabled = !sheet;
}
function setMode(m, user) {
  if (m === 'split' && !(S.has.sheet && S.has.model)) m = S.has.model ? 'model' : 'sheet';
  if (m === 'sheet' && !S.has.sheet) m = 'model';
  if (m === 'model' && !S.has.model) m = 'sheet';
  if (user) S.userMode = m;
  const prev = S.mode; S.mode = m;
  $('#stage').dataset.mode = m;
  $$('#modes button').forEach(b => b.classList.toggle('on', b.dataset.m === m));
  $('#sheetv').hidden = m === 'model'; $('#modelv').hidden = m === 'sheet';
  $('#hint').textContent = m === 'sheet' ? 'scroll to zoom · drag to pan · ← → step through items' : m === 'model' ? 'drag to orbit · right-drag to pan · ← → step through items' : 'same GlobalIds light up in both views · ← → step';
  if (prev === m) return;
  requestAnimationFrame(() => {
    T.resize();
    if (m !== 'model' && S.items.length && S.revealed) {
      if (SV.inline && !SV.items.length) { drawOverlay(S.items); markRevealed(); }
      S.sel && SV.items.find(x => x.n === S.sel) ? select(S.sel) : fitEvidence(false);
    } else if (m !== 'model') fitBox(fullBox(), 20, false);
    if (m !== 'sheet' && S.revealed) { if (S.sel) focus3d(S.sel); else fit3d(false); }
  });
}
function markRevealed() { S.items.forEach(it => revealItem(it.n)); }

// ============================================================ 2D sheet viewer
// Content lives in "user units" (PDF points, image pixels, or the plan SVG's viewBox units).
// SV.vb = [x0, y0, w, h] in user units; SV.k = CSS px per unit inside the pan layer; SV.s/x/y = zoom + pan.
const SV = { s: 1, x: 0, y: 0, vb: [0, 0, 1, 1], k: 1, url: null, items: [], inline: false };
const U2P = (ux, uy) => [SV.x + (ux - SV.vb[0]) * SV.k * SV.s, SV.y + (uy - SV.vb[1]) * SV.k * SV.s];
const fullBox = () => [SV.vb[0], SV.vb[1], SV.vb[0] + SV.vb[2], SV.vb[1] + SV.vb[3]];
function showSheet(on) { $('#pan').style.display = on ? '' : 'none'; $('#sheetEmpty').style.display = on ? 'none' : ''; if (!on) $('#minimap').hidden = true; }
function sizeLayers() {
  const W = SV.vb[2] * SV.k, H = SV.vb[3] * SV.k;
  const host = SV.inline ? $('#svgHost') : $('#sheetImg');
  host.style.width = W + 'px'; host.style.height = H + 'px';
  const ov = $('#ov'); ov.setAttribute('viewBox', SV.vb.join(' ')); ov.style.width = W + 'px'; ov.style.height = H + 'px';
}
async function loadSheet(url, w, h, inline) {
  if (SV.url === url) { showSheet(true); return SV.loading; }
  SV.url = url; SV.inline = !!inline; SV.mini = null; applyTheme();
  SV.loading = (async () => {
    let host = $('#svgHost');
    if (!host) { host = el('div'); host.id = 'svgHost'; host.className = 'svghost'; $('#pan').prepend(host); }
    host.style.display = inline ? '' : 'none'; $('#sheetImg').style.display = inline ? 'none' : '';
    $('#sheetEmpty').querySelector('span').textContent = 'loading drawing…';
    if (inline) {
      const txt = await (await fetch(url)).text();
      if (SV.url !== url) return;
      host.innerHTML = txt;
      const svg = host.querySelector('svg'); svg.removeAttribute('width'); svg.removeAttribute('height');
      svg.style.width = '100%'; svg.style.height = '100%';
      SV.vb = svg.getAttribute('viewBox').split(/[ ,]+/).map(Number);
      SV.k = 1600 / Math.max(SV.vb[2], SV.vb[3]);
    } else {
      const img = $('#sheetImg');
      await new Promise(res => { img.onload = res; img.onerror = res; img.src = url; });
      if (SV.url !== url) return;
      SV.vb = [0, 0, w || img.naturalWidth, h || img.naturalHeight];
      SV.k = 1;
    }
    sizeLayers(); showSheet(true);
    fitBox(fullBox(), 20, false);
  })();
  return SV.loading;
}
function applyT() {
  $('#pan').style.transform = `translate(${SV.x}px,${SV.y}px) scale(${SV.s})`;
  placeLabels2d();
  if (!S.miniQ) { S.miniQ = true; requestAnimationFrame(() => { S.miniQ = false; drawMini(); }); }
}
// safe area: keep the evidence clear of the floating answer card and the dock
function insets() {
  const V = $('#sheetv').getBoundingClientRect();
  const ins = { l: 0, t: 0, r: 0, b: 56 };
  const A = $('#answer');
  if (!A.hidden) {
    const a = A.getBoundingClientRect();
    const useLeft = (V.width - a.width - 28) * V.height > V.width * (V.height - a.height - 28);
    if (useLeft) ins.l = a.right - V.left + 10; else ins.t = a.bottom - V.top + 10;
  }
  return ins;
}
function fitBox(b, pad = 40, anim = true) {
  const V = $('#sheetv').getBoundingClientRect(); if (!V.width) return Promise.resolve();
  const I = insets();
  const W = V.width - I.l - I.r, H = V.height - I.t - I.b;
  const bw = Math.max(b[2] - b[0], 1e-6) * SV.k, bh = Math.max(b[3] - b[1], 1e-6) * SV.k;
  const s = Math.min((W - 2 * pad) / bw, (H - 2 * pad) / bh, 14);
  const cx = (b[0] - SV.vb[0]) * SV.k + bw / 2, cy = (b[1] - SV.vb[1]) * SV.k + bh / 2;
  const tx = I.l + W / 2 - s * cx, ty = I.t + H / 2 - s * cy;
  if (!anim) { Object.assign(SV, { s, x: tx, y: ty }); applyT(); return Promise.resolve(); }
  const a = { s: SV.s, x: SV.x, y: SV.y }, t0 = performance.now(), Dur = 700;
  const id = (SV.anim = (SV.anim || 0) + 1);
  // zoom in log space so big zoom changes feel smooth
  const ls0 = Math.log(a.s), ls1 = Math.log(s);
  return new Promise(res => (function step(now) {
    if (id !== SV.anim) return res();
    const t = Math.min(1, (now - t0) / Dur), e = 1 - Math.pow(1 - t, 3);
    const sc = Math.exp(ls0 + (ls1 - ls0) * e);
    // keep the content point under the moving centre on a straight path
    const f = (sc - a.s) / ((s - a.s) || 1e-9);
    SV.s = sc; SV.x = a.x + (tx - a.x) * (Math.abs(s - a.s) > 1e-9 ? f : e); SV.y = a.y + (ty - a.y) * (Math.abs(s - a.s) > 1e-9 ? f : e); applyT();
    if (t < 1) requestAnimationFrame(step); else res();
  })(t0));
}
function evidenceBox() {
  if (!SV.items.length) return null;
  return SV.items.reduce((a, it) => [Math.min(a[0], it.bbox[0]), Math.min(a[1], it.bbox[1]), Math.max(a[2], it.bbox[2]), Math.max(a[3], it.bbox[3])], [1e12, 1e12, -1e12, -1e12]);
}
function fitEvidence(anim = true) {
  const b = evidenceBox();
  if (!b) return fitBox(fullBox(), 20, anim);
  const m = Math.max(b[2] - b[0], b[3] - b[1]) * 0.1 + Math.max(SV.vb[2], SV.vb[3]) * 0.01;
  return fitBox([b[0] - m, b[1] - m, b[2] + m, b[3] + m], 30, anim);
}
$('#fitBtn').onclick = () => { if (S.sel) return clearSel(); if (S.mode !== 'model') fitEvidence(); if (S.mode !== 'sheet') fit3d(true); };
// vector sheets default to blueprint; colour raster scans read better as paper
const isRaster = () => /\.(png|jpe?g)$/i.test(decodeURIComponent(SV.url || ''));
function applyTheme() { $('#sheetv').classList.toggle('blue', isRaster() ? !!S.blueR : S.blue); SV.mini = null; drawMini(); }
$('#tglTheme').onclick = () => { if (isRaster()) S.blueR = !S.blueR; else S.blue = !S.blue; applyTheme(); };
(() => {
  const v = $('#sheetv'); let d = null, moved = 0;
  v.addEventListener('wheel', e => {
    e.preventDefault(); SV.anim++;
    const r = v.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), s = Math.min(Math.max(SV.s * k, 0.02), 60);
    SV.x = mx - (mx - SV.x) * s / SV.s; SV.y = my - (my - SV.y) * s / SV.s; SV.s = s; applyT();
  }, { passive: false });
  v.addEventListener('pointerdown', e => {
    if (e.target.closest('.it, .lb, .minimap')) return;
    SV.anim++; d = { x: e.clientX - SV.x, y: e.clientY - SV.y }; moved = 0; v.classList.add('drag'); v.setPointerCapture(e.pointerId);
  });
  v.addEventListener('pointermove', e => { if (!d) return; moved++; SV.x = e.clientX - d.x; SV.y = e.clientY - d.y; applyT(); });
  v.addEventListener('pointerup', e => {
    v.classList.remove('drag');
    if (d && moved < 3 && SV.inline) {  // click on an IFC plan element → select its item
      const g = e.target.closest?.('#svgHost .gl'); if (g) select(+g.dataset.n);
    }
    d = null;
  });
})();

function drawOverlay(items) {
  const ov = $('#ovItems'); ov.innerHTML = ''; $('#ovFx').innerHTML = '';
  $('#ov').classList.remove('focus'); $('#labels2d').classList.remove('focus');
  $$('#svgHost .gl').forEach(g => { g.classList.remove('gl', 'hot', 'sel', 'pre'); delete g.dataset.n; });
  SV.items = [];
  if (SV.inline) {
    // IFC plan: highlight the plan's own elements by GlobalId (data-guid), no geometric fitting needed
    items.filter(i => i.gid).forEach(it => {
      const gs = [it.gid, ...(it.parts || [])].flatMap(g => $$(`#svgHost [data-guid="${CSS.escape(g)}"]`));
      if (!gs.length) return;
      let b = [1e12, 1e12, -1e12, -1e12];
      gs.forEach(g => { g.classList.add('gl', 'pre'); g.dataset.n = it.n; const bb = g.getBBox(); b = [Math.min(b[0], bb.x), Math.min(b[1], bb.y), Math.max(b[2], bb.x + bb.width), Math.max(b[3], bb.y + bb.height)]; });
      if (b[2] > b[0]) SV.items.push({ ...it, bbox: b, kind: it.cls === 'IfcSpace' ? 'room' : it.kind, plan: true });
    });
  } else SV.items = items.filter(i => i.bbox && !i.gid);
  const L = $('#labels2d'); L.innerHTML = '';
  const many = SV.items.length > 60;
  L.classList.toggle('sm', SV.items.length > 24);
  const minPad = Math.max(SV.vb[2], SV.vb[3]) * 0.0012;
  SV.items.forEach(it => {
    const warn = it.check && !it.check.ok;
    if (!it.plan) {
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('class', `it ${it.kind || ''}${warn ? ' warn' : ''}`); g.dataset.n = it.n;
      let sh;
      if (it.poly) {
        const ring = r => 'M' + r.map(p => p.join(',')).join('L') + 'Z';
        sh = document.createElementNS(NS, 'path'); sh.setAttribute('d', [it.poly, ...(it.holes || [])].map(ring).join(' ')); sh.setAttribute('fill-rule', 'evenodd');
      }
      else {
        const p = Math.max(minPad, Math.min(it.bbox[2] - it.bbox[0], it.bbox[3] - it.bbox[1]) * 0.15);
        sh = document.createElementNS(NS, 'rect');
        sh.setAttribute('x', it.bbox[0] - p); sh.setAttribute('y', it.bbox[1] - p);
        sh.setAttribute('width', it.bbox[2] - it.bbox[0] + 2 * p); sh.setAttribute('height', it.bbox[3] - it.bbox[1] + 2 * p); sh.setAttribute('rx', p);
      }
      sh.setAttribute('class', 'shape'); g.append(sh);
      g.onmouseenter = () => hot(it.n, true); g.onmouseleave = () => hot(it.n, false);
      g.onclick = () => select(it.n);
      ov.append(g);
    }
    const room = it.kind === 'room' && it.value != null;
    const lab = el('div', 'lb' + (room ? ' room' : '') + (many && !room ? ' dot' : '') + (warn ? ' warn' : ''), room ? `${it.n} · ${fmtVal(it.value)} m²` : it.n);
    lab.dataset.n = it.n; lab.title = it.label || '';
    if (warn && it.check.printed != null) lab.dataset.cx = `printed ${it.check.printed} ≠ computed ${fmtVal(it.check.computed ?? it.value)}`;
    lab.onmouseenter = () => hot(it.n, true); lab.onmouseleave = () => hot(it.n, false);
    lab.onclick = e => { e.stopPropagation(); select(it.n); };
    lab.onpointerdown = e => e.stopPropagation();
    L.append(lab); it.lab = lab;
  });
  placeLabels2d();
}
// getBBox only works once the inline SVG is visible and laid out: retry for a few frames
async function waitPlan(run) {
  for (let i = 0; i < 30 && run === S.run; i++) {
    await frame();
    drawOverlay(S.items);
    if (SV.items.length) return;
  }
}
function placeLabels2d() {
  SV.items.forEach(it => {
    if (!it.lab) return;
    const room = it.kind === 'room';
    const [x, y] = U2P(room ? (it.bbox[0] + it.bbox[2]) / 2 : it.bbox[2], room ? (it.bbox[1] + it.bbox[3]) / 2 : it.bbox[1]);
    it.lab.style.left = x + 'px'; it.lab.style.top = y + 'px';
  });
}

// ---- minimap: whole sheet, evidence dots, current viewport; click to jump
function drawMini() {
  const c = $('#minimap');
  if (S.mode === 'model' || !SV.url || $('#pan').style.display === 'none') { c.hidden = true; return; }
  const V = $('#sheetv').getBoundingClientRect();
  const vw = V.width / (SV.k * SV.s), vh = V.height / (SV.k * SV.s);
  const zoomed = vw < SV.vb[2] * 0.8 || vh < SV.vb[3] * 0.8;
  if (!zoomed || SV.inline) { c.hidden = true; return; }
  c.hidden = false;
  const W = c.width, H = c.height, sc = Math.min(W / SV.vb[2], H / SV.vb[3]);
  const ox = (W - SV.vb[2] * sc) / 2, oy = (H - SV.vb[3] * sc) / 2;
  SV.miniT = { sc, ox, oy };
  const ctx = c.getContext('2d');
  if (!SV.mini) {
    const off = document.createElement('canvas'); off.width = W; off.height = H;
    const o = off.getContext('2d');
    try { if (S.blue) o.filter = 'invert(.94) sepia(.35) hue-rotate(178deg) saturate(2.6) brightness(.95)'; o.fillStyle = '#fff'; o.fillRect(ox, oy, SV.vb[2] * sc, SV.vb[3] * sc); o.drawImage($('#sheetImg'), ox, oy, SV.vb[2] * sc, SV.vb[3] * sc); } catch (e) { }
    SV.mini = off;
  }
  ctx.clearRect(0, 0, W, H); ctx.drawImage(SV.mini, 0, 0);
  ctx.fillStyle = '#ffb020';
  SV.items.forEach(it => { const x = ox + ((it.bbox[0] + it.bbox[2]) / 2 - SV.vb[0]) * sc, y = oy + ((it.bbox[1] + it.bbox[3]) / 2 - SV.vb[1]) * sc; ctx.fillRect(x - 1.5, y - 1.5, 3, 3); });
  const x0 = -SV.x / (SV.k * SV.s), y0 = -SV.y / (SV.k * SV.s);
  ctx.strokeStyle = '#38d6ff'; ctx.lineWidth = 1.5; ctx.fillStyle = '#38d6ff22';
  ctx.fillRect(ox + x0 * sc, oy + y0 * sc, vw * sc, vh * sc); ctx.strokeRect(ox + x0 * sc, oy + y0 * sc, vw * sc, vh * sc);
}
$('#minimap').addEventListener('pointerdown', e => {
  e.stopPropagation();
  const c = $('#minimap'), r = c.getBoundingClientRect(), t = SV.miniT; if (!t) return;
  const ux = ((e.clientX - r.left) * c.width / r.width - t.ox) / t.sc + SV.vb[0], uy = ((e.clientY - r.top) * c.height / r.height - t.oy) / t.sc + SV.vb[1];
  const V = $('#sheetv').getBoundingClientRect();
  SV.anim++; SV.x = V.width / 2 - (ux - SV.vb[0]) * SV.k * SV.s; SV.y = V.height / 2 - (uy - SV.vb[1]) * SV.k * SV.s; applyT();
});

// ============================================================ 3D model viewer
const T = { inited: false, path: null, loading: null, hl: [] };
function init3d() {
  if (T.inited) return !T.failed; T.inited = true;
  const canvas = $('#three');
  try { T.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); }
  catch (e) { T.failed = true; $('#modelEmpty').style.display = ''; $('#modelEmpty span').textContent = '3D view needs WebGL, which this browser has disabled.'; return false; }
  T.renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); T.renderer.localClippingEnabled = true;
  T.renderer.toneMapping = THREE.ACESFilmicToneMapping; T.renderer.toneMappingExposure = 1.05;
  T.scene = new THREE.Scene();
  T.scene.fog = new THREE.Fog(0x0a1222, 200, 900);
  T.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
  T.controls = new OrbitControls(T.camera, canvas); T.controls.enableDamping = true; T.controls.dampingFactor = 0.08;
  T.scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x1a1408, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(60, 120, 80); T.scene.add(sun);
  const fill = new THREE.DirectionalLight(0x88aaff, 0.5); fill.position.set(-80, 40, -60); T.scene.add(fill);
  T.root = new THREE.Group(); T.root.rotation.x = -Math.PI / 2; T.scene.add(T.root);
  T.grid = new THREE.GridHelper(400, 80, 0x2a3a5a, 0x152036); T.grid.material.transparent = true; T.grid.material.opacity = .6; T.scene.add(T.grid);
  T.ray = new THREE.Raycaster();
  new ResizeObserver(() => T.resize()).observe($('#modelv'));
  let down = null;
  canvas.addEventListener('pointerdown', e => down = [e.clientX, e.clientY]);
  canvas.addEventListener('pointerup', e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 4) pick3d(e); down = null; });
  canvas.addEventListener('pointerdown', () => T.camAnim = (T.camAnim || 0) + 1);
  (function loop() {
    requestAnimationFrame(loop);
    if ($('#modelv').hidden) return;
    T.controls.update();
    const t = performance.now();
    if (T.hlMat) T.hlMat.emissiveIntensity = 0.5 + 0.3 * Math.sin(t / 300);
    if (T.selMat) T.selMat.opacity = 0.65 + 0.3 * Math.sin(t / 160);
    T.renderer.render(T.scene, T.camera); place3dLabels();
  })();
  return true;
}
T.resize = () => {
  if (!T.inited || T.failed) return;
  const r = $('#modelv').getBoundingClientRect(); if (!r.width) return;
  T.renderer.setSize(r.width, r.height, false); T.camera.aspect = r.width / r.height;
  // shift the projection so the model centres in the area not covered by the answer card
  const A = $('#answer'); let off = 0;
  if (!A.hidden && S.mode === 'model') { const a = A.getBoundingClientRect(); off = Math.min(a.right - r.left, r.width * 0.4) / 2; }
  if (off > 0) T.camera.setViewOffset(r.width, r.height, -off, 0, r.width, r.height); else T.camera.clearViewOffset();
  T.camera.updateProjectionMatrix();
};
async function loadModel(path) {
  if (!init3d()) return;
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
    T.root.clear(); T.hl = []; T.hlMesh = T.hlEdges = T.selMesh = T.hotMesh = null;
    T.H = H; T.byGid = new Map(); H.elements.forEach((e, k) => { e.k = k; (T.byGid.get(e.gid) || T.byGid.set(e.gid, []).get(e.gid)).push(e); });
    // per-storey floor level = 20th percentile of its elements' lowest z (robust to tall elements)
    const st = {};
    H.elements.forEach(e => { let z = 1e9; for (let v = e.v0; v < e.v0 + e.nv; v++) z = Math.min(z, P[v * 3 + 2]); if (e.storey) (st[e.storey] = st[e.storey] || []).push(z); });
    T.levels = Object.fromEntries(Object.entries(st).map(([k, zs]) => { zs.sort((a, b) => a - b); return [k, zs[Math.floor(zs.length * 0.2)]]; }));
    const C = new Float32Array(nV * 3);
    H.elements.forEach(e => { const c = e.rgb; for (let v = e.v0; v < e.v0 + e.nv; v++) { C[v * 3] = c[0]; C[v * 3 + 1] = c[1]; C[v * 3 + 2] = c[2]; } });
    T.pos = new THREE.BufferAttribute(P, 3); T.col = new THREE.BufferAttribute(C, 3);
    const base = H.elements.filter(e => e.cls !== 'IfcSpace');
    const { geo, map } = subset(base, I);
    T.baseMap = map; T.I = I;
    T.clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
    T.baseMat = new THREE.MeshStandardMaterial({ clippingPlanes: [T.clip], vertexColors: true, roughness: .78, metalness: .02, flatShading: true, side: THREE.DoubleSide, transparent: true, opacity: 1 });
    T.base = new THREE.Mesh(geo, T.baseMat); T.root.add(T.base);
    T.edges = null;
    if (geo.index.count < 4e6) {
      T.edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: 0x0b1222, transparent: true, opacity: .35, clippingPlanes: [T.clip] }));
      T.root.add(T.edges);
    }
    const bb = H.bbox; T.bbox = bb;
    T.grid.position.set(0, bb[2] - 0.02, 0);
    T.root.position.set(-(bb[0] + bb[3]) / 2, 0, (bb[1] + bb[4]) / 2);
    T.grid.scale.setScalar(Math.max(bb[3] - bb[0], bb[4] - bb[1]) / 200 * 1.6);
    T.resize();
    fit3d(false);
    $('#load3d').hidden = true;
  })();
  return T.loading;
}
// overlay geometries share the model's position/colour buffers: detach them before dispose so only the index is freed
function drop(key) {
  const m = T[key]; if (!m) return;
  T.root.remove(m);
  const g = m.geometry;
  if (m.isLineSegments) g.dispose(); else { g.deleteAttribute('position'); g.deleteAttribute('color'); g.dispose(); }
  T[key] = null;
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
function fit3d(anim = true, box, close) {
  if (!T.bbox) return Promise.resolve();
  T.root.updateMatrixWorld();
  const b = box || (T.hl.length ? elemBox(T.hl.flatMap(h => h.els)) : T.bbox);
  const c = toWorld((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
  const r = Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2], close ? 1.5 : 2) * 0.5;
  const d = r / Math.tan(THREE.MathUtils.degToRad(T.camera.fov / 2)) * (close ? 2.6 : 1.25);
  const dir = close ? T.camera.position.clone().sub(T.controls.target).normalize() : new THREE.Vector3(0.75, 0.62, 0.95).normalize();
  if (close && dir.y < 0.35) { dir.y = 0.35; dir.normalize(); }
  const to = c.clone().add(dir.multiplyScalar(d));
  const span = Math.max(T.bbox[3] - T.bbox[0], T.bbox[4] - T.bbox[1], T.bbox[5] - T.bbox[2]);
  T.camera.near = Math.max(0.05, d / 500); T.camera.far = Math.max(d, span) * 20; T.camera.updateProjectionMatrix();
  T.scene.fog.near = Math.max(d, span) * 2; T.scene.fog.far = Math.max(d, span) * 8;
  if (!anim) { T.camera.position.copy(to); T.controls.target.copy(c); return Promise.resolve(); }
  const p0 = T.camera.position.clone(), t0c = T.controls.target.clone(), t0 = performance.now();
  const id = (T.camAnim = (T.camAnim || 0) + 1);
  return new Promise(res => (function step(now) {
    if (id !== T.camAnim) return res();
    const t = Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - t, 3);
    T.camera.position.lerpVectors(p0, to, e); T.controls.target.lerpVectors(t0c, c, e);
    if (t < 1) requestAnimationFrame(step); else res();
  })(t0));
}
function highlight3d(items, storey) {
  if (!T.inited || T.failed || !T.H) { T.hl = []; $('#labels3d').innerHTML = ''; return; }
  T.cutInfo = null;
  if (T.clip) {
    const z0 = storey != null ? T.levels[storey] : null;
    if (z0 != null) {
      const above = Object.values(T.levels).filter(z => z > z0 + 0.5).sort((a, b) => a - b)[0];
      const cut = z0 + Math.min(1.2, above != null ? (above - z0) * 0.5 : 1.2);
      T.clip.constant = cut; T.cutInfo = `· section cut 1.2 m above “${storey}”`;
    } else T.clip.constant = 1e6;
  }
  $('#cutTag').textContent = T.cutInfo || '';
  for (const k of ['hlMesh', 'hlEdges', 'selMesh', 'hotMesh']) drop(k);
  T.hl = items.filter(i => i.gid).map(it => ({ it, els: [it.gid, ...(it.parts || [])].flatMap(g => T.byGid.get(g) || []) })).filter(h => h.els.length);
  const L = $('#labels3d'); L.innerHTML = ''; L.classList.remove('focus'); L.classList.toggle('sm', T.hl.length > 24);
  if (T.edges) { T.edges.material.color.set(T.hl.length ? 0x6f8fc7 : 0x0b1222); T.edges.material.opacity = T.hl.length ? .22 : .35; }
  if (!T.hl.length) { T.baseMat.opacity = 1; T.baseMat.depthWrite = true; T.hlMat = null; return; }
  T.baseMat.opacity = T.cutInfo ? 0.28 : 0.10; T.baseMat.depthWrite = false;
  T.hl.forEach(h => { const b = elemBox(h.els); h.c = [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, b[5]]; h.box = b; h.shown = false;
    if (T.hl.length <= 400) {
      const d = el('div', 'lb' + (T.hl.length > 40 ? ' dot' : ''), h.it.n); d.dataset.n = h.it.n; d.title = h.it.label || '';
      d.onclick = () => select(h.it.n); d.onmouseenter = () => hot(h.it.n, true); d.onmouseleave = () => hot(h.it.n, false);
      L.append(d); h.lab = d;
    } });
  const allSpaces = T.hl.every(h => h.els.every(e => e.cls === 'IfcSpace'));
  T.hlMat = new THREE.MeshStandardMaterial({ color: 0xffb020, emissive: 0xff8a00, emissiveIntensity: .6, roughness: .5, flatShading: true, side: THREE.DoubleSide, transparent: allSpaces, opacity: allSpaces ? .6 : 1 });
  T.hlShown = -1; revealed3d();
}
// rebuild the glowing mesh from the items revealed so far (called as the scan reaches each item)
function revealed3d() {
  if (!T.hlMat || !T.hl.length) return;
  const shown = T.hl.filter(h => h.shown);
  if (shown.length === T.hlShown) return;
  T.hlShown = shown.length;
  if (S.q3d) return; S.q3d = true;
  requestAnimationFrame(() => {
    S.q3d = false;
    for (const k of ['hlMesh', 'hlEdges']) drop(k);
    const els = T.hl.filter(h => h.shown).flatMap(h => h.els);
    if (!els.length) return;
    const { geo, map } = subset(els, T.I); T.hlMap = map;
    T.hlMesh = new THREE.Mesh(geo, T.hlMat); T.hlMesh.renderOrder = 2; T.root.add(T.hlMesh);
    if (els.length < 3000) {
      T.hlEdges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0xfff1c9, transparent: true, opacity: .9 }));
      T.root.add(T.hlEdges);
    }
  });
}
function place3dLabels() {
  if (S.mode === 'sheet' || !T.hl.length) return;
  const r = $('#modelv').getBoundingClientRect(); T.root.updateMatrixWorld();
  T.hl.forEach(h => { if (!h.lab) return; const v = toWorld(...h.c).project(T.camera);
    h.lab.style.display = v.z > 1 ? 'none' : ''; h.lab.style.left = ((v.x + 1) / 2 * r.width) + 'px'; h.lab.style.top = ((1 - v.y) / 2 * r.height) + 'px'; });
}
function overlayMesh(key, h, mat) {
  drop(key);
  if (!h) return;
  const { geo } = subset(h.els, T.I);
  T[key] = new THREE.Mesh(geo, mat); T[key].renderOrder = 5; T.root.add(T[key]);
}
function hot3d(n) {
  if (!T.H) return;
  overlayMesh('hotMesh', n == null ? null : T.hl.find(h => h.it.n == n), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: .75, depthTest: false }));
}
function sel3d(n) {
  if (!T.H) return;
  if (!T.selMat) T.selMat = new THREE.MeshBasicMaterial({ color: 0xff2d55, transparent: true, opacity: .9, depthTest: false });
  overlayMesh('selMesh', n == null ? null : T.hl.find(h => h.it.n == n), T.selMat);
}
function focus3d(n) { const h = T.hl.find(h => h.it.n === n); if (h) { fit3d(true, h.box, true); showPick(h.els[0], h.it); } }
function pick3d(e) {
  if (!T.H) return;
  const r = e.target.getBoundingClientRect();
  T.ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), T.camera);
  const targets = [T.hlMesh, T.base].filter(Boolean);
  const hit = T.ray.intersectObjects(targets, false)[0];
  if (!hit) { $('#pick').hidden = true; return; }
  const map = hit.object === T.hlMesh ? T.hlMap : T.baseMap, o = hit.faceIndex * 3;
  let lo = 0, hi = map.length - 1; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (map[m][0] <= o) lo = m; else hi = m - 1; }
  const e3 = map[lo][1];
  const h = T.hl.find(h => h.els.includes(e3));
  if (h) select(h.it.n); else showPick(e3);
}
function showPick(e, it) {
  const p = $('#pick'); p.hidden = false;
  p.innerHTML = `${it ? `<span class="pill" style="margin-right:6px">${it.n}</span>` : ''}<b>${esc(e.cls)}</b> ${esc(e.name || '')}<br><code>GlobalId ${esc(e.gid)}</code>${e.storey ? `<br><span class="muted">storey: ${esc(e.storey)}</span>` : ''}`;
}

// ============================================================ audit: grade every dataset question on this drawing
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
    d.onclick = () => { $('#q').value = q.q; r.q = q.q; S.last = r; show(r); };
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
  ['data/swiss_dwellings/site1000_bldg2082_floor9385.pdf', 'Wie viele WCs sind auf diesem Grundriss eingezeichnet?', 'sheet', 2],
  ['data/swiss_dwellings/site1000_bldg2082_floor9385.pdf', 'What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, terraces and other outdoor spaces?', 'sheet', 2],
  ['data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-04-4-korrus.pdf', 'Mitu ust on näidatud korruse „4.korrus“ plaanil?', 'split', 3],
  ['data/ifc_bench/duplex_arc.ifc', 'How many bedrooms are there?', 'model', 2],
  ['data/opening_design/Sports_Complex/Sheets - Current Set/A-801 - Door and Finish Schedules & Wall Types.pdf', 'On sheet A-801 of the Xcel Sports Complex drawings, how many doors in the door schedule are door type B2 (double aluminium door with glazing)?', 'sheet', 2],
  ['data/cubicasa5k/colorful-11400.png', 'Kuinka monta ikkunaa pohjapiirustuksessa on?', 'sheet', 2],
];
S.touring = false;
const tourWait = async ms => { const t = performance.now(); while (S.touring && performance.now() - t < ms) await sleep(100); };
async function tour() {
  if (S.touring) { S.touring = false; $('#tourBtn').textContent = '▶ Tour'; $('#tourBtn').classList.remove('on'); return; }
  S.touring = true; $('#tourBtn').textContent = '■ Stop'; $('#tourBtn').classList.add('on');
  const um = S.userMode;
  for (const [path, q, mode, steps] of TOUR) {
    if (!S.touring) break;
    const f = S.cat.find(x => x.path === path); if (!f) continue;
    S.userMode = mode;
    if (S.file !== f) { selectFile(f); await tourWait(900); }
    $('#q').value = '';
    for (const ch of q) { if (!S.touring) break; $('#q').value += ch; await sleep(16); }
    if (!S.touring) break;
    await ask();
    await tourWait(1600);
    for (let i = 1; i <= Math.min(steps, S.items.length) && S.touring; i++) { select(i); await tourWait(1700); }
    if (S.touring && S.items.length) { clearSel(); await tourWait(1800); }
  }
  S.userMode = um;
  S.touring = false; $('#tourBtn').textContent = '▶ Tour'; $('#tourBtn').classList.remove('on');
}
$('#tourBtn').onclick = tour;

window.PP = { S, SV, T, select, setMode, ask, hot, clearSel };
boot();
