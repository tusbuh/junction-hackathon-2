// PINPOINT demo-video helpers: headless Chrome (installed Google Chrome via playwright-core), drawn cursor, CDP screencast.
import fs from 'node:fs';
const PW = process.env.PW_CORE || '/Users/hubertusfinckenberg/ANKKU-Game/node_modules/playwright-core/index.mjs';
const { chromium } = await import(PW);
export const BASE = process.env.PP_BASE || 'http://localhost:8737';
export const W = 1920, H = +(process.env.PP_H || 960);
export const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function launch() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true,
    args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--hide-scrollbars', '--font-render-hinting=none'] });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error') console.log('[page error]', m.text().slice(0, 200)); });
  page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 200)));
  await ctx.addInitScript(CURSOR_JS);
  return { browser, ctx, page };
}

// a drawn macOS-style arrow cursor + click ripple; positions are driven from Node with eased motion
const CURSOR_JS = `
(() => {
  const mk = () => {
    if (document.getElementById('vcur') || !document.body) return;
    const st = document.createElement('style');
    st.textContent = '#vcur{position:fixed;left:0;top:0;width:34px;height:34px;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.55))}' +
      '.vrip{position:fixed;z-index:2147483646;pointer-events:none;width:46px;height:46px;margin:-23px 0 0 -23px;border-radius:50%;border:3px solid #ffb02e;background:rgba(255,176,46,.25);animation:vrip .6s ease-out forwards}' +
      '@keyframes vrip{from{transform:scale(.3);opacity:1}to{transform:scale(1.5);opacity:0}}';
    document.head.append(st);
    const c = document.createElement('div'); c.id = 'vcur';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M3 2 L3 19.5 L7.6 15.4 L10.6 22 L13.6 20.7 L10.7 14.2 L16.8 14.2 Z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.append(c);
    window.__cur = { x: -100, y: -100 };
    window.__setCur = (x, y) => { window.__cur = { x, y }; c.style.transform = 'translate(' + (x - 4) + 'px,' + (y - 3) + 'px)'; };
    window.__ripple = (x, y) => { const r = document.createElement('div'); r.className = 'vrip'; r.style.left = x + 'px'; r.style.top = y + 'px'; document.body.append(r); setTimeout(() => r.remove(), 700); };
    if (window.__startCur) window.__setCur(...window.__startCur);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
})();`;

let CUR = { x: 960, y: 600 };
export function setStart(x, y) { CUR = { x, y }; }
export async function placeCursor(page, x = CUR.x, y = CUR.y) {
  CUR = { x, y };
  await page.evaluate(([x, y]) => { window.__startCur = [x, y]; window.__setCur?.(x, y); }, [x, y]);
  await page.mouse.move(x, y);
}
// eased move: animate inside the page (smooth at screencast rate), mouse follows at the end (hover states)
export async function moveTo(page, x, y, ms) {
  const d = Math.hypot(x - CUR.x, y - CUR.y);
  ms = ms ?? Math.min(1300, Math.max(450, 300 + d * 0.9));
  await page.evaluate(([x0, y0, x1, y1, ms]) => new Promise(res => {
    const t0 = performance.now();
    const cx = (x0 + x1) / 2 + (y1 - y0) * 0.08, cy = (y0 + y1) / 2 - (x1 - x0) * 0.08;   // a gentle arc
    (function f(now) {
      const t = Math.min(1, (now - t0) / ms), e = t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      const x = (1 - e) * (1 - e) * x0 + 2 * (1 - e) * e * cx + e * e * x1, y = (1 - e) * (1 - e) * y0 + 2 * (1 - e) * e * cy + e * e * y1;
      window.__setCur(x, y);
      if (t < 1) requestAnimationFrame(f); else res();
    })(t0);
  }), [CUR.x, CUR.y, x, y, ms]);
  CUR = { x, y };
  await page.mouse.move(x, y, { steps: 4 });
}
export async function box(page, sel) {
  const l = page.locator(sel).first();
  await l.waitFor({ state: 'visible', timeout: 20000 });
  const b = await l.boundingBox();
  return b;
}
export async function moveToSel(page, sel, ms, dx = 0.5, dy = 0.5) {
  const b = await box(page, sel);
  await moveTo(page, b.x + b.width * dx, b.y + b.height * dy, ms);
  return b;
}
export async function click(page, sel, { ms, pause = 220, dx, dy } = {}) {
  if (sel) await moveToSel(page, sel, ms, dx, dy);
  await sleep(pause);
  await page.evaluate(([x, y]) => window.__ripple(x, y), [CUR.x, CUR.y]);
  await page.mouse.click(CUR.x, CUR.y);
}
export async function clickXY(page, x, y, opts = {}) { await moveTo(page, x, y, opts.ms); await sleep(opts.pause ?? 220); await page.evaluate(([x, y]) => window.__ripple(x, y), [x, y]); await page.mouse.click(x, y); }
export async function typeText(page, text, cps = 22) {
  for (const ch of text) { await page.keyboard.type(ch); await sleep(1000 / cps * (0.6 + Math.random() * 0.8)); }
}

// ---- CDP screencast recorder: jpeg frames + timestamps -> later resampled to constant 30 fps by ffmpeg
export async function startRec(page, dir) {
  fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  let n = 0, stopped = false;
  cdp.on('Page.screencastFrame', async f => {
    if (stopped) return;
    const file = `${dir}/f${String(n++).padStart(6, '0')}.jpg`;
    fs.writeFileSync(file, Buffer.from(f.data, 'base64'));
    frames.push({ file, t: f.metadata.timestamp });
    try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch { }
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 88, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  const t0 = Date.now() / 1000;
  return {
    t0,
    async stop() {
      await sleep(150);
      await cdp.send('Page.stopScreencast');
      stopped = true;
      const t1 = Date.now() / 1000;
      // concat list: each frame lasts until the next one; the last until stop
      let s = 'ffconcat version 1.0\n';
      frames.forEach((f, i) => {
        const next = i + 1 < frames.length ? frames[i + 1].t : Math.max(f.t + 1 / 30, t1);
        s += `file '${f.file}'\nduration ${Math.max(0.001, next - f.t).toFixed(4)}\n`;
      });
      if (frames.length) s += `file '${frames[frames.length - 1].file}'\n`;
      fs.writeFileSync(`${dir}/list.txt`, s);
      return { frames: frames.length, start: frames[0]?.t, secs: t1 - (frames[0]?.t ?? t1) };
    },
  };
}
