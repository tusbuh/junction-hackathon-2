// PINPOINT receipt panel: answer, confidence colour, cross-check badges, itemized evidence with citations,
// excluded items with reasons, derivation steps and source credit. Self-contained: renderReceipt(r, host, hooks).
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const num = v => typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en') : v.toLocaleString('en', { maximumFractionDigits: 2, minimumFractionDigits: 2 })) : (v ?? '—');
const withUnit = (v, u) => v == null || v === '' ? '—' : `${num(v)}${u && u !== 'count' && u !== 'text' ? ' ' + u : ''}`;
const CONF = { high: 'High confidence', check: 'Check the flagged items', low: 'Low confidence' };

function delta(p, c) {
  if (typeof p !== 'number' || typeof c !== 'number' || !p) return '';
  const d = (c - p) / Math.abs(p) * 100;
  return `${d > 0 ? '+' : ''}${d.toFixed(Math.abs(d) < 10 ? 1 : 0)}%`;
}

function checkRow(c) {
  const ok = c.ok !== false;
  const vals = c.printed != null || c.computed != null
    ? `<span class="rc-vals"><b>${esc(withUnit(c.printed, c.unit))}</b><i>${ok ? '=' : '≠'}</i><b>${esc(withUnit(c.computed, c.unit))}</b>${ok ? '' : `<em>${delta(c.printed, c.computed)}</em>`}</span>` : '';
  return `<div class="rc-check ${ok ? 'ok' : 'warn'}"><span class="rc-ico">${ok ? '✓' : '!'}</span>
    <span class="rc-what">${esc(c.what)}${c.note ? `<small>${esc(c.note)}</small>` : ''}</span>${vals}</div>`;
}

function itemRow(it, unit) {
  const c = it.check;
  const warn = c && c.ok === false;
  let badge = '';
  if (c && c.what === 'duplicate geometry') badge = `<span class="rc-b warn" title="same bounding box and volume as ${esc(c.printed)}">duplicate of ${esc(c.printed)}</span>`;
  else if (c && c.what === 'low confidence') badge = `<span class="rc-b warn" title="detector confidence">conf ${num(c.computed)}</span>`;
  else if (c) badge = `<span class="rc-b ${warn ? 'warn' : 'ok'}" title="${esc(c.what || 'printed label vs computed geometry')}">${warn ? '≠' : '='} ${esc(c.what && /Qto|mesh/.test(c.what) ? 'Qto' : 'label')} ${esc(num(c.printed))}${warn ? ` <em>${delta(c.printed, c.computed)}</em>` : ''}</span>`;
  const val = it.value != null && unit !== 'text' ? `<span class="rc-v">${esc(withUnit(it.value, unit))}</span>` : '';
  return `<div class="rc-item${warn ? ' warn' : ''}" data-n="${it.n}" tabindex="0">
    <span class="rc-n">${it.n}</span>
    <span class="rc-l">${esc(it.label || it.kind)}<small>${esc(it.cite || '')}</small></span>
    <span class="rc-r">${val}${badge}</span></div>`;
}

function tolRow(t, r) {
  if (!t) return '';
  const cls = t.ok === true ? 'ok' : t.ok === false ? 'warn' : '';
  const ref = t.reference != null && t.text == null ? `<small>reference: ${esc(String(t.reference).slice(0, 220))}</small>` : '';
  return `<div class="rc-tol ${cls}"><span class="rc-tl">Tolerance</span><span><b>${esc(t.rule)}</b>${t.text ? `<small>${t.ok === true ? '✓ ' : t.ok === false ? '✗ ' : ''}${esc(t.text)}</small>` : ''}${ref}</span></div>`;
}

export function renderReceipt(r, host, hooks = {}) {
  if (!host) return;
  const rc = r.receipt || {};
  const conf = rc.confidence || null;   // servers started before cite.py send no receipt: show no colour rather than a false 'low'
  const items = r.items || [];
  const checks = rc.checks || [];
  const exc = rc.excluded || [];
  const src = rc.source || {};
  const isText = r.unit === 'text';
  const bad = checks.filter(c => c.ok === false).length + items.filter(i => i.check && i.check.ok === false && i.check.what !== 'low confidence').length;
  const showSum = items.length > 1 && r.unit && !['count', 'text'].includes(r.unit) && r.value != null;

  host.innerHTML = `
  <div class="rc ${conf ? conf.colour : ''}">
    ${conf ? `<div class="rc-head">
      <div class="rc-conf"><span class="rc-dot"></span><b>${CONF[conf.level] || conf.level}</b><span class="rc-score">${Math.round((conf.score || 0) * 100)}</span></div>
      <div class="rc-why">${(conf.why || []).map(w => `<span>${esc(w)}</span>`).join('')}</div>
    </div>` : ''}
    <div class="rc-ans${isText ? ' text' : ''}">
      <div class="rc-val">${r.value == null ? 'no answer' : esc(isText ? r.value : withUnit(r.value, r.unit === 'count' ? '' : r.unit))}${r.unit === 'count' && r.value != null ? '<small>counted</small>' : ''}</div>
      <div class="rc-method">${esc(r.method || '')}</div>
    </div>
    ${tolRow(rc.tolerance, r)}
    ${checks.length ? `<div class="rc-sec"><h4>Cross-checks <span class="${bad ? 'warn' : 'ok'}">${bad ? `${bad} disagree` : 'all agree'}</span></h4>${checks.map(checkRow).join('')}</div>` : ''}
    <div class="rc-sec"><h4>Itemized evidence <span>${items.length} cited · click to locate on the drawing</span></h4>
      <div class="rc-items">${items.map(it => itemRow(it, r.unit)).join('') || '<div class="rc-empty">No drawing elements cited.</div>'}</div>
      ${showSum ? `<div class="rc-sum"><span>Σ ${items.length} items</span><b>${esc(withUnit(r.value, r.unit))}</b></div>` : ''}
    </div>
    ${exc.length ? `<details class="rc-sec rc-exc"><summary><h4>Excluded from the take-off <span>${exc.length}</span></h4></summary>
      ${exc.map(e => `<div class="rc-item ex"><span class="rc-n">–</span><span class="rc-l">${esc(e.label)}<small>${esc(e.reason)}</small><small>${esc(e.cite || '')}</small></span><span class="rc-r"><span class="rc-v">${esc(withUnit(e.value, r.unit))}</span></span></div>`).join('')}
    </details>` : ''}
    <details class="rc-sec rc-steps" ${items.length ? '' : 'open'}><summary><h4>How it was derived <span>${(r.steps || []).length} steps</span></h4></summary>
      <ol>${(r.steps || []).map(s => `<li>${esc(s)}</li>`).join('')}</ol></details>
    <div class="rc-src">
      <div><b>${esc(src.file || '')}</b> · ${esc(src.kind || '')}</div>
      ${src.licence ? `<div class="rc-lic">${esc(src.licence)}</div>` : ''}
    </div>
  </div>`;

  host.querySelectorAll('.rc-item[data-n]').forEach(row => {
    const n = +row.dataset.n, it = items.find(i => i.n === n);
    row.onmouseenter = () => hooks.onHover && hooks.onHover(n, true);
    row.onmouseleave = () => hooks.onHover && hooks.onHover(n, false);
    row.onclick = () => hooks.onFocus && hooks.onFocus(it);
    row.onkeydown = e => { if (e.key === 'Enter') row.click(); };
  });
}

if (typeof window !== 'undefined') window.renderReceipt = renderReceipt;
