"""PINPOINT local web server.  Run:  .venv/bin/python -m pinpoint.server   ->  http://127.0.0.1:8737"""
import os, hashlib, threading
import pymupdf
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import engine
from .engine import DATA, CACHE, ROOT

app = FastAPI(title='PINPOINT')
STATIC = os.path.join(ROOT, 'static')
_mesh_lock = threading.Lock()


def safe(path):
    from . import fullset
    for base in (DATA, fullset.FILES):
        full = os.path.realpath(os.path.join(base, path))
        if full.startswith(os.path.realpath(base) + os.sep) and os.path.exists(full):
            return full
    raise HTTPException(404, 'not found')


class Ask(BaseModel):
    path: str
    question: str


@app.get('/')
def index():
    return FileResponse(os.path.join(STATIC, 'index.html'), headers={'Cache-Control': 'no-store'})


@app.get('/api/catalog')
def catalog():
    return JSONResponse(engine.catalog())


@app.post('/api/ask')
def ask(a: Ask):
    safe(a.path)
    try:
        return JSONResponse(engine.ask(a.path, a.question.strip()))
    except Exception as e:  # never crash the demo; show the failure honestly
        import traceback; traceback.print_exc()
        return JSONResponse(dict(value=None, unit=None, items=[], method='error', steps=[f'{type(e).__name__}: {e}'],
                                 cost=dict(seconds=0, total_eur=0, cpu_eur=0, llm_eur=0, llm_calls=0, vlm_baseline_eur=0)))


@app.get('/api/scoreboard')
def scoreboard():
    import json, glob, statistics
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'data/eval/*.json'))):
        res = json.load(open(f))
        g = [r for r in res if r['correct'] is not None]
        ok = sum(bool(r['correct']) for r in g)
        vlm = sum(engine.vlm_baseline(None) for _ in res)
        out.append(dict(source=os.path.basename(f)[:-5], total=len(res), graded=len(g), correct=ok,
                        eur=sum(r['eur'] or 0 for r in res), median_ms=round(1000 * statistics.median([r['secs'] for r in res]), 1) if res else 0,
                        p95_ms=round(1000 * sorted(r['secs'] for r in res)[int(0.95 * (len(res) - 1))], 1) if res else 0,
                        llm_calls=0, vlm_eur=vlm, by_type={t: [sum(bool(r['correct']) for r in g if r['type'] == t), sum(1 for r in g if r['type'] == t)]
                                                         for t in sorted({r['type'] for r in g})}))
    return JSONResponse(out)


@app.get('/api/eval_all')
def eval_all():
    """Per-source / per-question-type accuracy: dev split vs unseen full-dataset drawings (python -m pinpoint.eval_all)."""
    import json
    f = os.path.join(ROOT, 'data/eval_all.json')
    if not os.path.exists(f):
        raise HTTPException(404, 'run python -m pinpoint.eval_all first')
    return JSONResponse(json.load(open(f)))


@app.get('/api/sheet')
def sheet(path: str = Query(...), page: int = 0):
    full = safe(path)
    if full.lower().endswith(('.png', '.jpg', '.jpeg', '.svg')):
        return FileResponse(full, headers={'Cache-Control': 'max-age=86400'})
    key = hashlib.md5(f'{full}:{page}'.encode()).hexdigest()
    out = os.path.join(CACHE, key + '.svg')
    png = os.path.join(CACHE, key + '.png')
    if os.path.exists(png):
        return FileResponse(png, media_type='image/png', headers={'Cache-Control': 'max-age=86400'})
    if not os.path.exists(out):
        pg = pymupdf.open(full)[page]
        svg = pg.get_svg_image(text_as_path=False)
        if len(svg) > 1_200_000:   # dense sheets: a 2.2x PNG is lighter for the browser than megabytes of vector paths
            pg.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2)).save(png)
            return FileResponse(png, media_type='image/png', headers={'Cache-Control': 'max-age=86400'})
        with open(out, 'w') as f:
            f.write(svg)
    return FileResponse(out, media_type='image/svg+xml', headers={'Cache-Control': 'max-age=86400'})


@app.get('/api/mesh')
def mesh(path: str = Query(...)):
    full = safe(path)
    out = os.path.join(CACHE, os.path.splitext(os.path.basename(full))[0] + '.mesh.bin')
    with _mesh_lock:
        if not os.path.exists(out):
            from .mesh import build
            build(full, out)
    return FileResponse(out, media_type='application/octet-stream', headers={'Cache-Control': 'max-age=86400'})


from .wow import router as _wow_router  # WOW track: 3D walkthrough + bill of quantities
app.include_router(_wow_router)

app.mount('/static', StaticFiles(directory=STATIC), name='static')

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8737))
    print(f'PINPOINT on http://127.0.0.1:{port}')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
