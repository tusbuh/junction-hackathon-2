"""Component identification: click any element -> what it is, its type, size, properties and the exact source.

Two calls, both read-only over data the app already loads:
  parts(path)        -> "this drawing contains": categories -> types -> element ids, plus 2D geometry to light them up
  inspect(path, ...) -> one inspector card for an element id, a sheet point (PDF pt / image px) or a DXF point (metres)

Swiss Dwellings: every element is a DXF entity (layer + handle); sizes are measured on its geometry in metres.
IFC: every element is an IfcProduct (GlobalId + STEP #id); sizes come from IFC attributes / Qto sets, properties from Psets.
Vector PDF sheets / raster scans: the printed text or detected symbol under the click, honestly labelled as such.
Nothing is estimated silently: derived values say how they were derived; values the source lacks are listed as missing.
"""
import functools, math, os, re, collections
import numpy as np
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from shapely.prepared import prep

from . import engine


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def _m(x):
    return f'{x:.2f} m'


def _cm(x):
    return f'{round(x * 100)} cm'


# ---------------------------------------------------------------- room-name vocabulary (Swiss plans: DE/FR/IT/EN)
ROOM_TERMS = [   # regex on the printed room name -> (English term, SIA 416 use class)
    (r'wohn|séjour|sejour|soggiorno|living|salon', 'living room', 'HNF · main usable area'),
    (r'ess|manger|pranzo|dining', 'dining room', 'HNF · main usable area'),
    (r'küche|kueche|cuisine|cucina|kitchen', 'kitchen', 'HNF · main usable area'),
    (r'schlaf|zimmer|chambre|camera|stanza|bedroom|room', 'room / bedroom', 'HNF · main usable area'),
    (r'bad|bain|bagno|dusche|douche|doccia|bath|shower', 'bathroom', 'NNF · ancillary area'),
    (r'^wc|w\.c\.|toilet', 'WC', 'NNF · ancillary area'),
    (r'reduit|réduit|abstell|ripostiglio|dépôt|depot|storage', 'storage room (réduit)', 'NNF · ancillary area'),
    (r'keller|cave|cantina', 'cellar', 'NNF · ancillary area'),
    (r'wasch|buanderie|lavanderia|laundry', 'laundry', 'NNF · ancillary area'),
    (r'korridor|flur|gang|entrée|entree|couloir|corridoio|disimpegno|hall|eingang|ingresso', 'corridor / hall', 'VF · circulation area'),
    (r'treppe|escalier|scala|stair', 'stairwell', 'VF · circulation area'),
    (r'lift|ascenseur|ascensore|elevator', 'lift shaft', 'FF · services area'),
    (r'balkon|balcon|loggia|terrass|terrazza|sitzplatz', 'balcony / loggia / terrace', 'AGF · exterior floor area (not NFA)'),
]


def room_term(name):
    for rx, term, cls in ROOM_TERMS:
        if name and re.search(rx, name, re.I):
            return term, cls
    return None, None


FIX_RULE = {
    'WC': 'FIXTURE layer: 48-vertex bowl outline with no drain circle inside (WC pan)',
    'washbasin': 'FIXTURE layer: 48-vertex bowl outline with a drain circle inside (washbasin)',
    'bathtub': 'FIXTURE layer: 69-vertex tub outline',
    'shower': 'FIXTURE layer: free drain circle (r ≈ 4.5 cm) with its tray outline',
}
FIX_TERM = {'WC': 'WC pan (water closet)', 'washbasin': 'washbasin', 'bathtub': 'bathtub', 'shower': 'shower tray'}


# ====================================================================== Swiss Dwellings (DXF)
def _pts(e):
    return [(float(p[0]), float(p[1])) for p in e.get_points()]


def _ebox(e):
    from ezdxf import bbox as ebbox
    b = ebbox.extents([e])
    return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)


