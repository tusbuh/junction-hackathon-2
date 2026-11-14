"""2D -> 3D: extrude a Swiss Dwellings DXF floor plan into a walkable building model.

Everything comes from the DXF layers (metres): WALL polygons are extruded to storey height, WINDOW frames become
sill + glazing + lintel in the wall gap, DOOR threshold lines become openings with a lintel, the drawn DOOR leaf
becomes a panel, ROOM_OUTLINE polygons become floor finishes and FIXTURE symbols become sanitary objects.
Nothing is invented: heights are the only assumption and they are reported as such (``assumed``).
"""
import functools, math
import numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union

# Typical Swiss residential section (SIA 500-ish clear heights); shown in the UI as assumptions, not data.
H = dict(storey=2.60, door=2.10, sill=0.90, head=2.10, slab=0.22)


def _pts(e):
    return [(float(p[0]), float(p[1])) for p in e.get_points()]


def _coords(poly):
    return [[round(x, 3), round(y, 3)] for x, y in poly.exterior.coords][:-1]


def _jamb_depth(U, p, d, n):
    """Wall extent (along normal n) at the jamb next to point p (d points out of the opening into the wall)."""
    q = Point(p[0] + d[0] * 0.03, p[1] + d[1] * 0.03)
    out = []
    for s in (1, -1):
        t = 0.0
        while t < 0.8 and U.contains(Point(q.x + s * n[0] * (t + 0.01), q.y + s * n[1] * (t + 0.01))):
            t += 0.01
        out.append(t)
    return out


@functools.lru_cache(maxsize=32)
def build(stem):
    from .engine import swiss_plan
    plan = swiss_plan(stem)
    msp = plan.msp
    walls = [Polygon(_pts(e)).buffer(0) for e in msp.query('LWPOLYLINE[layer=="WALL"]') if e.closed and len(e) >= 3]
    U = unary_union([w for w in walls if not w.is_empty])
    wall_polys = []
    for g in getattr(U, 'geoms', [U]):
        if g.geom_type == 'Polygon' and g.area > 1e-4:
            wall_polys.append(dict(outer=_coords(g), holes=[[[round(x, 3), round(y, 3)] for x, y in r.coords][:-1] for r in g.interiors]))

    # door openings: threshold line (2-vertex DOOR polyline) -> gap rectangle spanning the wall thickness
    doors = []
    leaves = [Polygon(_pts(e)) for e in msp.query('LWPOLYLINE[layer=="DOOR"]') if len(e) == 5]
    for e in msp.query('LWPOLYLINE[layer=="DOOR"]'):
        if len(e) != 2:
            continue
        (x1, y1), (x2, y2) = _pts(e)
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 0.3:
            continue
        d = ((x2 - x1) / L, (y2 - y1) / L)
        n = (-d[1], d[0])
        a = _jamb_depth(U, (x1, y1), (-d[0], -d[1]), n)
        b = _jamb_depth(U, (x2, y2), d, n)
        fwd, back = max(a[0], b[0], 0.08), max(a[1], b[1], 0.0)
        rect = [[x1 + n[0] * fwd, y1 + n[1] * fwd], [x2 + n[0] * fwd, y2 + n[1] * fwd],
                [x2 - n[0] * back, y2 - n[1] * back], [x1 - n[0] * back, y1 - n[1] * back]]
        th = LineString([(x1, y1), (x2, y2)])
        leaf = min(leaves, key=lambda p: p.distance(th)) if leaves else None
        doors.append(dict(gap=[[round(v, 3) for v in p] for p in rect], width=round(L, 2),
                          leaf=_coords(leaf) if leaf is not None and leaf.distance(th) < 0.15 else None,
                          bbox=[round(v, 3) for v in (min(x1, x2) - 0.05, min(y1, y2) - 0.05, max(x1, x2) + 0.05, max(y1, y2) + 0.05)]))

    windows = []
    for e in msp.query('LWPOLYLINE[layer=="WINDOW"]'):
        if len(e) == 4 and e.closed:
            p = Polygon(_pts(e))
            bx = p.bounds
            windows.append(dict(poly=_coords(p), width=round(max(bx[2] - bx[0], bx[3] - bx[1]), 2), bbox=[round(v, 3) for v in bx]))

    rooms = []
    for r in plan.rooms:
        if not r['poly']:
            continue
        rooms.append(dict(num=r['num'], name=r['name'], unit=r['unit'], area=r['area'], printed=r['printed'],
                          poly=[[round(x, 3), round(y, 3)] for x, y in r['poly']][:-1],
                          holes=[[[round(x, 3), round(y, 3)] for x, y in h][:-1] for h in (r.get('holes') or [])],
                          outdoor=(r['name'] or '').lower() in {'balcon', 'balcone', 'balkon', 'loggia', 'terrasse', 'terrazza'},
                          shaft=bool(r.get('shaft'))))
    fx = []
    for kind, lst in (('WC', plan.wc), ('washbasin', plan.basin), ('bathtub', plan.tub), ('shower', plan.shower)):
        for b in lst:
            fx.append(dict(kind=kind, bbox=[round(v, 3) for v in b]))
    xs = [p[0] for w in wall_polys for p in w['outer']]
    ys = [p[1] for w in wall_polys for p in w['outer']]
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 1, 1]
    # spawn point: centroid of the largest indoor room (usually the living room)
    indoor = [r for r in rooms if not r['outdoor'] and not r['shaft']]
    import re
    living = [r for r in indoor if re.search(r'wohn|séjour|sejour|soggiorno|living|salon', r['name'] or '', re.I)]
    habitable = [r for r in indoor if not re.search(r'reduit|réduit|treppe|escalier|scala|korridor|flur|corridoio|couloir|lift|keller|cave|abstell|ripostiglio|disimpegno', r['name'] or '', re.I)]
    big = max(living or habitable or indoor, key=lambda r: r['area'] or 0) if indoor else None
    spawn = list(Polygon(big['poly']).representative_point().coords[0]) if big else [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    # the printed sheet, placed under the model: invert the DXF->PDF affine fit (same fit the 2D view uses)
    sheet = None
    try:
        from .engine import swiss_fit
        A, err, n, (w, h) = swiss_fit(stem)
        M = np.array([[A[0, 0], A[1, 0]], [A[0, 1], A[1, 1]]])
        Mi = np.linalg.inv(M)
        inv = lambda u, v: (Mi @ (np.array([u, v]) - A[2])).round(3).tolist()
        sheet = dict(url=f'/api/sheet?path=data/swiss_dwellings/{stem}.png', corners=[inv(0, 0), inv(w, 0), inv(w, h), inv(0, h)],
                     fit_err_pt=round(err, 2), fit_n=n)
    except Exception:
        pass
    return dict(kind='swiss', stem=stem, heights=H, sheet=sheet, walls=wall_polys, doors=doors, windows=windows, rooms=rooms,
                fixtures=fx, bbox=bbox, spawn=spawn,
                stats=dict(walls=len(wall_polys), doors=len(doors), windows=len(windows), rooms=len(rooms), fixtures=len(fx)))


def answer_items(stem, q):
    """Answer the question with the same engine as /api/ask but keep evidence in DXF metres for the 3D scene."""
    from .engine import swiss_plan, _reroute
    from .router import canonical_swiss
    plan = swiss_plan(stem)
    r = _reroute(plan.answer(q), q, canonical_swiss, plan.answer, 'floor plan')
    for i, it in enumerate(r['items']):
        it['n'] = i + 1
    return dict(value=r['value'], unit=r['unit'], method=r['method'], items=r['items'])
