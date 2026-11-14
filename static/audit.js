// DRAWING AUDIT: where a drawing disagrees with itself. Amber badges for printed-vs-computed mismatches, a findings list
// whose items light up on the drawing, and "what a site engineer should double-check" per drawing.
// Self-contained: adds an "Audit" button to the header and an "Errors we found" showcase; uses window.PP from app.js.
const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/static/audit.css'; document.head.append(css);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const $ = s => document.querySelector(s);
const cache = new Map();
// servers started before drawaudit.py have no /api/audit: the button then hides itself instead of failing
const get = async p => { if (!cache.has(p)) cache.set(p, fetch('/api/audit?path=' + encodeURIComponent(p)).then(r => r.ok ? r.json() : null).catch(() => null)); return cache.get(p); };
let SHOW = null;

const KIND = { schedule_vs_plan: 'Schedule ≠ plan', untagged_door: 'Untagged door', revision: 'Revision change', duplicate: 'Duplicate element',
  overlap: 'Overlapping copy', space_body: 'Qto area ≠ 3D body', label_vs_geometry: 'Label ≠ outline' };

function checkRow(c) {
  const v = c.printed != null ? `<span class="au-v">${esc(c.printed)} <i>${c.ok ? '=' : '≠'}</i> ${esc(c.computed)}${c.unit ? ` <small>${esc(c.unit)}</small>` : ''}</span>` : '';
  return `<div class="au-chk ${c.ok ? 'ok' : 'warn'}"><span class="au-ico">${c.ok ? '✓' : '!'}</span><span>${esc(c.what)}<small>${esc(c.note || '')}</small></span>${v}</div>`;
}

function findingCard(f, i) {
  return `<div class="au-f" data-i="${i}" tabindex="0">
    <div class="au-ft"><span class="au-k">${esc(KIND[f.kind] || f.kind)}</span>${f.printed != null ? `<span class="au-pc">${esc(f.printed)} ≠ ${esc(f.computed)} ${esc(f.unit || '')}</span>` : ''}</div>
    <b>${esc(f.title)}</b>${f.detail ? `<small>${esc(f.detail)}</small>` : ''}
    <div class="au-cites">${(f.items || []).slice(0, 4).map(it => `<code>${esc(it.cite || it.label)}</code>`).join('')}</div>
    <span class="au-go">show on drawing →</span></div>`;
}

export function renderAudit(a, host) {
  const bad = a.findings.length;
  host.innerHTML = `<div class="au">
    <div class="au-head ${bad ? 'warn' : 'ok'}"><span class="au-dot"></span><div><b>Drawing audit</b><small>${esc(a.file)}</small></div>
      <span class="au-n">${bad ? `${bad} to check` : 'consistent'}</span></div>
    <div class="au-sec"><h4>Cross-checks <span>two independent readings of the same fact</span></h4>${a.checks.map(checkRow).join('') || '<div class="au-empty">No cross-checkable facts on this drawing.</div>'}</div>
    ${bad ? `<div class="au-sec"><h4>Discrepancies <span>${bad} · click to see the evidence</span></h4>${a.findings.map(findingCard).join('')}</div>` : ''}
    <div class="au-sec au-dbl"><h4>What a site engineer should double-check</h4><ol>${a.doublecheck.map(d => `<li>${esc(d)}</li>`).join('')}</ol></div>
    <div class="au-src">${esc(a.file)}${a.licence ? `<div>${esc(a.licence)}</div>` : ''}</div>
    <button type="button" class="au-sc">Errors we found in the dataset</button>
  </div>`;
  host.querySelectorAll('.au-f').forEach(el => { el.onclick = () => focusFinding(a, a.findings[+el.dataset.i], host); el.onkeydown = e => e.key === 'Enter' && el.click(); });
  host.querySelector('.au-sc').onclick = showcase;
}