@functools.lru_cache(maxsize=24)
def swiss_index(stem):
    """All identifiable elements of one Swiss DXF, keyed by id, with geometry in DXF metres."""
    plan = engine.swiss_plan(stem)
    msp = plan.msp
    E = {}
    rooms = [r for r in plan.rooms if r['poly']]
    rpolys = [(r, Polygon(r['poly'], r.get('holes') or None).buffer(0)) for r in rooms]
    units = []
    for t, x, y, _ in plan.texts:
        m = re.match(r'^(Whg\.|App\.)\s*([A-Z])$', t)
        if m:
            for up in plan.units_poly:
                if up.contains(Point(x, y)):
                    units.append((m.group(2), up))

    def room_at(x, y):
        p = Point(x, y)
        c = [(r, P) for r, P in rpolys if P.contains(p)]
        return min(c, key=lambda rp: rp[1].area)[0] if c else None

    # ---- walls (one per WALL polyline) + hatch convention
    walls = []
    for e in msp.query('LWPOLYLINE[layer=="WALL"]'):
        if e.closed and len(e) >= 3:
            P = Polygon(_pts(e)).buffer(0)
            if not P.is_empty and P.area > 1e-4:
                walls.append((e, P))
    hatches = []
    for h in msp.query('HATCH[layer=="WALL"]'):
        try:
            for bp in h.paths:
                vs = [(v[0], v[1]) for v in getattr(bp, 'vertices', [])]
                if len(vs) >= 3:
                    hatches.append((h, prep(Polygon(vs).buffer(0.01))))
        except Exception:
            pass
    allw = unary_union([P for _, P in walls]) if walls else Polygon()
    foot = unary_union([allw.buffer(0.05)] + [P.buffer(0.05) for _, P in rpolys]
                       + [Polygon(_pts(e)).buffer(0.05) for e in msp.query('LWPOLYLINE[layer=="WINDOW"]') if len(e) == 4 and e.closed]).buffer(-0.05)
    rings = [g.exterior for g in getattr(foot, 'geoms', [foot]) if g.geom_type == 'Polygon']
    outer = unary_union(rings) if rings else None
    for e, P in walls:
        rp = P.representative_point()
        hp = next((h.dxf.pattern_name for h, hpoly in hatches if hpoly.contains(rp)), None)
        ext = outer is not None and P.distance(outer) < 0.06
        E[f'w:{e.dxf.handle}'] = dict(kind='wall', h=e.dxf.handle, poly=list(P.exterior.coords), holes=[list(i.coords) for i in P.interiors],
                                      ent=e, P=P, hatch=hp, ext=ext, nv=len(e))

    # ---- doors: threshold line (2 vertices) + nearest leaf (5-vertex) + swing arcs
    leaves = [(e, Polygon(_pts(e))) for e in msp.query('LWPOLYLINE[layer=="DOOR"]') if len(e) == 5]
    arcs = list(msp.query('ARC[layer=="DOOR"]'))
    for e in msp.query('LWPOLYLINE[layer=="DOOR"]'):
        if len(e) != 2:
            continue
        (x1, y1), (x2, y2) = _pts(e)
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 0.3:
            continue
        th = LineString([(x1, y1), (x2, y2)])
        lv = []
        for le, lp in sorted(leaves, key=lambda x: x[1].distance(th)):
            if lp.distance(th) < 0.15 and not any(lp.symmetric_difference(q).area < 1e-4 for _, q in lv):
                lv.append((le, lp))
        ar, seen = [], []
        for a in arcs:   # swing arcs hinged on this threshold; identical duplicates collapse to one
            c = (a.dxf.center.x, a.dxf.center.y)
            if th.distance(Point(*c)) < 0.12 and 0.35 * L < a.dxf.radius < 1.1 * L and not any(math.dist(c, q) < 0.03 and abs(a.dxf.radius - rr) < 0.01 for q, rr in seen):
                ar.append(a); seen.append((c, a.dxf.radius))
        def probe(p1, p2):
            """rooms on both sides of an opening line p1-p2 (walk out up to 1.2 m, through the wall)"""
            ll = math.dist(p1, p2)
            d = ((p2[0] - p1[0]) / ll, (p2[1] - p1[1]) / ll); n = (-d[1], d[0]); mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            rays = []
            for s in (1, -1):
                seq = []
                for k in [0.03 + 0.05 * i for i in range(24)]:
                    px, py = mx + s * n[0] * k, my + s * n[1] * k
                    if allw.contains(Point(px, py)):
                        continue
                    r = room_at(px, py)
                    if r is not None and (not seq or seq[-1] is not r):
                        seq.append(r)
                rays.append(seq)
            A0, B0 = (rays[0] or [None])[0], (rays[1] or [None])[0]
            if A0 is not None and A0 is B0:   # threshold inside one outline (door niche drawn as part of a room)
                nxt = [r for r in rays[0][1:] + rays[1][1:] if r is not A0]
                B0 = nxt[0] if nxt else A0
            return [A0, B0]
        sides = probe((x1, y1), (x2, y2))
        opening = [(x1, y1), (x2, y2)]
        if ar and (sides[0] is sides[1]):   # the drawn line may be the open leaf: try the arc's other end as the opening
            a = ar[0]; cx, cy, rr = a.dxf.center.x, a.dxf.center.y, a.dxf.radius
            ends = [(cx + rr * math.cos(math.radians(t)), cy + rr * math.sin(math.radians(t))) for t in (a.dxf.start_angle, a.dxf.end_angle)]
            far = max(ends, key=lambda q: min(math.dist(q, (x1, y1)), math.dist(q, (x2, y2))))
            s2 = probe((cx, cy), far)
            if s2[0] is not s2[1]:
                sides, opening = s2, [(cx, cy), far]
        swing = None
        if ar:
            a = ar[0]
            mid = math.radians((a.dxf.start_angle + ((a.dxf.end_angle - a.dxf.start_angle) % 360) / 2))
            sx, sy = a.dxf.center.x + 0.5 * a.dxf.radius * math.cos(mid), a.dxf.center.y + 0.5 * a.dxf.radius * math.sin(mid)
            swing = room_at(sx, sy)
        bx = th.buffer(0.08, cap_style=2)
        for le, lp in lv:
            bx = bx.union(lp)
        geo = unary_union([bx] + [lp for _, lp in lv])
        E[f'd:{e.dxf.handle}'] = dict(kind='door', h=e.dxf.handle, width=L, leaves=[(le.dxf.handle, lp) for le, lp in lv], arcs=ar,
                                      sides=sides, swing=swing, poly=list(geo.envelope.exterior.coords) if geo.geom_type != 'Polygon' else list(geo.exterior.coords),
                                      P=geo, line=opening, ent=e)

    dl = [(k, v) for k, v in E.items() if v['kind'] == 'door']
    for k, v in dl:   # identical DOOR entities drawn on top of each other (a drafting duplicate)
        v['dup'] = [kk[2:] for kk, vv in dl if kk != k and all(math.dist(a, b) < 0.01 for a, b in zip(sorted(_pts(v['ent'])), sorted(_pts(vv['ent']))))]
    # ---- windows: closed 4-vertex frame
    for e in msp.query('LWPOLYLINE[layer=="WINDOW"]'):
        if not (len(e) == 4 and e.closed):
            continue
        P = Polygon(_pts(e))
        mr = P.minimum_rotated_rectangle
        c = list(mr.exterior.coords)[:4]
        l1, l2 = math.dist(c[0], c[1]), math.dist(c[1], c[2])
        wdt, dep = max(l1, l2), min(l1, l2)
        if l1 >= l2:
            ax = ((c[1][0] - c[0][0]) / l1, (c[1][1] - c[0][1]) / l1)
        else:
            ax = ((c[2][0] - c[1][0]) / l2, (c[2][1] - c[1][1]) / l2)
        n = (-ax[1], ax[0]); ctr = P.centroid
        sides = []
        for s in (1, -1):
            r = None
            for k in [dep / 2 + 0.05 + 0.05 * i for i in range(14)]:
                px, py = ctr.x + s * n[0] * k, ctr.y + s * n[1] * k
                if allw.contains(Point(px, py)):
                    continue
                r = room_at(px, py)
                break
            sides.append(r)
        glass = [g for g in msp.query('LWPOLYLINE[layer=="WINDOW"]') if len(g) == 2 and P.buffer(0.02).contains(LineString(_pts(g)))]
        E[f'n:{e.dxf.handle}'] = dict(kind='window', h=e.dxf.handle, width=wdt, depth=dep, sides=sides, poly=list(P.exterior.coords), P=P,
                                      glass=len(glass), ent=e)

    # ---- sanitary fixtures (classification shared with the Q&A engine)
    fxe = [(fe, _ebox(fe)) for fe in msp.query('*[layer=="FIXTURE"]')]
    for kind, lst in (('WC', plan.wc), ('washbasin', plan.basin), ('bathtub', plan.tub), ('shower', plan.shower)):
        for i, b in enumerate(lst):
            P = box(*b)
            hs = [fe.dxf.handle for fe, fb in fxe if fb[0] >= b[0] - 0.01 and fb[1] >= b[1] - 0.01 and fb[2] <= b[2] + 0.01 and fb[3] <= b[3] + 0.01]
            c = P.centroid
            E[f'f:{kind}:{i}'] = dict(kind='fixture', fx=kind, bbox=b, poly=list(P.exterior.coords), P=P, handles=hs, room=room_at(c.x, c.y))

    # ---- rooms
    texts = {t: e for e in msp.query('TEXT[layer=="ROOM_TEXT"]') for t in [e.dxf.text.strip()]}
    for r, P in rpolys:
        E[f'r:{r["num"]}'] = dict(kind='room', room=r, poly=r['poly'], holes=r.get('holes') or [], P=P,
                                  h=texts[r['num']].dxf.handle if r['num'] in texts else None)
    # ---- apartments
    for u, up in units:
        E[f'u:{u}'] = dict(kind='unit', unit=u, poly=list(up.exterior.coords), P=up)
    return dict(E=E, plan=plan, units=units)


