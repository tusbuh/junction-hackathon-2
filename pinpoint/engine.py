"""PINPOINT dispatcher: path + question -> answer with a receipt (evidence mapped to the drawing, steps, cost)."""
import os, re, json, time, functools, threading
import numpy as np
from urllib.parse import quote
import pymupdf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.environ.get('PINPOINT_DATA', os.path.join(ROOT, 'data/preview/junction-dataset-preview'))
CACHE = os.path.join(ROOT, 'data/cache')
os.makedirs(CACHE, exist_ok=True)

# --- cost model (shown in the UI meter; all numbers are explicit estimates) ---
CPU_EUR_PER_SEC = 0.04 / 3600          # ~€0.04 per vCPU-hour on commodity cloud
VLM_EUR_PER_MTOK_IN, VLM_EUR_PER_MTOK_OUT = 2.8, 14.0   # frontier VLM list price class (≈$3/$15 per Mtok)

_lock = threading.Lock()


def abspath(p):
    return os.path.join(DATA, p)


@functools.lru_cache(maxsize=None)
def questions():
    out = []
    with open(os.path.join(DATA, 'questions.jsonl')) as f:
        for l in f:
            out.append(json.loads(l))
    return out


def source_of(path):
    return path.split('/')[1] if path.startswith('data/') else path.split('/')[0]


# ---------------------------------------------------------------- Swiss (DXF geometry -> PDF page)
@functools.lru_cache(maxsize=64)
def swiss_plan(stem):
    from .swiss import Plan
    return Plan(abspath(f'data/swiss_dwellings/{stem}.dxf'))


@functools.lru_cache(maxsize=64)
def swiss_fit(stem):
    """Affine DXF(m) -> PDF(pt) fitted on room numbers printed in both files."""
    from .swiss import NUM_RE
    plan = swiss_plan(stem)
    page = pymupdf.open(abspath(f'data/swiss_dwellings/{stem}.pdf'))[0]
    words = {w[4]: ((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in page.get_text('words') if NUM_RE.match(w[4])}
    src, dst = [], []
    for t, x, y, b in plan.texts:
        if t in words:
            src.append(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, 1)); dst.append(words[t])
    A, *_ = np.linalg.lstsq(np.array(src), np.array(dst), rcond=None)
    err = float(np.abs(np.array(src) @ A - np.array(dst)).max())
    return A, err, len(src), (page.rect.width, page.rect.height)


def _map_items(items, A):
    T = lambda x, y: (np.array([x, y, 1.0]) @ A).tolist()
    out = []
    for it in items:
        it = dict(it)
        b = it.get('bbox')
        if b:
            p1, p2 = T(b[0], b[1]), T(b[2], b[3])
            it['bbox'] = [min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])]
        if it.get('poly'):
            it['poly'] = [[round(v, 2) for v in T(x, y)] for x, y in it['poly']]
        if it.get('holes'):
            it['holes'] = [[[round(v, 2) for v in T(x, y)] for x, y in h] for h in it['holes']]
        out.append(it)
    return out


def _reroute(r, q, canon, answer_fn, kind):
    """Primary rules failed -> lexicon canonical form -> optional tiny-LLM canonical form."""
    if r['method'] != 'not routed':
        return r
    from .router import llm_canonical
    c = canon(q)
    if c:
        r2 = answer_fn(c)
        if r2['method'] != 'not routed':
            r2['router'] = 'lexicon'
            r2['steps'].insert(0, f"Router: multilingual lexicon mapped the question to “{c}” (0 LLM calls)")
            return r2
    c, eur = llm_canonical(q, kind)
    if c:
        r2 = answer_fn(c)
        r2['router'] = 'tiny LLM (template only)'
        r2['llm_calls'] = 1; r2['llm_eur'] = eur
        r2['steps'].insert(0, f"Router: small LLM rewrote the question as “{c}” — it never sees the drawing or gives the answer")
        return r2
    return r