// a finding becomes a pseudo-answer so the existing viewers (2D overlay / 3D X-ray) light up its evidence in amber
function focusFinding(a, f, host) {
  const PP = window.PP; if (!PP) return;
  const items = (f.items || []).map((it, k) => ({ ...it, n: k + 1, check: { ok: false, what: 'audit', printed: f.printed ?? null, computed: f.computed ?? null } }));
  let view;
  if (f.model || a.model) view = { kind: 'model' };
  else {
    const pg = (a.pages || []).find(p => p.page === (f.page || 0));
    // the server-built URL (not app.js's encoding): the viewer then loads it in PDF points, the unit of the evidence boxes
    view = pg ? { kind: 'sheet', url: pg.url, w: pg.w, h: pg.h } : a.view;
  }
  const r = { q: f.title, value: KIND[f.kind] || 'Discrepancy', unit: 'text', method: f.detail || '', items, view, model: f.model || a.model, steps: [], router: 'rules',
    receipt: { confidence: { level: 'check', colour: 'amber', score: 0.6, why: ['drawing audit finding'] }, checks: [], source: { file: a.file, licence: a.licence } } };
  $('#docName') && ($('#docName').textContent = a.file);
  PP.credit && PP.credit(f.model || a.model || a.path, !!(f.model || a.model));   // licence credit of the drawing on screen
  if ($('#splash')) $('#splash').hidden = true;
  if ($('#srcTag')) $('#srcTag').textContent = (f.model || a.model) ? 'IFC' : 'PDF';
  const pr = PP.show(r);
  // one small symbol: frame it with the surrounding rooms (≈ 12 symbol widths) so a site engineer can find it on the sheet
  const bb = items.filter(i => i.bbox).map(i => i.bbox);
  if (bb.length && !(f.model || a.model) && PP.fitBox) pr.then(() => {
    const b = bb.reduce((x, y) => [Math.min(x[0], y[0]), Math.min(x[1], y[1]), Math.max(x[2], y[2]), Math.max(x[3], y[3])]);
    const m = Math.max(0, 140 - Math.max(b[2] - b[0], b[3] - b[1]) / 2);
    if (m > 0) PP.fitBox([b[0] - m, b[1] - m, b[2] + m, b[3] + m]);
  });
  renderAudit(a, host);          // keep the audit in the side panel (show() rendered a receipt there synchronously)
  host.querySelectorAll('.au-f').forEach(el => el.classList.toggle('on', a.findings[+el.dataset.i] === f));
  host.querySelector('.au-f.on')?.scrollIntoView({ block: 'nearest' });
}

export async function openAudit(path) {
  const PP = window.PP; const p = path || PP?.S?.file?.path; if (!p) return;
  if ($('#splash')) $('#splash').hidden = true;
  const host = $('#receipt'); host.innerHTML = '<div class="au-empty">Auditing the drawing…</div>';
  const a = await get(p);
  if (!a) { host.innerHTML = '<div class="au-empty">Drawing audit needs the server restarted on the current code.</div>'; return; }
  renderAudit(a, host);
}