def _sheet_tf(stem):
    A, err, n, (w, h) = engine.swiss_fit(stem)
    T = lambda x, y: (np.array([x, y, 1.0]) @ A).tolist()
    M = np.array([[A[0, 0], A[1, 0]], [A[0, 1], A[1, 1]]])
    Mi = np.linalg.inv(M)
    inv = lambda u, v: (Mi @ (np.array([u, v]) - A[2])).tolist()
    return T, inv, (w, h), err, n


def _ring(T, pts):
    return [[round(v, 2) for v in T(x, y)] for x, y in pts]


def _door_type(d):
    return f"{'double' if len(d['arcs']) >= 2 or len(d['leaves']) >= 2 else 'single'}-leaf · {round(d['width'] * 20) * 5} cm clear"


def _room_name(r):
    if r is None:
        return None
    return f"{r['num']} {r['name'] or ''}".strip()


def _door_role(d):
    a, b = d['sides']
    out = lambda r: r is not None and room_term(r['name'])[0] == 'balcony / loggia / terrace'
    if a is None or b is None:
        return 'external / building-edge door'
    if out(a) or out(b):
        return 'balcony door (glazed French door likely; leaf type not in DXF)'
    if a['unit'] != b['unit']:
        return 'apartment entrance door' if (a['unit'] or b['unit']) else 'door between shared spaces'
    return 'internal door'


