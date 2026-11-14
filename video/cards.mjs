// Renders caption bands (1920x120) and the title / end cards (1920x1080) to PNG with headless Chrome.
// End-card numbers are fetched live from /api/scoreboard and /api/race: nothing typed in by hand.
import fs from 'node:fs';
const PW = process.env.PW_CORE || '/Users/hubertusfinckenberg/ANKKU-Game/node_modules/playwright-core/index.mjs';
const { chromium } = await import(PW);
const BASE = process.env.PP_BASE || 'http://localhost:8737';
const OUT = process.env.CARDS || '/tmp/ppvid/cards';
fs.mkdirSync(OUT, { recursive: true });
const CFG = JSON.parse(fs.readFileSync(new URL('./scenes.json', import.meta.url)));
const sb = await (await fetch(BASE + '/api/scoreboard')).json();
const race = await (await fetch(BASE + '/api/race')).json();
const by = Object.fromEntries(sb.map(x => [x.source, x]));
const n = x => x.toLocaleString('en');
const eur = race.total.eur, vlm = race.total.vlm_eur, ratio = vlm / eur;
const fmtEur = v => v >= 1 ? '€' + v.toFixed(2) : '€' + v.toFixed(Math.min(10, Math.max(2, 1 - Math.floor(Math.log10(v)))));
const facts = {
  ifc: `${n(by.ifc_models.correct)} / ${n(by.ifc_models.graded)}`, swiss: `${n(by.swiss_dwellings.correct)} / ${n(by.swiss_dwellings.graded)}`,
  cc: `${n(by.cubicasa5k.correct)} / ${n(by.cubicasa5k.graded)}`, us: `${n(by.opening_design.correct)} / ${n(by.opening_design.graded)}`,
  eur: fmtEur(eur), vlm: fmtEur(vlm), ratio: n(Math.round(ratio)), q: n(race.total.n), secs: race.total.secs.toFixed(1),
};
fs.writeFileSync(`${OUT}/facts.json`, JSON.stringify(facts, null, 1));
console.log(facts);

const FONT = `font-family: Inter, "SF Pro Display", -apple-system, "Helvetica Neue", Arial, sans-serif;`;
const css = `*{margin:0;box-sizing:border-box} body{${FONT} background:transparent; color:#fff}
 em{font-style:normal;color:#ffb02e}
 .band{width:1920px;height:120px;background:#06090f;border-top:2px solid #1d2635;display:flex;align-items:center;padding:0 56px;gap:28px}
 .band .tag{flex:none;font:700 17px/1 ui-monospace,Menlo,monospace;letter-spacing:.22em;color:#ffb02e;border:2px solid #ffb02e55;border-radius:8px;padding:10px 12px}
 .band .t{font-weight:700;font-size:42px;letter-spacing:-.01em;white-space:nowrap;line-height:1.1}
 .card{width:1920px;height:1080px;background:radial-gradient(1200px 700px at 50% 40%,#13213a 0%,#070a11 70%);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;position:relative;overflow:hidden}
 .grid{position:absolute;inset:0;background-image:linear-gradient(#5aa9ff14 1px,transparent 1px),linear-gradient(90deg,#5aa9ff14 1px,transparent 1px);background-size:48px 48px}
 .logo{width:120px;height:120px;margin-bottom:34px;position:relative}
 h1{font-size:150px;font-weight:900;letter-spacing:.06em;position:relative}
 h2{font-size:66px;font-weight:800;margin-top:6px;position:relative;letter-spacing:-.01em}
 .sub{font-size:34px;color:#b8c3d6;margin-top:34px;position:relative}
 .stats{display:grid;grid-template-columns:repeat(3,500px);gap:26px;margin-top:56px;position:relative}
 .st{border:2px solid #2a3850;border-radius:22px;padding:28px 20px;background:#0b1220cc}
 .st b{display:block;font:800 58px/1 ui-monospace,Menlo,monospace;color:#3ddc97;white-space:nowrap}
 .st b.amber{color:#ffb02e} .st span{display:block;font-size:21px;color:#aab6c9;margin-top:14px;letter-spacing:.08em;text-transform:uppercase}
 .cost{margin-top:34px;font-size:40px;position:relative;border:2px solid #3ddc9755;background:#0c1d18cc;border-radius:22px;padding:22px 40px}
 .cost b{color:#3ddc97;font-family:ui-monospace,Menlo,monospace} .cost s{color:#ff7a59;text-decoration:none;font-family:ui-monospace,Menlo,monospace}
 .credit{position:absolute;bottom:36px;left:0;right:0;font-size:19px;color:#7d8aa0;line-height:1.5}`;
const LOGO = `<svg class="logo" viewBox="0 0 64 64"><circle cx="32" cy="32" r="26" fill="none" stroke="#ffb02e" stroke-width="4"/><circle cx="32" cy="32" r="14" fill="none" stroke="#ffb02e" stroke-width="4"/><circle cx="32" cy="32" r="4" fill="#ffb02e"/><path d="M32 0v12M32 52v12M0 32h12M52 32h12" stroke="#ffb02e" stroke-width="4"/></svg>`;

const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
async function shot(html, file, w, h) {
  await p.setViewportSize({ width: w, height: h });
  await p.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>${css}</style></head><body>${html}</body></html>`);
  await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: file, omitBackground: true, clip: { x: 0, y: 0, width: w, height: h } });
}
// caption bands
for (const s of CFG.scenes) for (const [i, [, text]] of (s.captions || []).entries()) {
  await shot(`<div class="band"><span class="tag">PINPOINT</span><span class="t">${text}</span></div>`, `${OUT}/${s.id}_c${i}.png`, 1920, 120);
  const w = await p.evaluate(() => document.querySelector('.t').getBoundingClientRect().right);
  if (w > 1880) console.log('WARNING caption too wide', s.id, i, w);
}
await shot(`<div class="card"><div class="grid"></div>${LOGO}<h1>PINPOINT</h1><h2>blueprints that <em>show</em></h2>
  <div class="sub">Ask a construction drawing anything. Every answer comes with a receipt.</div></div>`, `${OUT}/title.png`, 1920, 1080);
await shot(`<div class="card"><div class="grid"></div><h2 style="font-size:76px">PINPOINT: blueprints that <em>show</em></h2>
  <div class="sub" style="margin-top:40px;font-size:28px">Questions answered correctly, per source</div><div class="stats" style="margin-top:22px">
   <div class="st"><b>${facts.ifc}</b><span>IFC building models</span></div>
   <div class="st"><b>${facts.swiss}</b><span>Swiss CAD floor plans</span></div>
   <div class="st"><b class="amber">${facts.cc}</b><span>CubiCasa5K raster scans</span></div>
  </div>
  <div class="cost">All ${facts.q} questions: <b>${facts.eur}</b> measured vs <s>${facts.vlm}</s> frontier VLM (est.) · <em>~${facts.ratio}× cheaper</em></div>
  <div class="sub" style="font-size:30px">Counts exact · areas within 2% · 0 LLM calls in the scored path · every answer comes with a receipt</div>
  <div class="credit">Data: Swiss Dwellings v3.0.0, Archilyse AG, CC BY 4.0 · CubiCasa5K, © 2019 CubiCasa, Kalervo et al., CC BY-NC-SA 4.0, non-commercial ·
   OpeningDesign, CC BY-SA 4.0 · IFC models: licence per file · All numbers from /api/scoreboard and /api/race</div></div>`, `${OUT}/end.png`, 1920, 1080);
await b.close();