async function showcase() {
  let m = $('#auShow');
  if (!m) {
    m = document.createElement('div'); m.id = 'auShow'; m.className = 'au-modal'; m.hidden = true;
    m.innerHTML = '<div class="au-card"><div class="au-mh"><h2>Errors we found in the dataset <small>each one measured from the files, with the evidence one click away</small></h2><button type="button">✕</button></div><div class="au-mb">Auditing…</div></div>';
    m.querySelector('button').onclick = () => m.hidden = true;
    m.onclick = e => { if (e.target === m) m.hidden = true; };
    document.body.append(m);
  }
  m.hidden = false;
  SHOW = SHOW || await fetch('/api/audit/showcase').then(r => r.ok ? r.json() : null).catch(() => null);
  if (!SHOW) { m.querySelector('.au-mb').textContent = 'The showcase needs the server restarted on the current code.'; return; }
  const cards = [];
  SHOW.audits.forEach((a, ai) => a.findings.forEach((f, fi) => cards.push({ a, f, ai, fi })));
  // lead with the strongest kinds of evidence; one card per kind and file keeps the list readable
  const order = ['schedule_vs_plan', 'untagged_door', 'duplicate', 'space_body', 'revision', 'overlap'];
  cards.sort((x, y) => order.indexOf(x.f.kind) - order.indexOf(y.f.kind));
  const seen = new Set(), pick = cards.filter(c => { const k = c.a.file + c.f.kind; if (seen.has(k)) return false; seen.add(k); return true; });
  const more = c => c.a.findings.filter(f => f.kind === c.f.kind).length - 1;
  m.querySelector('.au-mb').innerHTML = pick.map((c, i) => `<div class="au-sf" data-i="${i}">
      <span class="au-k">${esc(KIND[c.f.kind] || c.f.kind)}</span><b>${esc(c.f.title)}</b>${more(c) > 0 ? `<em>+${more(c)} more like it</em>` : ''}
      <small>${esc(c.f.detail || '')}</small><code>${esc(c.a.file)}</code><span class="au-lic">${esc((c.a.licence || '').split(' · http')[0])}</span></div>`).join('')
    + (k => `<p class="au-note">Also audited, nothing to flag: ${k.swiss_rooms ? `${k.swiss_rooms.toLocaleString('en')} printed m² room labels on the Swiss CAD plans all match their drawn outlines (±2 %). ` : ''}`
      + `${k.elements ? `IFC: ${k.elements.toLocaleString('en')} building elements and ${k.spaces} spaces in ${k.models} models fingerprinted for duplicates, overlaps and Qto-vs-body.` : ''}</p>`)(SHOW.checked || {});
  m.querySelectorAll('.au-sf').forEach(el => el.onclick = () => {
    const c = pick[+el.dataset.i]; m.hidden = true;
    const host = $('#receipt'); renderAudit(c.a, host); focusFinding(c.a, c.f, host);
  });
}

function mount() {
  const anchor = document.querySelector('#tourBtn');
  const b = document.createElement('button'); b.id = 'auBtn'; b.type = 'button'; b.className = 'wowBtn au-btn';
  b.innerHTML = 'Audit <span class="au-badge" hidden></span>'; b.title = 'Drawing audit: where this drawing disagrees with itself (A)';
  b.onclick = () => openAudit();
  if (anchor) anchor.before(b); else (document.querySelector('.top') || document.body).append(b);
  let last = null;
  setInterval(async () => {   // amber count badge for the drawing on screen
    const p = window.PP?.S?.file?.path; if (!p || p === last) return; last = p;
    const a = await get(p); if (!a) { b.hidden = true; return; } if (window.PP?.S?.file?.path !== p) return;
    const s = b.querySelector('.au-badge'); s.hidden = !a.findings.length; s.textContent = a.findings.length;
  }, 800);
  addEventListener('keydown', e => { if (!e.target.closest?.('input,textarea') && !e.metaKey && !e.ctrlKey && e.key === 'a') openAudit(); });
  const P = new URLSearchParams(location.search);
  if (P.get('audit')) setTimeout(function go() {
    if (!window.PP?.S?.file) return setTimeout(go, 300);
    if (P.get('audit') === 'showcase') showcase().then(() => { if (P.get('pick') != null) document.querySelector(`.au-sf[data-i="${P.get('pick')}"]`)?.click(); });
    else openAudit(P.get('audit') === '1' ? null : P.get('audit')).then(() => { if (P.get('f') != null) document.querySelector(`#receipt .au-f[data-i="${P.get('f')}"]`)?.click(); });
  }, 700);
}
if (document.readyState === 'loading') addEventListener('DOMContentLoaded', mount); else mount();
window.PPaudit = { open: openAudit, showcase };