def swiss_parts(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    X = swiss_index(stem)
    E = X['E']
    T, inv, (w, h), err, n = _sheet_tf(stem)
    groups = []

    def grp(key, term, layer, items, typer):
        types = collections.defaultdict(list)
        for k, v in items:
            types[typer(v)].append(k)
        groups.append(dict(key=key, term=term, layer=layer, count=len(items),
                           types=[dict(name=t, count=len(ids), ids=ids) for t, ids in sorted(types.items(), key=lambda kv: (-len(kv[1]), kv[0]))]))

    by = lambda kind: [(k, v) for k, v in E.items() if v['kind'] == kind]
    grp('door', 'Doors', 'DOOR', by('door'), _door_type)
    grp('window', 'Windows', 'WINDOW', by('window'), lambda v: f"{round(v['width'] * 20) * 5} cm wide")
    grp('wall', 'Walls', 'WALL', by('wall'), lambda v: ('exterior wall' if v['ext'] else 'interior wall') + (f" · hatch {v['hatch']}" if v['hatch'] else ''))
    grp('fixture', 'Sanitary fixtures', 'FIXTURE', by('fixture'), lambda v: FIX_TERM[v['fx']])
    grp('room', 'Rooms / spaces', 'ROOM_OUTLINE', [(k, v) for k, v in by('room') if not v['room'].get('shaft')],
        lambda v: room_term(v['room']['name'])[0] or (v['room']['name'] or 'unnamed room'))
    ndup = sum(1 for _, v in by('door') if v.get('dup')) // 2
    if ndup:
        groups[0]['warn'] = f'{ndup} door{"s" if ndup > 1 else ""} drawn twice (identical overlapping DXF entities)'
    if by('unit'):
        grp('unit', 'Apartments', 'UNIT_OUTLINE', by('unit'), lambda v: 'apartment (Wohnung)')
    geo = {}
    for k, v in E.items():
        if v['kind'] == 'unit':
            continue
        g = dict(kind=v['kind'], poly=_ring(T, v['poly']))
        if v.get('holes'):
            g['holes'] = [_ring(T, hh) for hh in v['holes']]
        geo[k] = g
    from .wow import credit
    return dict(kind='swiss', file=f'{stem}.dxf', sheet=dict(w=w, h=h, units='pt', fit_err_pt=round(err, 2), fit_n=n), groups=groups, geo=geo,
                summary=_summary(groups), credit=credit(path))


def _summary(groups):
    out = []
    for g in groups:
        if not g['count']:
            continue
        nt = len(g['types'])
        out.append(f"{g['count']} {g['term'].lower()}" + (f" of {nt} types" if nt > 1 else ''))
    return out


def swiss_hit(stem, x, y, hint=None):
    """Element id under a DXF point (metres): smallest-first by kind priority; `hint` restricts to one kind."""
    X = swiss_index(stem)
    p = Point(x, y)
    order = ['fixture', 'door', 'window', 'wall', 'room']
    if hint in order:
        order = [hint] + [o for o in order if o != hint]
    for kind in order:
        tol = 0.0 if kind == 'room' else (0.12 if hint == kind else 0.04)
        c = [(k, v) for k, v in X['E'].items() if v['kind'] == kind and v['P'].distance(p) <= tol]
        if c:
            return min(c, key=lambda kv: (kv[1]['P'].distance(p), kv[1]['P'].area))[0]
    return None


def swiss_card(path, eid):
    stem = os.path.splitext(os.path.basename(path))[0]
    X = swiss_index(stem)
    v = X['E'].get(eid)
    if v is None:
        return None
    T, inv, (w, h), err, n = _sheet_tf(stem)
    dxf, pdf = f'{stem}.dxf', f'{stem}.pdf'
    k = v['kind']
    dims, props, src, notes = [], [], [], []
    D = lambda label, val, how=None: dims.append(dict(k=label, v=val, how=how))
    Pp = lambda label, val, how=None: props.append(dict(k=label, v=val, how=how))
    if k == 'wall':
        P = v['P']
        mr = P.minimum_rotated_rectangle
        c = list(mr.exterior.coords)[:4]
        l1, l2 = math.dist(c[0], c[1]), math.dist(c[1], c[2])
        rect = v['nv'] == 4 and abs(mr.area - P.area) < 1e-3
        title, typ = ('Exterior wall' if v['ext'] else 'Interior wall'), ('facade / envelope wall (Aussenwand)' if v['ext'] else 'internal wall (Innenwand)')
        if rect:
            D('Thickness', _cm(min(l1, l2)), 'short side of the wall polygon')
            D('Length', _m(max(l1, l2)), 'long side of the wall polygon')
        else:
            t = 2 * P.area / P.length
            D('Mean thickness', f'≈ {_cm(t)}', '2 × area ÷ perimeter of the wall polygon (non-rectangular piece)')
            D('Centre-line length', f'≈ {_m(P.area / t)}', 'area ÷ mean thickness')
        D('Section area on plan', f'{P.area:.2f} m²', 'shoelace area of the closed WALL polyline')
        D('Height', 'not in a 2D plan', 'the 3D walkthrough assumes 2.60 m storey height (shown as an assumption)')
        if v['hatch']:
            conv = {'SOLID': 'solid poché: in Swiss practice usually reinforced concrete (load-bearing)',
                    'ANSI31': 'diagonal hatch: in Swiss practice usually masonry'}.get(v['hatch'])
            Pp('Section hatch', v['hatch'], conv and f'drawing convention, not a material attribute: {conv}')
        Pp('Position', 'on the floor outline (envelope)' if v['ext'] else 'inside the floor outline', 'wall polygon touches the outer boundary of walls ∪ rooms ∪ windows')
        src += [dict(k='File', v=dxf), dict(k='Layer', v='WALL'), dict(k='Entity', v=f"LWPOLYLINE, {v['nv']} vertices, closed"), dict(k='Handle', v=v['h'])]
    elif k == 'door':
        title = 'Door'
        typ = _door_type(v)
        D('Clear opening width', _cm(v['width']), 'length of the threshold line between the jambs')
        if v['leaves']:
            lp = v['leaves'][0][1].minimum_rotated_rectangle
            c = list(lp.exterior.coords)[:4]
            a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
            D('Leaf', f'{_cm(max(a, b))} × {round(min(a, b) * 1000)} mm', 'drawn door-leaf rectangle (width × thickness)')
        if v['arcs']:
            a = v['arcs'][0]
            D('Swing radius', _cm(a.dxf.radius), f'ARC, {round((a.dxf.end_angle - a.dxf.start_angle) % 360)}° sweep')
        D('Height', 'not in a 2D plan', 'the 3D walkthrough assumes 2.10 m door head')
        Pp('Role', _door_role(v), 'from the rooms on both sides of the threshold')
        a, b = v['sides']
        Pp('Connects', f"{_room_name(a) or 'outside / no room'}  ↔  {_room_name(b) or 'outside / no room'}", 'probe 0.2–0.85 m either side of the threshold, skipping the wall')
        if v['swing'] is not None:
            Pp('Opens into', _room_name(v['swing']), 'room under the middle of the swing arc')
        units = {r['unit'] for r in v['sides'] if r is not None and r['unit']}
        if units:
            Pp('Apartment', ', '.join(sorted(units)))
        src += [dict(k='File', v=dxf), dict(k='Layer', v='DOOR'), dict(k='Threshold', v=f"LWPOLYLINE (2 vertices) handle {v['h']}")]
        if v['leaves']:
            src.append(dict(k='Leaf', v=', '.join(f'LWPOLYLINE handle {hh}' for hh, _ in v['leaves'])))
        if v['arcs']:
            src.append(dict(k='Swing', v=', '.join(f'ARC handle {a.dxf.handle}' for a in v['arcs'])))
        if v.get('dup'):
            notes.append(f"⚠ Drafting duplicate: identical DOOR entities (threshold handle {', '.join(v['dup'])}) lie exactly on top of this one. "
                         "Door counts here follow the DXF entities, as the dataset's own answers do.")
        notes.append('Door type, fire rating and hardware are not drawn in the Swiss DXF; a door schedule would be needed.')
    elif k == 'window':
        title = 'Window'
        a, b = v['sides']
        inner = [r for r in v['sides'] if r is not None]
        typ = 'exterior window' if len(inner) < 2 else 'internal glazing'
        if inner and room_term(inner[0]['name'])[0] == 'balcony / loggia / terrace' and len(inner) == 1:
            typ = 'window to balcony side'
        D('Width', _cm(v['width']), 'long side of the window frame rectangle')
        D('Frame depth (reveal)', _cm(v['depth']), 'short side of the frame rectangle = wall depth at the opening')
        D('Sill / head height', 'not in a 2D plan', '3D walkthrough assumes 0.90 m sill, 2.10 m head')
        if inner:
            Pp('Lights', ' & '.join(_room_name(r) for r in inner), 'room(s) found either side of the frame')
        if v['glass']:
            Pp('Glazing lines', f"{v['glass']} drawn", 'lines inside the frame (glass panes / sash)')
        src += [dict(k='File', v=dxf), dict(k='Layer', v='WINDOW'), dict(k='Entity', v='LWPOLYLINE, 4 vertices, closed'), dict(k='Handle', v=v['h'])]
    elif k == 'fixture':
        b = v['bbox']
        title = FIX_TERM[v['fx']][0].upper() + FIX_TERM[v['fx']][1:]
        typ = 'sanitary fixture (sanitary appliance)'
        D('Size on plan', f'{_cm(b[2] - b[0])} × {_cm(b[3] - b[1])}', 'bounding box of the symbol')
        if v['room'] is not None:
            Pp('Room', _room_name(v['room']))
            if v['room']['unit']:
                Pp('Apartment', v['room']['unit'])
        Pp('Recognised by', FIX_RULE[v['fx']])
        src += [dict(k='File', v=dxf), dict(k='Layer', v='FIXTURE'), dict(k='Handles', v=', '.join(v['handles'][:8]) + (' …' if len(v['handles']) > 8 else ''))]
    elif k == 'room':
        r = v['room']
        term, cls = room_term(r['name'])
        title = f"Room {r['num']}" + (f" · {r['name']}" if r['name'] else '')
        typ = term or 'room / space'
        P = v['P']
        D('Net floor area', f"{r['area']:.2f} m²", 'shoelace area of the ROOM_OUTLINE polygon (islands subtracted)')
        if r['printed'] is not None:
            dlt = r['area'] - r['printed']
            ok = abs(dlt) <= max(0.02 * r['printed'], 0.06)
            D('Printed on drawing', f"{r['printed']:.2f} m²", ('agrees' if ok else '⚠ disagrees') + f" with geometry ({dlt:+.2f} m², {100 * dlt / r['printed']:+.1f}%)")
        D('Perimeter', _m(P.length), 'length of the room outline (skirting / wall finish run)')
        bx = P.bounds
        D('Overall dimensions', f'{bx[2] - bx[0]:.2f} × {bx[3] - bx[1]:.2f} m', 'bounding box of the outline')
        if cls:
            Pp('Use class', cls, 'SIA 416 class inferred from the printed room name')
        if r['unit']:
            Pp('Apartment', r['unit'])
        E = X['E']
        dr = [e for e in E.values() if e['kind'] == 'door' and r in e['sides']]
        wn = [e for e in E.values() if e['kind'] == 'window' and r in e['sides']]
        fx = [e for e in E.values() if e['kind'] == 'fixture' and e['room'] is r]
        Pp('Doors', f"{len(dr)}" + (f" ({', '.join(_cm(e['width']) for e in dr)})" if dr else ''))
        if wn:
            Pp('Windows', f"{len(wn)} · {sum(e['width'] for e in wn):.2f} m total width")
        if fx:
            Pp('Fixtures', ', '.join(f'{c}× {k}' for k, c in collections.Counter(e['fx'] for e in fx).items()))
        src += [dict(k='File', v=dxf), dict(k='Layer', v='ROOM_OUTLINE (polygon) + ROOM_TEXT (number, name, m²)')]
        if v['h']:
            src.append(dict(k='Room number', v=f"TEXT “{r['num']}” handle {v['h']}"))
    elif k == 'unit':
        title, typ = f"Apartment {v['unit']}", 'dwelling unit (UNIT_OUTLINE)'
        D('Gross outline area', f"{v['P'].area:.2f} m²", 'area inside the UNIT_OUTLINE polygon')
        src += [dict(k='File', v=dxf), dict(k='Layer', v='UNIT_OUTLINE')]
    else:
        return None
    src.append(dict(k='Shown on', v=f'{pdf} page 1 (affine fit on {n} room labels, max error {err:.2f} pt)'))
    from .wow import credit
    return dict(id=eid, kind=k, title=title, type=typ, dims=dims, props=props, source=src, notes=notes,
                geo=dict(poly=_ring(T, v['poly']), holes=[_ring(T, hh) for hh in (v.get('holes') or [])]),
                dxf=dict(poly=[[round(a, 3), round(b, 3)] for a, b in v['poly']]), credit=credit(path))


# ====================================================================== IFC
IFC_TERMS = {
    'IfcWall': 'Wall', 'IfcWallStandardCase': 'Wall', 'IfcCurtainWall': 'Curtain wall', 'IfcSlab': 'Slab', 'IfcRoof': 'Roof',
    'IfcDoor': 'Door', 'IfcWindow': 'Window', 'IfcColumn': 'Column', 'IfcBeam': 'Beam', 'IfcStair': 'Stair', 'IfcStairFlight': 'Stair flight',
    'IfcRamp': 'Ramp', 'IfcRampFlight': 'Ramp flight', 'IfcRailing': 'Railing', 'IfcCovering': 'Covering / finish', 'IfcPlate': 'Plate / panel',
    'IfcMember': 'Member (frame / mullion)', 'IfcFooting': 'Footing', 'IfcPile': 'Pile', 'IfcBuildingElementProxy': 'Generic element (proxy)',
    'IfcFurnishingElement': 'Furniture', 'IfcFurniture': 'Furniture', 'IfcSanitaryTerminal': 'Sanitary fixture', 'IfcFlowTerminal': 'Terminal (MEP)',
    'IfcLightFixture': 'Light fitting', 'IfcSpace': 'Room / space', 'IfcPipeSegment': 'Pipe', 'IfcDuctSegment': 'Duct', 'IfcFlowSegment': 'Pipe / duct segment',
    'IfcFlowFitting': 'Fitting', 'IfcOpeningElement': 'Opening', 'IfcChimney': 'Chimney', 'IfcShadingDevice': 'Shading device',
}
IFC_TERMS.update({'IfcBuildingElementPart': 'Element part', 'IfcTransportElement': 'Transport element (lift / escalator)',
                  'IfcDiscreteAccessory': 'Accessory', 'IfcFastener': 'Fastener', 'IfcElementAssembly': 'Assembly', 'IfcReinforcingBar': 'Rebar'})
PLURAL = {'IfcTransportElement': 'Transport elements (lifts / escalators)', 'IfcSpace': 'Rooms / spaces', 'IfcCovering': 'Coverings / finishes', 'IfcMember': 'Members (frames / mullions)',
          'IfcBuildingElementProxy': 'Generic elements (proxies)', 'IfcPlate': 'Plates / panels', 'IfcFlowTerminal': 'Terminals (MEP)',
          'IfcFlowSegment': 'Pipe / duct segments', 'IfcFurnishingElement': 'Furniture', 'IfcFurniture': 'Furniture'}
ORDER = ['IfcSpace', 'IfcWall', 'IfcWallStandardCase', 'IfcCurtainWall', 'IfcDoor', 'IfcWindow', 'IfcSlab', 'IfcRoof', 'IfcColumn', 'IfcBeam',
         'IfcStair', 'IfcStairFlight', 'IfcRamp', 'IfcRailing', 'IfcCovering', 'IfcPlate', 'IfcMember', 'IfcFooting', 'IfcSanitaryTerminal',
         'IfcFlowTerminal', 'IfcFurnishingElement', 'IfcFurniture', 'IfcBuildingElementProxy']
KEY_PROPS = ['FireRating', 'IsExternal', 'LoadBearing', 'ThermalTransmittance', 'AcousticRating', 'Reference', 'Status', 'Combustible',
             'SurfaceSpreadOfFlame', 'Compartmentation', 'HandicapAccessible', 'FireExit', 'SmokeStop', 'SelfClosing', 'GlazingAreaFraction',
             'IsLandmarked', 'PubliclyAccessible', 'OccupancyType', 'GrossPlannedArea', 'NetPlannedArea', 'ExtendToStructure', 'Roughness',
             'PitchAngle', 'NumberOfRiser', 'NumberOfTreads', 'RiserHeight', 'TreadLength']


def _ifc_type_name(e):
    import ifcopenshell.util.element as ue
    t = ue.get_type(e)
    if t is not None and t.Name:
        return t.Name
    pt = getattr(e, 'PredefinedType', None)
    ot = getattr(e, 'ObjectType', None)
    if ot:
        return ot
    if pt and pt not in ('NOTDEFINED', 'USERDEFINED'):
        return pt.lower().replace('_', ' ')
    return '(no type)'


@functools.lru_cache(maxsize=6)
def ifc_parts_cached(ifc):
    m = engine.ifc_model(ifc)
    f = m.f
    groups = []
    seen = set()
    by = collections.defaultdict(list)
    for e in f.by_type('IfcProduct'):
        c = e.is_a()
        if c in ('IfcOpeningElement', 'IfcAnnotation', 'IfcGrid', 'IfcVirtualElement', 'IfcSite', 'IfcBuilding', 'IfcBuildingStorey',
                 'IfcProject') or not getattr(e, 'GlobalId', None) or e.Representation is None and c != 'IfcSpace':
            continue
        if c.endswith('Type') or e.is_a('IfcPort') or e.is_a('IfcStructuralItem'):
            continue
        by['IfcWall' if c == 'IfcWallStandardCase' else c].append(e)
    for c in sorted(by, key=lambda c: (ORDER.index(c) if c in ORDER else 99, -len(by[c]))):
        es = by[c]
        types = collections.defaultdict(list)
        for e in es:
            tn = _ifc_type_name(e)
            if c == 'IfcSpace':
                tn = re.sub(r'\s*\d+$', '', getattr(e, 'LongName', None) or '').strip() or 'space'
            elif tn == '(no type)':
                tn = IFC_TERMS.get(c, c[3:]).lower() + ' (no type in model)'
            if c in ('IfcDoor', 'IfcWindow'):
                wd, ht = getattr(e, 'OverallWidth', None), getattr(e, 'OverallHeight', None)
                if wd and ht:
                    tn += f' · {round(wd * m.lscale * 100)} × {round(ht * m.lscale * 100)} cm'
            types[tn].append(e.GlobalId)
        groups.append(dict(key=c, term=PLURAL.get(c) or IFC_TERMS.get(c, c[3:]) + ('s' if not IFC_TERMS.get(c, c[3:]).endswith(('s', ')', 'ure')) else ''),
                           layer=c, count=len(es),
                           types=[dict(name=t, count=len(ids), ids=ids) for t, ids in sorted(types.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:60]]))
    return dict(kind='ifc', file=os.path.basename(ifc), model=ifc, schema=f.schema, groups=groups, summary=_summary(groups))


def ifc_parts(path):
    ifc = engine.ifc_for(path)
    if not os.path.exists(engine.abspath(ifc)):
        return dict(kind='none', why=f'{os.path.basename(ifc)} is not in this dataset split.')
    out = dict(ifc_parts_cached(ifc))
    from .wow import credit
    out['credit'] = credit(ifc)
    return out


def _fmt(v):
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, float):
        return f'{v:.3f}'.rstrip('0').rstrip('.')
    return str(v)


