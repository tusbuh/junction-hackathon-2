// PINPOINT · COST RACE. Same eval questions, two lanes: PINPOINT (measured, data/eval/*.json) vs a frontier VLM
// (list-price estimate, sources cited). Every number on screen comes from /api/race; nothing is typed in here.
const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/static/race.css'; document.head.append(css);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const STATIC = () => new URLSearchParams(location.search).has('static') || matchMedia('(prefers-reduced-motion: reduce)').matches;
const NAMES = { swiss_dwellings: 'Swiss CAD floor plans', ifc_models: 'IFC building models', opening_design: 'US drawing sets (PDF)', cubicasa5k: 'Finnish raster scans', ifc_bench: 'IFC-Bench' };
const R = { open: false, run: 0 };
const fmtN = x => Math.round(x).toLocaleString('en');
const eur = v => {
  if (!v) return '€0';
  if (v >= 1) return '€' + v.toFixed(2);
  const d = Math.min(9, Math.max(2, 1 - Math.floor(Math.log10(v))));
  return '€' + v.toFixed(d);
};
const ratio = r => r >= 1e6 ? (r / 1e6).toFixed(1) + ' million' : fmtN(r);

function dom() {
  if (R.root) return;
  const d = document.createElement('div'); d.className = 'race'; d.hidden = true;
  d.innerHTML = `
  <div class="rcIn">
    <header><span class="rcK">COST RACE</span><h2>Same <b id="rcN">–</b> questions. Two ways to answer them.</h2>
      <button class="rcX" id="rcX" title="Close (Esc)">✕</button></header>
    <div class="rcTick"><span class="rcQn" id="rcQn">0</span><span class="rcQ" id="rcQ"></span></div>
    <div class="lane vlm">
      <div class="lh"><b>Frontier VLM</b><span class="est">ESTIMATE*</span><small id="rcVsub"></small></div>
      <div class="track"><i class="rcBar" id="rcVb"></i></div>
      <div class="lv"><b id="rcVe">€0</b><small>accuracy <em>not measured</em> · latency <em>not measured</em></small></div>
    </div>
    <div class="lane pp">
      <div class="lh"><b>PINPOINT</b><span class="meas">MEASURED</span><small id="rcPsub"></small></div>
      <div class="track"><i class="rcBar" id="rcPb"></i><span class="here" id="rcHere">← PINPOINT's bar is here: <b id="rcPct"></b> of the width</span></div>
      <div class="lv"><b id="rcPe">€0</b><small id="rcPacc"></small></div>
    </div>
    <div class="rcBig" id="rcBig"><b id="rcX1">–</b><span>× cheaper, on the questions we actually ran</span></div>
    <div class="rcLog" id="rcLog"><div class="lgh">Same two totals on a log scale, so PINPOINT's bar is visible at all</div><div class="lgAx" id="rcAx"></div></div>
    <table class="rcT" id="rcT"></table>
    <footer id="rcF"></footer>
    <div class="rcAct"><button id="rcAgain">Replay</button></div>
  </div>`;
  document.body.append(d); R.root = d; R.$ = s => d.querySelector(s);
  R.$('#rcX').onclick = close; R.$('#rcAgain').onclick = () => play();
  d.onclick = e => { if (e.target === d) close(); };
  addEventListener('keydown', e => { if (R.open && e.key === 'Escape') { e.stopPropagation(); close(); } }, true);
}
export function close() { R.open = false; R.run++; if (R.root) R.root.hidden = true; document.body.classList.remove('raceOpen'); }

export async function openRace() {
  dom(); R.root.hidden = false; R.open = true; document.body.classList.add('raceOpen');
  if (!R.d) R.d = await load();
  return play();
}

// /api/race (pinpoint/race.py); if a server started before race.py existed, rebuild the same totals from
// /api/scoreboard, which reads the same data/eval/*.json files (only the question ticker and CPU-seconds are missing).
async function load() {
  const r = await fetch('/api/race');
  if (r.ok) return r.json();
  const sb = await (await fetch('/api/scoreboard')).json();
  const sources = sb.map(x => ({ source: x.source, n: x.total, graded: x.graded, correct: x.correct, eur: x.eur, median_ms: x.median_ms, vlm_eur: x.vlm_eur })).sort((a, b) => b.n - a.n);
  const total = ['n', 'graded', 'correct', 'eur', 'vlm_eur'].reduce((o, k) => (o[k] = sources.reduce((a, x) => a + x[k], 0), o), {});
  return { sources, total, file: 'data/eval/*.json', sample: [], cpu_eur_per_h: 0.04, partial: true,
    vlm: { eur_per_q: total.vlm_eur / total.n, sources: [{ what: 'list price, Sonnet-class frontier VLM: $3 / Mtok input, $15 / Mtok output; ~1.6k image tokens per 1.15 MP', url: 'https://www.anthropic.com/pricing' }] } };
}

