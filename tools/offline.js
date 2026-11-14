// PINPOINT static build: answers the app's /api/* requests from responses recorded from the real app
// (tools/build_static.py -> pp-data/). Loaded as a classic script before the app modules.
(() => {
  const M = window.__PP_OFFLINE; if (!M) return;
  const ROOT = new URL('./', document.baseURI).href;
  const realFetch = window.fetch.bind(window);
  const cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const parse = url => {
    try { const u = new URL(url, location.href); const i = u.pathname.indexOf('/api/'); return i < 0 || u.origin !== location.origin ? null : { u, p: u.pathname.slice(i) }; }
    catch (e) { return null; }
  };
  const keyOf = r => r.p + '?' + JSON.stringify([...r.u.searchParams.entries()].sort((a, b) => cmp(a[0], b[0]) || cmp(a[1], b[1])));
  const fileUrl = e => ROOT + e.f;
  const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'Content-Type': 'application/json' } });
  async function load(e) {
    const r = await realFetch(fileUrl(e));
    if (!r.ok) return json({ detail: 'static file missing: ' + e.f }, 404);
    let body = r.body;
    if (e.z) {   // .gz files are decoded here; a host that already sent them with Content-Encoding: gzip hands over plain bytes
      const buf = new Uint8Array(await r.arrayBuffer());
      body = buf[0] === 0x1f && buf[1] === 0x8b ? new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip')) : buf;
    }
    return new Response(body, { status: e.s || 200, headers: { 'Content-Type': e.t } });
  }
  const cache = new Map();
  const getJson = e => { if (!cache.has(e.f)) cache.set(e.f, load(e).then(r => r.json())); return cache.get(e.f); };
  const bundle = (kind, path) => { const e = M[kind][path] || M[kind][M.alias?.[path]]; return e ? getJson(e) : Promise.resolve(null); };
  const NOTE = 'This is the static demo: it only contains the answers PINPOINT computed for the dataset questions on these drawings. ' +
    'Click the ask box to pick one of them, or run PINPOINT locally to ask anything.';

  async function ask(body) {
    const b = JSON.parse(body || '{}'), A = await bundle('ask', b.path), q = (b.question || '').trim();
    if (A && A[q]) return A[q];
    return { value: null, unit: null, items: [], method: 'not in the static demo', steps: [NOTE], static_miss: true,
      cost: { seconds: 0, total_eur: 0, cpu_eur: 0, llm_eur: 0, llm_calls: 0, vlm_baseline_eur: 0 } };
  }
  async function walk(r) {
    const path = r.u.searchParams.get('path'), q = (r.u.searchParams.get('q') || '').trim();
    const W = await bundle('walk', path);
    if (!W) { const e = M.get[keyOf(r)]; return e ? load(e) : json({ detail: 'walkthrough not included in the static demo' }, 404); }
    const out = { ...W.base };
    if (q && W.answers[q]) out.answer = W.answers[q];
    return json(out);
  }
  // point picks: the same bounding-box rule the server uses for raster plans, point-in-polygon first for CAD sheets
  const inPoly = (x, y, P) => { let c = false; for (let i = 0, j = P.length - 1; i < P.length; j = i++) { const [xi, yi] = P[i], [xj, yj] = P[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; };
  const bbox = P => P.reduce((b, p) => [Math.min(b[0], p[0]), Math.min(b[1], p[1]), Math.max(b[2], p[0]), Math.max(b[3], p[1])], [1e12, 1e12, -1e12, -1e12]);
  async function inspect(r) {
    const sp = r.u.searchParams, path = sp.get('path'), id = sp.get('id');
    const C = await bundle('inspect', path);
    if (!C) return { none: true, why: 'Component identification for this drawing is not included in the static demo.' };
    if (id) return C[id] || { none: true, why: `No card was recorded for element ${id} in the static demo.` };
    if (sp.has('x') && sp.has('y')) {
      const x = +sp.get('x'), y = +sp.get('y'), pe = M.get[`/api/parts?${JSON.stringify([['path', path]])}`];
      const parts = pe ? await getJson(pe) : null, geo = parts?.geo || {};
      let best = null, bestA = Infinity, tol = 4;
      for (const [k, g] of Object.entries(geo)) {
        if (!g.poly?.length) continue;
        const b = bbox(g.poly), a = (b[2] - b[0]) * (b[3] - b[1]);
        const hit = parts.kind === 'swiss' ? inPoly(x, y, g.poly) || (g.kind !== 'room' && x >= b[0] - tol && x <= b[2] + tol && y >= b[1] - tol && y <= b[3] + tol)
          : x >= b[0] - tol && x <= b[2] + tol && y >= b[1] - tol && y <= b[3] + tol;
        if (hit && a < bestA && C[k]) { best = k; bestA = a; }
      }
      if (best) return C[best];
      return { none: true, why: parts?.kind === 'ifc' || !parts?.geo ? 'In the static demo only drawn model elements can be identified (printed text lookup needs the live app).' : 'No identifiable element here.' };
    }
    return { none: true, why: 'Pick the element itself: free 3D points are not resolved in the static demo.' };
  }

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const r = parse(url); if (!r) return realFetch(input, init);
    const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    try {
      if (r.p === '/api/ask' && method === 'POST') return json(await ask(init.body));
      if (r.p === '/api/inspect') return json(await inspect(r));
      if (r.p === '/api/walk') return walk(r);
      const e = M.get[keyOf(r)];
      return e ? load(e) : json({ detail: 'not included in the static demo' }, 404);
    } catch (err) { console.warn('static api', url, err); return json({ detail: String(err) }, 500); }
  };
  // <img src> and <a href> pointing at /api/... (sheets, BoQ CSV/PDF) are mapped to the recorded files
  const mapUrl = v => { if (typeof v !== 'string' || !v.includes('/api/')) return v; const r = parse(v); const e = r && M.get[keyOf(r)]; return e && !e.z ? fileUrl(e) : v; };
  for (const [C, prop] of [[HTMLImageElement, 'src'], [HTMLAnchorElement, 'href']]) {
    const d = Object.getOwnPropertyDescriptor(C.prototype, prop);
    Object.defineProperty(C.prototype, prop, { configurable: true, enumerable: d.enumerable, get: d.get, set(v) {
      // recorded BoQ exports keep the app's download name (<drawing>_BoQ.csv / .pdf)
      const m = typeof v === 'string' && v.match(/\/api\/boq\.(csv|pdf)\?/);
      if (m) { const p = parse(v)?.u.searchParams.get('path') || ''; this.setAttribute('download', p.split('/').pop().replace(/\.[^.]+$/, '') + '_BoQ.' + m[1]); }
      d.set.call(this, mapUrl(v));
    } });
  }
  const sa = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (n, v) { return sa.call(this, n, (n === 'src' || n === 'href') ? mapUrl(v) : v); };
})();