def ifc_card(path, gid):
    import ifcopenshell.util.element as ue, ifcopenshell.util.unit as uu
    ifc = engine.ifc_for(path)
    m = engine.ifc_model(ifc)
    f = m.f
    try:
        e = f.by_guid(gid)
    except Exception:
        return None
    L, Ar, Vo = m.lscale, uu.calculate_unit_scale(f, 'AREAUNIT'), uu.calculate_unit_scale(f, 'VOLUMEUNIT')
    c = e.is_a()
    term = IFC_TERMS.get(c) or re.sub(r'(?<!^)(?=[A-Z])', ' ', c[3:]).capitalize()
    dims, props, src, notes = [], [], [], []
    D = lambda k, v, how=None: dims.append(dict(k=k, v=v, how=how))
    Pp = lambda k, v, how=None: props.append(dict(k=k, v=v, how=how))
    tname = _ifc_type_name(e)
    for a, lab in (('OverallWidth', 'Width'), ('OverallHeight', 'Height')):
        x = getattr(e, a, None)
        if x:
            D(lab, _cm(x * L) if x * L < 10 else _m(x * L), f'IFC attribute {a}')
    try:
        qs = ue.get_psets(e, qtos_only=True)
    except Exception:
        qs = {}
    unit_of = lambda k: ('m³', Vo) if 'Volume' in k else ('m²', Ar) if 'Area' in k else ('m', L) if any(s in k for s in ('Length', 'Width', 'Height', 'Depth', 'Perimeter', 'Thickness')) else ('', 1)
    seenq = set()
    for qn, q in qs.items():
        for k, v in q.items():
            if k == 'id' or not isinstance(v, (int, float)) or isinstance(v, bool) or not v or k in seenq:
                continue
            u, s = unit_of(k)
            seenq.add(k)
            D(k, f'{v * s:.3f} {u}'.rstrip(), f'{qn}.{k}')
            if len(seenq) >= 9:
                break
    try:
        ps = ue.get_psets(e, psets_only=True)
    except Exception:
        ps = {}
    flat = []
    for pn, p in ps.items():
        for k, v in p.items():
            if k == 'id' or v is None or v == '' or isinstance(v, (dict, list, tuple)):
                continue
            if isinstance(v, str) and re.sub(r'\W', '', v).lower() == re.sub(r'\W', '', k).lower():
                continue   # exporter placeholder (value = property name), i.e. no value
            if any(k == k2 and str(v) == str(v2) for _, k2, v2 in flat):
                continue
            flat.append((pn, k, v))
    key = sorted([x for x in flat if x[1] in KEY_PROPS], key=lambda x: KEY_PROPS.index(x[1]))
    for pn, k, v in key:
        Pp(k, _fmt(v), pn)
    other = [x for x in flat if x[1] not in KEY_PROPS]
    for pn, k, v in other[:max(0, 14 - len(key))]:
        Pp(k, _fmt(v)[:80], pn)
    if len(other) > 14 - len(key):
        notes.append(f'{len(flat)} property values in {len(ps)} property sets; the most relevant are shown.')
    if not any(k == 'FireRating' for _, k, _ in flat) and c in ('IfcDoor', 'IfcWall', 'IfcWallStandardCase', 'IfcSlab'):
        notes.append('No FireRating in this element’s property sets.')
    # material
    try:
        mm = ue.get_material(e, should_skip_usage=True)
    except Exception:
        mm = None
    if mm is not None:
        if mm.is_a('IfcMaterialLayerSet'):
            lay = [f"{l.Material.Name if l.Material else '?'} {round(l.LayerThickness * L * 1000)} mm" for l in mm.MaterialLayers]
            tot = sum(l.LayerThickness for l in mm.MaterialLayers) * L
            Pp('Material layers', ' | '.join(lay), f'IfcMaterialLayerSet “{mm.LayerSetName or ""}”')
            D('Build-up thickness', f'{round(tot * 1000)} mm', 'sum of material layer thicknesses')
        elif mm.is_a('IfcMaterial'):
            Pp('Material', mm.Name, 'IfcMaterial')
        elif mm.is_a('IfcMaterialList'):
            Pp('Materials', ', '.join(x.Name for x in mm.Materials), 'IfcMaterialList')
        elif mm.is_a('IfcMaterialConstituentSet'):
            Pp('Materials', ', '.join(f"{x.Material.Name}" + (f' ({x.Name})' if x.Name else '') for x in (mm.MaterialConstituents or []) if x.Material), 'IfcMaterialConstituentSet')
        elif mm.is_a('IfcMaterialProfileSet'):
            Pp('Profile / material', ', '.join(f"{x.Profile.ProfileName if x.Profile else ''} {x.Material.Name if x.Material else ''}".strip() for x in mm.MaterialProfiles), 'IfcMaterialProfileSet')
    st = m._storey(e)
    if st is not None:
        el = getattr(st, 'Elevation', None)
        Pp('Storey', st.Name + (f' (elevation {el * L:+.2f} m)' if el is not None else ''), 'IfcRelContainedInSpatialStructure')
    if c == 'IfcSpace':
        if getattr(e, 'LongName', None):
            Pp('Room name', e.LongName)
        a = m.q(e, 'NetFloorArea', 'GrossFloorArea')
        if not a:
            fp = m.footprint(e)
            if fp:
                D('Floor area', f'{fp:.2f} m²', 'computed from the IfcSpace 3D geometry (footprint); no Qto in the model')
    # host wall for doors / windows
    for rel in getattr(e, 'FillsVoids', None) or []:
        op = rel.RelatingOpeningElement
        for vr in getattr(op, 'VoidsElements', None) or []:
            hw = vr.RelatingBuildingElement
            Pp('Hosted in', f'{hw.is_a()} “{hw.Name or ""}”', f'IfcRelFillsElement → {hw.GlobalId}')
    if c in ('IfcWall', 'IfcWallStandardCase') and 'IsExternal' not in [k for _, k, _ in flat]:
        try:
            ext = m.exterior_walls()
            Pp('Position (geometric)', 'exterior (on the storey outline)' if e.id() in ext else 'interior', 'no IsExternal in the model: perpendicular probe to the storey outline')
        except Exception:
            pass
    if getattr(e, 'Tag', None):
        Pp('Tag', e.Tag, 'IfcElement.Tag (mark / ID on drawings)')
    if getattr(e, 'Description', None):
        Pp('Description', e.Description)
    title = term + (f' · {e.Name}' if e.Name and e.Name != tname else '')
    if c == 'IfcSpace':
        title = f"Space {e.Name or ''}" + (f" · {e.LongName}" if getattr(e, 'LongName', None) else '')
    src += [dict(k='File', v=os.path.basename(ifc) + f' ({f.schema})'), dict(k='Class', v=c + (f'.{e.PredefinedType}' if getattr(e, 'PredefinedType', None) else '')),
            dict(k='GlobalId', v=e.GlobalId), dict(k='STEP line', v=f'#{e.id()}')]
    t = ue.get_type(e)
    if t is not None:
        src.append(dict(k='Type object', v=f'{t.is_a()} #{t.id()} “{t.Name or ""}”'))
    if not dims:
        notes.append('This element carries no size attributes or quantity sets; sizes would have to be measured on the 3D geometry.')
    from .wow import credit
    return dict(id=gid, kind=c, title=title, type=tname if tname != '(no type)' else term, dims=dims, props=props, source=src, notes=notes,
                credit=credit(ifc))


