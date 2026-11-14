// Records each app scene of the PINPOINT demo from the live app (headless Chrome, CDP screencast).
// usage: node record.mjs [sceneId ...]   (default: all app scenes). Frames -> $REC/<id>/
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { launch, BASE, sleep, placeCursor, moveTo, moveToSel, click, clickXY, typeText, startRec } from './lib.mjs';

const REC = process.env.REC || '/tmp/ppvid/rec';
const AUD = process.env.AUD || '/tmp/ppvid/audio';
const CFG = JSON.parse(fs.readFileSync(new URL('./scenes.json', import.meta.url)));
const durs = Object.fromEntries(fs.readFileSync(`${AUD}/durations.txt`, 'utf8').trim().split('\n').map(l => l.split(' ')).map(([k, v]) => [k, +v]));
const T = id => { const s = CFG.scenes.find(x => x.id === id); return Math.max(s.minT, CFG.lead + durs[id] + 1.0); };

const SW_PATH = 'data/swiss_dwellings/site1000_bldg2082_floor9385.pdf';
const IFC_PATH = 'data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-04-4-korrus.pdf';
const Q_WC = 'Wie viele WCs sind auf diesem Grundriss eingezeichnet?';
const Q_AREA = 'What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, terraces and other outdoor spaces?';
const Q_EST = 'Mitu ust on näidatud korruse „4.korrus“ plaanil?';

const { browser, page } = await launch();
const url = (p = {}) => BASE + '/?' + new URLSearchParams(p).toString();
async function open(p, wait = 3500) { await page.goto(url(p)); await page.waitForFunction(() => window.PP && PP.S.file); await sleep(wait); }
async function noSugg() { await page.addStyleTag({ content: '#sugg{display:none!important}' }); }
async function hideSplash() { await page.evaluate(() => { document.querySelector('#splash').hidden = true; }); }
async function settled() { // wait until no network for a moment and the drawing is in
  await page.waitForLoadState('networkidle').catch(() => { });
}
// step to item n but keep a readable zoom (the raster sheet is 2.2x; the default item zoom is too tight for video)
async function stepTo(n, frac = 0.10, btn = '#nextBtn') {
  await click(page, btn, { pause: 150 });
  await sleep(40);
  await page.evaluate(([n, frac]) => {
    const it = PP.SV.items.find(x => x.n === n); if (!it) return;
    const b = it.bbox, m = Math.max(PP.SV.vb[2], PP.SV.vb[3]) * frac;
    const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
    PP.fitBox([cx - m, cy - m * 0.8, cx + m, cy + m * 0.8]);
  }, [n, frac]);
}