function play() {
  const d = R.d, T = d.total, V = d.vlm, $ = R.$, run = ++R.run, inst = STATIC();
  R.root.classList.remove('done');
  $('#rcN').textContent = fmtN(T.n);
  if (d.partial) {
    $('#rcVsub').textContent = `list-price estimate · ${eur(V.eur_per_q)} per question`;
    $('#rcPsub').textContent = `geometry already in the CAD / PDF / IFC file · 0 LLM calls · €${d.cpu_eur_per_h.toFixed(2)} / vCPU-hour`;
  } else {
  $('#rcVsub').textContent = `one ~${(V.px / 1e6).toFixed(0)} MP image (~${fmtN(V.img_tokens)} tokens) + ${V.prompt_tokens} prompt tokens in, ~${V.answer_tokens} out, per question · ${eur(V.eur_per_q)} each`;
  $('#rcPsub').textContent = `geometry already in the CAD / PDF / IFC file · 0 LLM calls · ${T.secs.toFixed(1)} s CPU in total · €${d.cpu_eur_per_h.toFixed(2)} / vCPU-hour`;
  }
  $('#rcPacc').innerHTML = `<em class="ok">${fmtN(T.correct)} / ${fmtN(T.graded)} correct</em> (counts exact, measures within 2%)` + (T.secs != null ? ` · ${T.secs.toFixed(1)} s CPU for all ${fmtN(T.n)}` : '');
  const r = T.vlm_eur / T.eur, pct = 100 * T.eur / T.vlm_eur;
  $('#rcPct').textContent = `${pct.toPrecision(2)}%`;
  $('#rcX1').textContent = ratio(r);
  // per-source table
  $('#rcT').innerHTML = `<tr><th>source</th><th>questions</th><th>correct</th><th>PINPOINT (measured)</th><th>median</th><th>frontier VLM (est.)</th><th>cheaper</th></tr>` +
    d.sources.map(s => `<tr><td>${esc(NAMES[s.source] || s.source)}</td><td>${fmtN(s.n)}</td><td class="ok">${fmtN(s.correct)} / ${fmtN(s.graded)}</td>
      <td class="pp">${eur(s.eur)}</td><td>${s.median_ms < 1 ? '<1' : s.median_ms.toFixed(0)} ms</td><td class="vl">${eur(s.vlm_eur)}</td><td><b>${ratio(s.vlm_eur / s.eur)}×</b></td></tr>`).join('') +
    `<tr class="tot"><td>all</td><td>${fmtN(T.n)}</td><td class="ok">${fmtN(T.correct)} / ${fmtN(T.graded)}</td><td class="pp">${eur(T.eur)}</td><td></td><td class="vl">${eur(T.vlm_eur)}</td><td><b>${ratio(r)}×</b></td></tr>`;
  $('#rcF').innerHTML = `<b>*</b> The VLM side is an <b>estimate</b>, not a run: list-price tokens for ${V.px ? `one ${(V.px / 1e6).toFixed(0)} MP image` : 'one sheet image'} per question (conservative; a whole sheet at legible 200 dpi is larger).
    Sources: ${V.sources.map(s => `${esc(s.what)} — <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url.replace('https://', ''))}</a>`).join('; ')}.
    PINPOINT: measured CPU seconds × €${d.cpu_eur_per_h.toFixed(2)}/vCPU-hour, per question, read from <code>${esc(d.file)}</code> (warm cache). Grading: counts exact, area/length/volume within 2%.`;
  // log axis
  const lo = Math.floor(Math.log10(T.eur)) , hi = Math.ceil(Math.log10(T.vlm_eur)), span = hi - lo;
  const pos = v => 100 * (Math.log10(v) - lo) / span;
  $('#rcAx').innerHTML = `<div class="lgRow pp"><i style="--w:${pos(T.eur)}%"></i><b>${eur(T.eur)}</b></div><div class="lgRow vlm"><i style="--w:${pos(T.vlm_eur)}%"></i><b>${eur(T.vlm_eur)}</b></div>` +
    `<div class="lgTicks">${Array.from({ length: span + 1 }, (_, k) => `<span style="left:${100 * k / span}%">${eur(10 ** (lo + k)).replace(/0+$/, '').replace(/\.$/, '')}</span>`).join('')}</div>`;
  // the race: questions stream through; each lane's meter adds its per-question cost
  const qs = d.sample || [];
  const finish = () => {
    $('#rcQn').textContent = fmtN(T.n); $('#rcQ').textContent = `all ${fmtN(T.n)} questions answered`;
    $('#rcVe').textContent = eur(T.vlm_eur); $('#rcPe').textContent = eur(T.eur);
    $('#rcVb').style.width = '100%'; $('#rcPb').style.width = `${pct}%`;
    R.root.classList.add('done');
  };
  if (inst) { finish(); return Promise.resolve(); }
  $('#rcVb').style.width = '0%'; $('#rcPb').style.width = '0%';
  const D = 5200, t0 = performance.now();
  return new Promise(res => (function step(now) {
    if (run !== R.run) return res();
    const t = Math.min(1, (now - t0) / D), k = t * t * (3 - 2 * t), n = Math.round(k * T.n);
    $('#rcQn').textContent = fmtN(n);
    if (qs.length) $('#rcQ').textContent = qs[Math.min(qs.length - 1, Math.floor(k * qs.length))];
    $('#rcVe').textContent = eur(k * T.vlm_eur); $('#rcPe').textContent = eur(k * T.eur);
    $('#rcVb').style.width = `${100 * k}%`; $('#rcPb').style.width = `${pct * k}%`;
    if (t < 1) requestAnimationFrame(step); else { finish(); res(); }
  })(t0));
}
