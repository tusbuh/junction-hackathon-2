"""WOW-track endpoints: 3D walkthrough geometry and the instant bill of quantities. Mounted by server.py."""
import os, json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from . import engine

router = APIRouter()


def _num(o):
    """numpy scalars -> plain JSON numbers."""
    import numpy as np
    if isinstance(o, dict):
        return {k: _num(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_num(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


def credit(path):
    """Licence + credit line for a dataset file, read from data/<source>/LICENSE.md (table row, else 'All files:')."""
    src = engine.source_of(path)
    lic = os.path.join(engine.DATA, 'data', src, 'LICENSE.md')
    name = os.path.basename(path)
    rel = path.split(f'{src}/', 1)[1] if f'{src}/' in path else name   # opening_design keys rows by sub-path
    if not os.path.exists(lic):
        return dict(licence=None, credit=f'Stoa Junction 2026 dataset · {src}')
    txt = open(lic, encoding='utf-8').read()
    for line in txt.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) >= 4 and cells[0] in (name, rel):
            return dict(licence=cells[2], credit=cells[3])
    for line in txt.splitlines():
        if line.startswith('All files:'):
            m = line.split('Credit:', 1)
            lic_id = line.split(':', 1)[1].split('Credit:')[0].strip().rstrip('.')
            return dict(licence=lic_id, credit=(m[1] if len(m) > 1 else line).strip())
    return dict(licence=None, credit=f'Stoa Junction 2026 dataset · {src} (see LICENSE.md)')


@router.get('/api/credit')
def credit_api(path: str = Query(...)):
    return JSONResponse(credit(path))


def _stem(path):
    if engine.source_of(path) != 'swiss_dwellings':
        return None
    return os.path.splitext(os.path.basename(path))[0]


@router.get('/api/walk')
def walk(path: str = Query(...), q: str = ''):
    from .server import safe
    safe(path)
    stem = _stem(path)
    if stem:
        from . import walk as W
        out = dict(W.build(stem))
        out['credit'] = credit(path)
        if q.strip():
            out['answer'] = W.answer_items(stem, q.strip())
        return JSONResponse(_num(out))
    if engine.source_of(path) in ('ifc_models', 'ifc_bench') or path.endswith('.ifc'):
        from urllib.parse import quote
        ifc = engine.ifc_for(path)
        if not os.path.exists(engine.abspath(ifc)):
            raise HTTPException(404, 'IFC model not in this split')
        return JSONResponse(dict(kind='ifc', model=ifc, mesh=f'/api/mesh_local?path={quote(ifc)}', credit=credit(ifc)))
    raise HTTPException(400, 'walkthrough needs vector geometry (Swiss DXF or IFC)')


@router.get('/api/boq')
def boq(path: str = Query(...)):
    from .server import safe
    safe(path)
    from . import boq as B
    out = _num(B.build(path))
    if out.get('kind') != 'none':
        B.warm(path)
    return JSONResponse(out)


@router.get('/api/boq_verify')
def boq_verify(path: str = Query(...)):
    from .server import safe
    safe(path)
    from . import boq as B
    return JSONResponse(B.verify(path))


@router.get('/api/boq.csv')
def boq_csv(path: str = Query(...)):
    from fastapi.responses import Response
    from .server import safe
    safe(path)
    from . import boq as B
    name = os.path.splitext(os.path.basename(path))[0]
    return Response(B.to_csv(_num(B.build(path)), path), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{name}_BoQ.csv"'})


@router.get('/api/boq.pdf')
def boq_pdf(path: str = Query(...)):
    from fastapi.responses import Response
    from .server import safe
    safe(path)
    from . import boq as B
    name = os.path.splitext(os.path.basename(path))[0]
    return Response(B.to_pdf(_num(B.build(path)), path), media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{name}_BoQ.pdf"'})


_mesh_lock = __import__('threading').Lock()


@router.get('/api/mesh_local')
def mesh_local(path: str = Query(...)):
    """IFC tessellation re-centred on a float64 origin (georeferenced models lose ~0.5 m to float32 otherwise)."""
    from fastapi.responses import FileResponse
    from .server import safe
    full = safe(path)
    out = os.path.join(engine.CACHE, os.path.splitext(os.path.basename(full))[0] + '.local.mesh.bin')
    with _mesh_lock:
        if not os.path.exists(out):
            from .mesh import build
            build(full, out + '.tmp', local=True)
            os.replace(out + '.tmp', out)
    return FileResponse(out, media_type='application/octet-stream', headers={'Cache-Control': 'max-age=86400'})