def ask_swiss(path, q):
    from .router import canonical_swiss
    stem = os.path.splitext(os.path.basename(path))[0]
    plan = swiss_plan(stem)
    r = _reroute(plan.answer(q), q, canonical_swiss, plan.answer, 'floor plan')
    A, err, n, (w, h) = swiss_fit(stem)
    r['items'] = _map_items(r['items'], A)
    r['excluded'] = _map_items(r.get('excluded') or [], A)
    r['steps'].append(f"Projected DXF geometry onto the PDF sheet with an affine fit on {n} shared room labels (max error {err:.2f} pt)")
    r['view'] = dict(kind='sheet', url=f'/api/sheet?path=data/swiss_dwellings/{stem}.pdf', w=w, h=h)
    r['inputs'] = [f'{stem}.dxf (geometry)', f'{stem}.pdf (sheet)']
    return r


# ---------------------------------------------------------------- IFC (ifcopenshell -> 3D)
@functools.lru_cache(maxsize=6)
def ifc_model(ifc_rel):
    from .ifcq import Model
    return Model(abspath(ifc_rel))


def ifc_for(path):
    if path.endswith('.ifc'):
        return path
    return re.sub(r'_plan-.*$', '', path.rsplit('.', 1)[0]) + '.ifc'


def plan_view(path, storey=None):
    """The IfcOpenShell-rendered plan SVG for this model (elements carry data-guid), preferring the asked storey."""
    base = ifc_for(path)[:-4]
    d = os.path.dirname(abspath(base))
    stem = os.path.basename(base)
    if path.endswith('.svg'):
        return dict(url=f'/api/sheet?path={quote(path)}', inline=True)
    cands = sorted(f for f in os.listdir(d) if f.startswith(stem + '_plan-') and f.endswith('.svg')) if os.path.isdir(d) else []
    if path.endswith('.pdf') and os.path.exists(abspath(path[:-4] + '.svg')):
        cands = [os.path.basename(path[:-4] + '.svg')] + cands
    if storey:
        norm = lambda x: re.sub(r'[^0-9a-zæøåäöüõ]', '', x.lower())
        m = [c for c in cands if norm(storey) and norm(storey) in norm(c.split('_plan-')[1])]
        cands = m + cands
    if not cands:
        return None
    rel = os.path.relpath(os.path.join(d, cands[0]), DATA)
    return dict(url=f'/api/sheet?path={quote(rel)}', inline=True, name=cands[0])


def ask_ifc(path, q):
    ifc = ifc_for(path)
    if not os.path.exists(abspath(ifc)):
        return dict(value=None, unit=None, items=[], method='model not in dataset', steps=[f'{ifc} is not in this dataset split'])
    with _lock:
        from .router import canonical_ifc
        m = ifc_model(ifc)
        if source_of(path) == 'ifc_bench':
            from .ifctext import answer as text_answer
            r = text_answer(m, q)
        else:
            r = _reroute(m.answer(q), q, lambda x: canonical_ifc(x, set(m.storeys)), m.answer, 'BIM model')
            if r['method'] == 'not routed':
                from .ifctext import answer as text_answer
                r = text_answer(m, q)
        r['storey'] = getattr(m, 'last_storey', None) if r.get('unit') != 'text' else None
    r['model'] = ifc
    r['view'] = dict(kind='model', mesh=f'/api/mesh?path={quote(ifc)}')
    pv = plan_view(path, r.get('storey'))
    try:
        with _lock:
            norm = lambda x: re.sub(r'[^0-9a-zæøåäöüõ]', '', (x or '').lower())
            same = pv and pv.get('name') and r.get('storey') and norm(r['storey']) and norm(r['storey']) in norm(pv['name'].split('_plan-')[-1])
            svg = abspath(os.path.join(os.path.dirname(ifc), pv['name'])) if same else None
            r['xchecks'] = (r.get('xchecks') or []) + m.xchecks(r, svg)
    except Exception as ex:
        r['steps'].append(f'Cross-checks skipped: {type(ex).__name__}')
    if pv:
        r['view']['sheet'] = pv
        r['steps'].append(f"Linked 2D plan {pv['name'] if 'name' in pv else ''}: plan elements carry IFC GlobalIds, so the same items light up in 2D and 3D")
    r['inputs'] = [os.path.basename(ifc)]
    return r