const SCENES = {
  async s01_pain(rec, until) {
    await open({}, 3800); await placeCursor(page, 980, 900);
    rec = await rec();
    await sleep(900);
    await moveToSel(page, '#spSwiss', 1300); await sleep(1400);
    await moveToSel(page, '#spIfc', 900); await sleep(1300);
    await moveToSel(page, '#spUs', 900); await sleep(1100);
    await moveToSel(page, '#spFi', 900); await sleep(1300);
    await moveToSel(page, '#spCost', 1100); await sleep(2600);
    await moveToSel(page, '#spTry', 1200);
    return until();
  },
  async s02_count(rec, until) {
    await open({}, 2500); await hideSplash(); await page.fill('#q', ''); await settled(); await sleep(800);
    await placeCursor(page, 980, 640);
    rec = await rec();
    await sleep(500);
    await noSugg();
    await click(page, '#q', { dx: 0.3 });
    await sleep(300);
    await typeText(page, Q_WC, 26);
    await page.evaluate(() => { document.querySelector('#sugg').hidden = true; });
    await click(page, '#go');
    await sleep(3200);
    await moveToSel(page, '#aBadges .tol', 800); await sleep(1300);
    await stepTo(1); await sleep(1900);
    await stepTo(2); await sleep(1500);
    await moveToSel(page, '#receipt [data-n="2"]', 1000, 0.4); await sleep(1800);
    await click(page, '#allBtn');
    return until();
  },
  async s03_area(rec, until) {
    await open({ q: Q_WC }, 4500); await settled();
    await placeCursor(page, 1000, 560);
    rec = await rec();
    await sleep(300);
    await click(page, '#q', { dx: 0.3 });
    await page.keyboard.press('Meta+A'); await page.keyboard.press('Backspace');
    await typeText(page, 'net floor area of apartment A', 26);
    await sleep(400);
    await click(page, '#chips button:has-text("net floor area of apartment A in m²"):visible', { ms: 700 });
    await sleep(3000);
    await moveToSel(page, '#aBadges .tol', 900); await sleep(2600);
    await moveToSel(page, '#receipt .rc-check', 1000, 0.85); await sleep(1800);
    await moveToSel(page, '#receipt [data-n="1"]', 800, 0.9); await sleep(1200);
    await moveToSel(page, '#receipt [data-n="2"]', 500, 0.9); await sleep(1000);
    await moveTo(page, 960, 520, 1000);
    return until();
  },
  async s04_audit(rec, until) {
    await open({ q: Q_AREA }, 4500); await settled();
    await placeCursor(page, 1200, 300);
    rec = await rec();
    await sleep(300);
    await click(page, '#auBtn');
    await page.locator('.au-sc').waitFor({ timeout: 20000 }); await sleep(900);
    await click(page, '.au-sc');
    await page.locator('.au-sf[data-i="0"]').waitFor({ timeout: 20000 }); await sleep(1200);
    await moveToSel(page, '.au-sf[data-i="0"]', 900, 0.5, 0.25); await sleep(1600);
    await click(page, '.au-sf[data-i="0"]', { ms: 300, dx: 0.5, dy: 0.3 });
    await page.waitForFunction(() => document.querySelector('#receipt')?.textContent.includes('door schedule vs door tags'), null, { timeout: 25000 });
    await sleep(1500);
    await moveToSel(page, '#receipt :text("door schedule vs door tags")', 1000); await sleep(2400);
    await moveTo(page, 830, 650, 900); await sleep(1800);
    return until();
  },
  async s05_bim(rec, until) {
    await open({ path: IFC_PATH }, 2000); await hideSplash();
    await page.evaluate(() => { PP.S.userMode = 'split'; });
    await page.fill('#q', ''); await settled(); await sleep(4000);
    await placeCursor(page, 1000, 600);
    rec = await rec();
    await sleep(300);
    await noSugg();
    await click(page, '#q', { dx: 0.3 });
    await typeText(page, Q_EST, 26);
    await page.evaluate(() => { document.querySelector('#sugg').hidden = true; });
    await click(page, '#go');
    await sleep(3400);
    await click(page, '#receipt [data-n="3"]', { ms: 1000, dx: 0.3 });
    await sleep(2500);
    await moveTo(page, 1170, 600, 1100); await sleep(1500);
    return until();
  },
  async s06_walk(rec, until) {
    await open({ q: Q_WC }, 4000); await settled();
    await placeCursor(page, 1100, 300);
    rec = await rec();
    await sleep(300);
    await click(page, '#wowWalk');
    await page.locator('#wkSeg').waitFor({ timeout: 20000 }); await sleep(2000);
    await moveTo(page, 900, 420, 1200); await sleep(900);
    await moveTo(page, 1250, 640, 1200); await sleep(1300);
    await click(page, '#wkSeg button[data-v="walk"]', { ms: 900 });
    await sleep(3000);
    return until();
  },
  async s07_boq(rec, until) {
    await open({ q: Q_AREA }, 4500); await settled();
    await placeCursor(page, 1200, 300);
    rec = await rec();
    await sleep(300);
    await click(page, '#wowBoq');
    await page.locator('#bqX').waitFor({ timeout: 20000 }); await sleep(2200);
    await moveTo(page, 1300, 196, 1000); await sleep(1800);
    await moveTo(page, 1320, 45, 800); await sleep(1500);
    await moveToSel(page, '#bqX >> xpath=preceding-sibling::*[1]', 900).catch(() => moveTo(page, 1820, 46, 900)); await sleep(800);
    await moveTo(page, 1742, 46, 600); await sleep(1500);
    return until();
  },
  async s08_race(rec, until) {
    await open({ q: Q_WC }, 4500); await settled();
    await placeCursor(page, 1100, 500);
    rec = await rec();
    await sleep(300);
    await click(page, '#meter', { ms: 1100 });
    await sleep(4200);
    await moveTo(page, 1430, 190, 1000); await sleep(2200);
    await moveTo(page, 1430, 340, 800); await sleep(2600);
    await moveTo(page, 840, 530, 1000); await sleep(2600);
    // scroll so the estimate footnote is fully on screen
    await page.mouse.wheel(0, 200); await sleep(600);
    await moveTo(page, 1460, 800, 1000); await sleep(1500);
    return until();
  },
  async s09_scores(rec, until) {
    await open({ q: Q_WC }, 4500); await settled();
    await placeCursor(page, 1500, 300);
    rec = await rec();
    await sleep(300);
    await click(page, '#sbBtn', { ms: 1000 });
    await sleep(1600);
    await moveTo(page, 1110, 400, 900); await sleep(1500);
    await moveTo(page, 1110, 480, 600); await sleep(1300);
    await moveTo(page, 1110, 640, 700); await sleep(1500);
    await moveTo(page, 1250, 640, 600); await sleep(1500);
    return until();
  },
};

const want = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCENES);
const report = {};
for (const id of want) {
  const dir = `${REC}/${id}`;
  let r, t0;
  const rec = async () => { r = await startRec(page, dir); t0 = Date.now(); return r; };
  const until = async () => { const left = T(id) + 0.4 - (Date.now() - t0) / 1000; if (left > 0) await sleep(left * 1000); return (Date.now() - t0) / 1000; };
  try {
    const used = await SCENES[id](rec, until);
    const info = await r.stop();
    report[id] = { ...info, target: T(id), used: +used.toFixed(2), over: used > T(id) + 0.45 };
    console.log(id, JSON.stringify(report[id]));
    execFileSync(new URL('./raw2mp4.sh', import.meta.url).pathname, [id], { stdio: 'inherit' });
  } catch (e) {
    console.log(id, 'FAILED', String(e).slice(0, 300));
    if (r) await r.stop();
    report[id] = { failed: String(e).slice(0, 300) };
  }
}
fs.writeFileSync(`${REC}/report-${Date.now()}.json`, JSON.stringify(report, null, 1));
await browser.close();