# ====================================================================== vector PDF sheets and raster scans
def pdf_card(path, x, y, page=0):
    """Printed text and drawn layer under a point on a vector PDF sheet (PDF points)."""
    import pymupdf
    doc = pymupdf.open(engine.abspath(path))
    pg = doc[page]
    best = None
    for w in pg.get_text('words'):
        r = pymupdf.Rect(w[:4])
        d = 0 if r.contains(pymupdf.Point(x, y)) else min(abs(x - r.x0), abs(x - r.x1)) + min(abs(y - r.y0), abs(y - r.y1))
        if best is None or d < best[0]:
            best = (d, w)
    layer = None
    try:
        for dr in pg.get_drawings():
            if dr.get('rect') and pymupdf.Rect(dr['rect']).contains(pymupdf.Point(x, y)) and dr['rect'].width * dr['rect'].height < 2e4 and dr.get('layer'):
                layer = dr['layer']
                break
    except Exception:
        pass
    from .wow import credit
    if best is None or best[0] > 30:
        return dict(id=f'pt:{x:.0f},{y:.0f}', kind='pdf', title='Drawing linework', type='vector PDF sheet', dims=[], props=[dict(k='PDF layer', v=layer)] if layer else [],
                    source=[dict(k='File', v=os.path.basename(path)), dict(k='Page', v=page + 1), dict(k='Point', v=f'{x:.0f}, {y:.0f} pt')],
                    notes=['This sheet is a plain PDF: lines have no object identity (no IFC/DXF model behind it). Click printed tags or text to read them.'],
                    credit=credit(path))
    w = best[1]
    line = ' '.join(t[4] for t in pg.get_text('words') if t[5] == w[5] and t[6] == w[6])
    props = [dict(k='Printed text', v=w[4]), dict(k='Text line', v=line[:120])]
    if re.match(r'^[A-Z]{0,3}-?\d{2,4}[A-Z]?$', w[4]):
        props.append(dict(k='Looks like', v='a tag / mark (door, window or room number style)', how='pattern of letters + digits'))
    if layer:
        props.append(dict(k='PDF layer', v=layer, how='optional content group of the drawing under the click'))
    return dict(id=f'pt:{x:.0f},{y:.0f}', kind='text', title=f'Printed label “{w[4]}”', type='text on a vector PDF sheet',
                dims=[dict(k='Text height', v=f'{w[3] - w[1]:.1f} pt', how='word box on the sheet')], props=props,
                source=[dict(k='File', v=os.path.basename(path)), dict(k='Page', v=page + 1), dict(k='Word box', v=', '.join(f'{v:.0f}' for v in w[:4]) + ' pt')],
                notes=['A vector PDF sheet has no element objects; this is the printed text nearest the click.'],
                geo=dict(poly=[[w[0], w[1]], [w[2], w[1]], [w[2], w[3]], [w[0], w[3]]]), credit=credit(path))