# ---------------------------------------------------------------- raster plans (CubiCasa-style PNG)
def ask_raster(path, q):
    from PIL import Image
    w, h = Image.open(abspath(path)).size
    view = dict(kind='sheet', url=f'/api/sheet?path={quote(path)}', w=w, h=h, raster=True)
    try:
        from .raster import qa
    except Exception as e:
        return dict(value=None, unit=None, items=[], method='raster detector not available', steps=[f'Raster adapter not loaded: {e}'], view=view)
    r = qa.answer(abspath(path), q)
    r['view'] = view
    return r


# ---------------------------------------------------------------- dispatcher
def ask(path, q):
    t = time.perf_counter()
    src = source_of(path)
    if src == 'swiss_dwellings':
        r = ask_swiss(path, q)
    elif src in ('ifc_models', 'ifc_bench') or path.endswith('.ifc'):
        r = ask_ifc(path, q)
    elif path.lower().endswith('.pdf'):
        from . import schedule
        r = schedule.answer(abspath(path), q)
        r['view'] = schedule.view(abspath(path), path)
    elif source_of(path) == 'cubicasa5k':
        r = ask_raster(path, q)
    else:
        r = dict(value=None, unit=None, items=[], method='unsupported source', steps=[f'No adapter for {src} yet'])
    dt = time.perf_counter() - t
    for i, it in enumerate(r['items']):
        it['n'] = i + 1
    r['router'] = r.get('router', 'rules')
    llm_eur = r.get('llm_eur', 0.0)
    r['cost'] = dict(seconds=round(dt, 4), cpu_eur=dt * CPU_EUR_PER_SEC, llm_eur=llm_eur,
                     total_eur=dt * CPU_EUR_PER_SEC + llm_eur, llm_calls=r.get('llm_calls', 0),
                     vlm_baseline_eur=vlm_baseline(r.get('view')))
    from .cite import finalize
    finalize(r, path, DATA)
    gt = next((x for x in questions() if x['path'] == path and x['question'] == q), None)
    if gt is not None:
        r['truth'] = gt['answer']
        r['correct'] = grade(r['value'], gt)
    return r


def vlm_baseline(view):
    """What sending this sheet to a frontier VLM would cost: ~1.6k image tokens per 1.15 MP tile at a
    resolution where small symbols are legible (200 dpi), plus prompt and answer tokens."""
    v = (view or {})
    v = v if 'w' in v else (v.get('sheet') or {})
    if not v.get('w'):
        px = 4e6          # plan rendering / model screenshots: ~4 MP
    elif v.get('raster'):
        px = v['w'] * v['h']
    else:
        px = (v['w'] * 200 / 72) * (v['h'] * 200 / 72)
    toks = max(1, px / 1.15e6) * 1600 + 300
    return toks / 1e6 * VLM_EUR_PER_MTOK_IN + 400 / 1e6 * VLM_EUR_PER_MTOK_OUT


def grade(v, gt):
    a = gt['answer']
    if v is None: return False
    if gt['type'] == 'count':
        return v == a
    if gt['type'] in ('area', 'length', 'volume'):
        try: return abs(float(v) - float(a)) <= 0.02 * abs(float(a)) + 1e-9
        except Exception: return False
    return None   # free-text: not auto-graded


def catalog():
    """Drawings that have questions, grouped by source, with their example questions."""
    by = {}
    for q in questions():
        by.setdefault(q['path'], []).append(q)
    out = []
    for p, qs in by.items():
        pv = plan_view(p) if source_of(p) == 'ifc_models' else None
        out.append(dict(path=p, source=source_of(p), name=os.path.basename(p), n=len(qs), plan=pv,
                        questions=[dict(q=x['question'], a=x['answer'], type=x['type']) for x in qs]))
    return out
