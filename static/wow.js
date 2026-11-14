// WOW-track launcher: adds "Walk in 3D" and "Bill of quantities" to the main UI without touching app.js.
const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/static/wow.css'; document.head.append(css);

const WALKABLE = p => /swiss_dwellings\//.test(p) || /ifc_models\/|ifc_bench\//.test(p) || p.endsWith('.ifc');

function mk(id, html, title, fn) {
  const b = document.createElement('button'); b.id = id; b.className = 'wowBtn'; b.innerHTML = html; b.title = title; b.type = 'button';
  b.onclick = () => fn(); return b;
}
function ctx() {
  const PP = window.PP; if (!PP?.S?.file) return null;
  const S = PP.S, last = S.last && S.last.q ? S.last : null;
  return { path: S.file.path, name: S.file.name, q: last?.q || document.querySelector('#q')?.value?.trim() || '', answer: last };
}
async function walk(extra = {}) {
  const c = ctx(); if (!c) return;
  const m = await import('/static/walk.js');
  m.openWalk({ path: c.path, name: c.name, q: c.answer ? c.answer.q : c.q, answer: c.answer, ...extra });
}
async function boq() {
  const c = ctx(); if (!c) return;
  const m = await import('/static/boq.js');
  m.openBoq({ path: c.path, name: c.name });
}

function mount() {
  const host = document.querySelector('.top') || document.body;
  const anchor = document.querySelector('#tourBtn');
  const w = mk('wowWalk', '🚶 Walk in 3D', 'Extrude this drawing into a 3D building and walk through it (W)', walk);
  const q = mk('wowBoq', '▤ Quantities', 'Instant bill of quantities for this drawing (Q)', boq);
  if (anchor) { anchor.before(w); anchor.before(q); } else { host.append(w, q); }
  const sync = () => { const p = window.PP?.S?.file?.path || ''; w.disabled = !WALKABLE(p); w.title = w.disabled ? '3D needs vector geometry (Swiss DXF or IFC)' : 'Extrude this drawing into a 3D building and walk through it (W)'; };
  setInterval(sync, 700); sync();
  addEventListener('keydown', e => {
    if (e.target.closest?.('input,textarea') || e.metaKey || e.ctrlKey || document.body.classList.contains('wkOpen') || document.body.classList.contains('boqOpen')) return;
    if (e.key === 'w' && !w.disabled) walk();
    if (e.key === 'q') boq();
  });
  const P = new URLSearchParams(location.search);
  if (P.get('walk')) setTimeout(function go() { if (window.PP?.S?.file && (!P.get('q') || window.PP.S.last)) walk({ mode: P.get('wmode'), sel: P.get('wsel') }); else setTimeout(go, 300); }, 600);
  if (P.get('boq')) setTimeout(function go() { if (window.PP?.S?.file) boq(); else setTimeout(go, 300); }, 600);
}
if (document.readyState === 'loading') addEventListener('DOMContentLoaded', mount); else mount();