RASTER_TERMS = {'window': 'Window', 'door': 'Door', 'toilet': 'WC pan', 'sink': 'Sink / washbasin', 'shower': 'Shower', 'bathtub': 'Bathtub',
                'sauna_stove': 'Sauna stove', 'floor': 'Floor plan'}


@functools.lru_cache(maxsize=64)
def raster_dets(path):
    from .raster import qa
    return [dict(d) for d in qa.dets(engine.abspath(path))]


def raster_parts(path):
    from .raster import detector as D
    from .wow import credit
    if not D.WEIGHTS.exists():
        return dict(kind='none', why='Raster symbol detector weights are not on this machine.', credit=credit(path))
    thr = D.thresholds()
    dets = [d for d in raster_dets(path) if d['cls'] in RASTER_TERMS and d['cls'] != 'floor' and d['conf'] >= thr.get(d['cls'], 0.25)]
    by = collections.defaultdict(list)
    geo = {}
    for i, d in enumerate(dets):
        k = f"x:{i}"
        by[d['cls']].append(k)
        b = d['bbox']
        geo[k] = dict(kind=d['cls'], poly=[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], conf=d['conf'])
    groups = [dict(key=c, term=RASTER_TERMS[c] + 's', layer='YOLO detector', count=len(ids), types=[dict(name=RASTER_TERMS[c] + ' (detected)', count=len(ids), ids=ids)])
              for c, ids in sorted(by.items(), key=lambda kv: -len(kv[1]))]
    return dict(kind='raster', file=os.path.basename(path), groups=groups, geo=geo, summary=_summary(groups), credit=credit(path),
                note='Raster scan: elements are symbols found by our fine-tuned detector (boxes with confidence), not CAD objects.')


