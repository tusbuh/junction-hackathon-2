// App shell: left sidebar (features + library of sources) and the bottom player bar.
// Pure UI glue: every control here proxies an existing button or reads window.PP.S; no numbers are computed here.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const SRC = {   // display names and the licence shown in the library row (the full credit stays under every drawing)
  swiss_dwellings: ['Swiss CAD floor plans', 'DXF + PDF', 'CC BY 4.0'],
  ifc_models: ['IFC building models', 'IFC', 'per file'],
  ifc_bench: ['IFC bench', 'IFC', 'per file'],
  opening_design: ['US drawing sets', 'PDF', 'CC BY-SA 4.0'],
  cubicasa5k: ['Finnish raster scans', 'scan', 'CC BY-NC-SA 4.0'],
};
const TAG = { swiss_dwellings: 'CH', ifc_models: 'IFC', ifc_bench: 'IFC', opening_design: 'US', cubicasa5k: 'FI' };

// dynamically injected stylesheets (wow.css, audit.css, race.css) must not override the shell theme: keep ours last
const keepLast = () => { const me = $('#spotifyCss'); if (me && me !== document.head.lastElementChild) document.head.append(me); };
new MutationObserver(keepLast).observe(document.head, { childList: true });
keepLast();

// ---------------------------------------------------------------- sidebar features
$('#navAsk').onclick = () => { $('#splash').hidden = true; $('#q').focus(); };
$('#navRace').onclick = () => $('#meter').click();
// launcher buttons injected by wow.js / identify.js / audit.js land before #tourBtn, i.e. inside the sidebar
function syncActive() {
  const on = id => $(id)?.classList.toggle('active', true);
  document.querySelectorAll('.feat > button').forEach(b => b.classList.remove('active'));
  const B = document.body.classList;
  if (B.contains('wkOpen')) on('#wowWalk');
  else if (B.contains('boqOpen')) on('#wowBoq');
  else if (B.contains('idOn')) on('#idBtn');
  else if ($('.race:not([hidden])')) on('#navRace');
  else if (!$('#sb').hidden) on('#sbBtn');
  else if ($('#tourBtn').classList.contains('on')) on('#tourBtn');
  else on('#navAsk');
}

// ---------------------------------------------------------------- library: one row per source
let libDone = false;
function library() {
  const S = window.PP?.S; if (!S?.cat?.length) return;
  const counts = {}; S.cat.forEach(f => counts[f.source] = (counts[f.source] || 0) + 1);
  const box = $('#sideSrc');
  if (!libDone) {
    box.innerHTML = Object.keys(SRC).filter(k => counts[k]).map(k => `<button type="button" class="libRow" data-src="${k}">
      <span class="tile t-${k}">${TAG[k]}</span><span class="lt"><b>${esc(SRC[k][0])}</b><small>${esc(SRC[k][1])} · ${counts[k].toLocaleString('en')} drawings · ${esc(SRC[k][2])}</small></span></button>`).join('');
    box.querySelectorAll('.libRow').forEach(b => b.onclick = () => {
      $('#docBtn').click(); if ($('#lib').hidden) $('#docBtn').click();
      [...$('#srcs').children].find(x => x.textContent.startsWith(SRC_NAMES_APP[b.dataset.src] || '§'))?.click();
    });
    libDone = true;
  }
  box.querySelectorAll('.libRow').forEach(b => b.classList.toggle('on', b.dataset.src === S.file?.source));
}
// the drawer's source buttons are labelled by app.js's SRC_NAMES
const SRC_NAMES_APP = { swiss_dwellings: 'Swiss CAD', ifc_models: 'IFC models', ifc_bench: 'IFC bench', cubicasa5k: 'Finnish scans', opening_design: 'US sheets' };
$('#libAll').onclick = () => $('#docBtn').click();

// ---------------------------------------------------------------- player bar
$('#pPrev').onclick = () => { if (window.PP?.S?.items?.length) $('#prevBtn').click(); };
$('#pNext').onclick = () => { if (window.PP?.S?.items?.length) $('#nextBtn').click(); };
$('#pPlay').onclick = () => $('#tourBtn').click();
function player() {
  const S = window.PP?.S; if (!S) return;
  const f = S.file;
  $('#npTile').textContent = f ? (TAG[f.source] || '—') : '—';
  $('#npTile').className = 'npTile' + (f ? ' t-' + f.source : '');
  $('#npTitle').textContent = f ? f.name : 'pick a drawing';
  const A = $('#answer');
  let sub;
  if ($('#go').classList.contains('busy')) sub = 'answering…';
  else if (!A.hidden && $('#aVal').textContent) {
    const v = $('#aVal').textContent, u = $('#aUnit').textContent;
    sub = A.classList.contains('text') ? 'answered · text' : `answer: ${v}${u ? ' ' + u : ''}`;
  } else sub = f ? (SRC[f.source]?.[0] || f.source) + ' · ready, ask a question' : 'ready';
  $('#npSub').textContent = sub; $('#npSub').title = $('#aQ').textContent || '';
  const n = S.items?.length || 0, k = S.sel || 0;
  $('#pL').textContent = n ? (k || 'all') : '–'; $('#pR').textContent = n ? n : '–';
  $('#pFill').style.width = n ? (k ? 100 * k / n : 100) + '%' : '0%';
  $('#pPrev').disabled = $('#pNext').disabled = !n;
  $('#pPlay').classList.toggle('on', $('#tourBtn').classList.contains('on'));
  library(); syncActive();
  // splash cards: the green bar under each per-source score is the percentage already printed on the card
  document.querySelectorAll('.splash .stats > div').forEach(d => { const v = parseFloat(d.querySelector('b')?.textContent); if (!isNaN(v)) d.style.setProperty('--p', Math.min(100, v)); });
}
$('#pTrack').onclick = e => {   // click the track to jump to an item, like scrubbing
  const S = window.PP?.S, n = S?.items?.length; if (!n) return;
  const r = e.currentTarget.getBoundingClientRect(), k = Math.min(n, Math.max(1, Math.ceil((e.clientX - r.left) / r.width * n)));
  window.PP.select(k);
};
setInterval(player, 250); player();
