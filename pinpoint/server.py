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
    full = os.path.realpath(os.path.join(DATA, path))
    if not full.startswith(os.path.realpath(DATA) + os.sep) or not os.path.exists(full):
        raise HTTPException(404, 'not found')
    return full


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


@app.get('/api/sheet')
def sheet(path: str = Query(...), page: int = 0):
    full = safe(path)
    if full.lower().endswith(('.png', '.jpg', '.jpeg', '.svg')):
        return FileResponse(full, headers={'Cache-Control': 'max-age=86400'})
    key = hashlib.md5(f'{full}:{page}'.encode()).hexdigest()
    out = os.path.join(CACHE, key + '.svg')
    if not os.path.exists(out):
        svg = pymupdf.open(full)[page].get_svg_image(text_as_path=False)
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


app.mount('/static', StaticFiles(directory=STATIC), name='static')

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8737))
    print(f'PINPOINT on http://127.0.0.1:{port}')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