def raster_card(path, eid):
    P = raster_parts(path)
    g = P.get('geo', {}).get(eid)
    if g is None:
        return None
    b = g['poly']
    from .wow import credit
    return dict(id=eid, kind=g['kind'], title=RASTER_TERMS.get(g['kind'], g['kind']), type='symbol detected on a raster scan',
                dims=[dict(k='Symbol box', v=f"{b[1][0] - b[0][0]:.0f} × {b[2][1] - b[1][1]:.0f} px", how='detector bounding box (no drawing scale applied)')],
                props=[dict(k='Detector confidence', v=f"{g['conf']:.2f}", how='YOLOv8n fine-tuned on CubiCasa5K (Stoa plans excluded), 4-rotation TTA')],
                source=[dict(k='File', v=os.path.basename(path)), dict(k='Pixel box', v=', '.join(f'{v:.0f}' for v in (b[0][0], b[0][1], b[2][0], b[2][1])))],
                notes=['Raster scans carry no element metadata; size in metres would need the drawing scale.'], geo=dict(poly=b), credit=credit(path))


# ====================================================================== dispatch
def parts(path):
    src = engine.source_of(path)
    if src == 'swiss_dwellings':
        return swiss_parts(path)
    if src in ('ifc_models', 'ifc_bench') or path.endswith('.ifc'):
        return ifc_parts(path)
    if src == 'cubicasa5k':
        try:
            return raster_parts(path)
        except Exception as e:
            from .wow import credit
            return dict(kind='none', why=f'Raster detector unavailable: {type(e).__name__}', credit=credit(path))
    from .wow import credit
    return dict(kind='none', why='This is a plain vector PDF sheet: no element objects to list. Click printed text or tags to identify them.',
                credit=credit(path))


def inspect(path, eid=None, pt=None, m=None, hint=None):
    src = engine.source_of(path)
    if src == 'swiss_dwellings':
        stem = os.path.splitext(os.path.basename(path))[0]
        if eid is None and pt is not None:
            T, inv, (w, h), err, n = _sheet_tf(stem)
            m = inv(*pt)
        if eid is None and m is not None:
            eid = swiss_hit(stem, m[0], m[1], hint)
        return swiss_card(path, eid) if eid else None
    if src in ('ifc_models', 'ifc_bench') or path.endswith('.ifc'):
        return ifc_card(path, eid) if eid else None
    if src == 'cubicasa5k':
        if eid is None and pt is not None:
            geo = raster_parts(path).get('geo', {})
            hits = [(k, g) for k, g in geo.items() if g['poly'][0][0] - 4 <= pt[0] <= g['poly'][2][0] + 4 and g['poly'][0][1] - 4 <= pt[1] <= g['poly'][2][1] + 4]
            if hits:
                eid = min(hits, key=lambda kg: (kg[1]['poly'][2][0] - kg[1]['poly'][0][0]) * (kg[1]['poly'][2][1] - kg[1]['poly'][0][1]))[0]
        return raster_card(path, eid) if eid else None
    if path.lower().endswith('.pdf') and pt is not None:
        return pdf_card(path, pt[0], pt[1])
    return None
