"""Instant bill of quantities (BoQ) for one drawing, built only from the geometry index / IFC model.

Every line carries: section, description, quantity + unit, how it was measured (method), where it came from (source
layer / IFC class / Qto name) and the evidence items, so each line can be lit up on the drawing. Quantities that the
data does not contain are left out, never estimated. Derived figures say how they were derived.
"""
import functools, os, re, collections
import numpy as np

OUT_RE = re.compile(r'balkon|balcon|loggia|terrass|terrazza|sitzplatz', re.I)


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def build(path):
    from . import engine
    src = engine.source_of(path)
    if src == 'swiss_dwellings':
        return swiss(os.path.splitext(os.path.basename(path))[0])
    if src in ('ifc_models', 'ifc_bench') or path.endswith('.ifc'):
        ifc = engine.ifc_for(path)
        if not os.path.exists(engine.abspath(ifc)):
            return dict(kind='none', lines=[], why=f'{os.path.basename(ifc)} is not in this dataset split, so there is no geometry to measure.')
        return ifc_boq(ifc, path)
    return dict(kind='none', lines=[], why='A bill of quantities needs vector geometry (Swiss DXF or IFC). '
                                          'This drawing is a raster scan or a sheet PDF, so quantities would have to be guessed. We do not guess.')


# ====================================================================== Swiss Dwellings (DXF)
@functools.lru_cache(maxsize=32)
def swiss(stem):
    from .engine import swiss_plan, swiss_fit, _map_items
    from .walk import build as walk_build
    from shapely.geometry import Polygon
    plan = swiss_plan(stem)
    g = walk_build(stem)
    A, err, n, (w, h) = swiss_fit(stem)
    lines = []

    def add(sec, desc, qty, unit, method, source, items, note=None, check=None):
        items = [dict(it, n=i + 1) for i, it in enumerate(items)]
        lines.append(dict(id=f'{sec[0]}.{sum(1 for l in lines if l["sec"] == sec) + 1:02d}', sec=sec, desc=desc, qty=qty, unit=unit,
                          method=method, source=source, note=note, check=check,
                          items=_map_items(items, A), dxf=items))

    # ---- 1 spaces: one line per apartment + its rooms, then circulation / outdoor
    rooms = [r for r in plan.rooms if r['poly']]
    rit = lambda r: dict(kind='room', label=f"{r['num']} {r['name'] or ''}".strip(), value=r['area'], bbox=list(r['bbox']),
                         poly=[list(p) for p in r['poly']], holes=r.get('holes') or None)
    units = sorted({r['unit'] for r in rooms if r['unit']})
    S1 = ('1', 'Spaces & floor areas (SIA 416)')
    for u in units:
        rs = [r for r in rooms if r['unit'] == u and not OUT_RE.search(r['name'] or '') and not r.get('shaft')]
        if rs:
            add(S1, f'Apartment {u} · net floor area (NFA), {len(rs)} rooms', _r(sum(r['area'] for r in rs)), 'm²',
                'sum of ROOM_OUTLINE polygon areas inside the UNIT_OUTLINE (shoelace)', 'DXF ROOM_OUTLINE + UNIT_OUTLINE', [rit(r) for r in rs])
    for r in sorted(rooms, key=lambda r: r['num']):
        if r.get('shaft'):
            continue
        chk = None
        if r['printed'] is not None and r['area'] is not None:
            d = abs(r['printed'] - r['area'])
            chk = dict(printed=r['printed'], computed=r['area'], ok=d <= max(0.02 * r['printed'], 0.06))
        cls = 'exterior floor area (AGF)' if OUT_RE.search(r['name'] or '') else 'net floor area'
        nm = r['name']
        if not nm:
            P = Polygon(r['poly'])
            fx = [k for k, lst in (('WC', plan.wc), ('basin', plan.basin), ('bathtub', plan.tub), ('shower', plan.shower))
                  for b in lst if P.contains(Polygon([(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]).centroid)]
            nm = f"(no name label · contains {', '.join(sorted(set(fx)))})" if fx else '(no name label)'
        add(S1, f"Room {r['num']} {nm}{' · apt ' + r['unit'] if r['unit'] else ''} · {cls}", _r(r['area']), 'm²',
            'polygon area of the room outline', 'DXF ROOM_OUTLINE', [rit(r)], check=chk)
    ind = [r for r in rooms if not OUT_RE.search(r['name'] or '') and not r.get('shaft')]
    out = [r for r in rooms if OUT_RE.search(r['name'] or '')]
    shafts = [r for r in rooms if r.get('shaft')]
    add(S1, f'Total net floor area, indoor ({len(ind)} rooms)', _r(sum(r['area'] for r in ind)), 'm²', 'sum of indoor room polygons',
        'DXF ROOM_OUTLINE', [rit(r) for r in ind])
    if out:
        add(S1, f'Total exterior floor area: balconies / loggias ({len(out)})', _r(sum(r['area'] for r in out)), 'm²', 'sum of outdoor room polygons',
            'DXF ROOM_OUTLINE', [rit(r) for r in out])
    if shafts:
        add(S1, f'Shafts / voids excluded from NFA ({len(shafts)})', _r(sum(r['area'] for r in shafts)), 'm²',
            'unlabelled strips < 1.3 m wide with no fixture', 'DXF ROOM_OUTLINE', [rit(r) for r in shafts])
    labs = [t for t in plan.texts if re.match(r'^(Whg\.|App\.)\s*[A-Z]$', t[0])]
    if labs:
        add(S1, 'Apartments (residential units)', len(labs), 'pcs', 'Whg./App. labels inside UNIT_OUTLINE', 'DXF ROOM_TEXT + UNIT_OUTLINE',
            [dict(kind='apartment', label=t[0], bbox=list(t[3])) for t in labs])

    # ---- 2 doors, grouped by clear opening width (threshold length)
    S2 = ('2', 'Doors')
    dd = collections.defaultdict(list)
    for d in g['doors']:
        dd[round(d['width'] * 100 / 5) * 5].append(d)
    for wcm in sorted(dd):
        ds = dd[wcm]
        add(S2, f'Door, opening width ≈ {wcm} cm', len(ds), 'pcs', 'threshold line (wall gap) length on layer DOOR, grouped to 5 cm',
            'DXF DOOR', [dict(kind='door', label=f"door {round(d['width'] * 100)} cm", value=d['width'], bbox=d['bbox']) for d in ds])
    add(S2, 'Doors, total', len(plan.doors), 'pcs', 'one 5-vertex door-leaf outline per door', 'DXF DOOR',
        [dict(kind='door', label=f'door {i + 1}', bbox=list(b)) for i, b in enumerate(plan.doors)])

    # ---- 3 windows, grouped by frame width
    S3 = ('3', 'Windows')
    ww = collections.defaultdict(list)
    for x in g['windows']:
        ww[round(x['width'] * 100 / 5) * 5].append(x)
    for wcm in sorted(ww):
        xs = ww[wcm]
        add(S3, f'Window, frame width ≈ {wcm} cm', len(xs), 'pcs', 'long side of the closed WINDOW frame, grouped to 5 cm', 'DXF WINDOW',
            [dict(kind='window', label=f"window {round(x['width'] * 100)} cm", value=x['width'], bbox=x['bbox']) for x in xs])
    add(S3, 'Windows, total', len(plan.windows), 'pcs', 'one closed 4-vertex frame per window', 'DXF WINDOW',
        [dict(kind='window', label=f'window {i + 1}', bbox=list(b)) for i, b in enumerate(plan.windows)])
    add(S3, 'Window frame run (sum of frame widths)', _r(sum(x['width'] for x in g['windows'])), 'm', 'sum of WINDOW frame long sides',
        'DXF WINDOW', [dict(kind='window', label=f"window {round(x['width'] * 100)} cm", value=x['width'], bbox=x['bbox']) for x in g['windows']])

    # ---- 4 sanitary
    S4 = ('4', 'Sanitary fixtures')
    for kind, lst, how in (('WC', plan.wc, 'bowl symbol (48-vertex) without drain circle'),
                           ('Washbasin', plan.basin, 'bowl symbol (48-vertex) with drain circle'),
                           ('Bathtub', plan.tub, 'bathtub outline (69-vertex polyline)'),
                           ('Shower (floor drain)', plan.shower, 'free floor-drain circle not inside basin/WC/tub')):
        add(S4, kind, len(lst), 'pcs', how, 'DXF FIXTURE', [dict(kind=kind.split()[0].lower(), label=f'{kind} {i + 1}', bbox=list(b)) for i, b in enumerate(lst)])

    # ---- 5 walls: exact plan figures + one clearly-labelled derived length
    S5 = ('5', 'Walls (plan quantities)')
    W = [Polygon([tuple(p) for p in x['outer']], [[tuple(p) for p in hh] for hh in x['holes']]) for x in g['walls']]
    witems = [dict(kind='wall', label=f'wall body {i + 1}', value=_r(p.area), bbox=list(p.bounds), poly=[list(c) for c in p.exterior.coords]) for i, p in enumerate(W)]
    area = sum(p.area for p in W)
    per = sum(p.length for p in W)
    add(S5, f'Wall footprint, {len(W)} wall bodies', _r(area), 'm²', 'area of the WALL polygons (union of the hatch outlines)', 'DXF WALL', witems)
    add(S5, 'Wall face length in plan (both faces + ends)', _r(per), 'm', 'perimeter of the WALL polygons', 'DXF WALL', witems)
    add(S5, 'Wall centreline length (derived)', _r(per / 2), 'm', 'perimeter ÷ 2: exact for straight walls, overstates by the wall thickness at each free end',
        'DXF WALL', witems, note='derived')
    if per:
        add(S5, 'Mean wall thickness (derived)', _r(2 * area / per, 3), 'm', '2 × footprint ÷ perimeter', 'DXF WALL', witems, note='derived')

    from .wow import credit
    rooms_ok = [l['check'] for l in lines if l['check']]
    return dict(kind='swiss', stem=stem, title=stem, lines=lines, sheet=dict(url=f'/api/sheet?path=data/swiss_dwellings/{stem}.pdf', w=w, h=h),
                pdf=f'data/swiss_dwellings/{stem}.pdf', credit=credit(f'data/swiss_dwellings/{stem}.pdf'),
                kpi=[dict(k='Net floor area', v=_r(sum(r['area'] for r in ind)), u='m²'), dict(k='Rooms', v=len(ind), u=''),
                     dict(k='Doors', v=len(plan.doors), u=''), dict(k='Windows', v=len(plan.windows), u=''),
                     dict(k='Sanitary', v=len(plan.wc) + len(plan.basin) + len(plan.tub) + len(plan.shower), u=''),
                     dict(k='Label checks', v=f"{sum(c['ok'] for c in rooms_ok)}/{len(rooms_ok)}", u='agree')],
                fit=dict(n=n, err_pt=round(err, 2)))


# ====================================================================== IFC
CLASSES = [  # section, label, classes
    ('2', 'Doors', ['IfcDoor']), ('3', 'Windows', ['IfcWindow']),
    ('4', 'Walls', ['IfcWall', 'IfcWallStandardCase', 'IfcCurtainWall']),
    ('5', 'Slabs, roofs & coverings', ['IfcSlab', 'IfcRoof', 'IfcCovering']),
    ('6', 'Structure', ['IfcColumn', 'IfcBeam', 'IfcFooting', 'IfcPile', 'IfcMember', 'IfcPlate']),
    ('7', 'Stairs, ramps & railings', ['IfcStair', 'IfcRamp', 'IfcRailing']),
    ('8', 'Sanitary & MEP', ['IfcSanitaryTerminal', 'IfcFlowTerminal', 'IfcPipeSegment', 'IfcFlowSegment', 'IfcFlowFitting', 'IfcDuctSegment']),
    ('9', 'Furnishing & other', ['IfcFurnishingElement', 'IfcBuildingElementProxy']),
]
SECT = {'1': 'Spaces & floor areas', '2': 'Doors', '3': 'Windows', '4': 'Walls', '5': 'Slabs, roofs & coverings', '6': 'Structure',
        '7': 'Stairs, ramps & railings', '8': 'Sanitary & MEP', '9': 'Furnishing & other', 'M': 'Materials (IfcRelAssociatesMaterial)'}
QKEYS = {'len': ['Length'], 'area': ['NetSideArea', 'NetArea', 'NetFloorArea', 'GrossArea', 'Area'], 'vol': ['NetVolume', 'GrossVolume', 'Volume', 'Skin/Component Volume']}


def _qto(e, keys):
    """First matching quantity in the element's quantity sets (incl. nested complex quantities) -> (value, key)."""
    import ifcopenshell.util.element as ue
    try:
        ps = ue.get_psets(e, qtos_only=True)
    except Exception:
        return None
    for k in keys:   # a plain quantity (BaseQuantities etc.) wins
        if k == 'Skin/Component Volume':
            continue
        for q in ps.values():
            v = q.get(k) if isinstance(q, dict) else None
            if isinstance(v, (int, float)) and v:
                return float(v), k
    if 'Skin/Component Volume' in keys:   # ArchiCAD complex quantities: one component per layer -> sum all layers
        tot, n = 0.0, 0
        for q in ps.values():
            for c in (q.values() if isinstance(q, dict) else []):
                if isinstance(c, dict):
                    v = c.get('properties', {}).get('Skin/Component Volume')
                    if isinstance(v, (int, float)):
                        tot += v; n += 1
        if n:
            return tot, f'Skin/Component Volume (sum of {n} layer components)' if n > 1 else 'Skin/Component Volume'
    return None


@functools.lru_cache(maxsize=8)
def ifc_boq(ifc, path):
    import ifcopenshell.util.element as ue, ifcopenshell.util.unit as uu
    from . import engine
    m = engine.ifc_model(ifc)
    f = m.f
    L = uu.calculate_unit_scale(f, 'LENGTHUNIT')
    Ar = uu.calculate_unit_scale(f, 'AREAUNIT')
    Vo = uu.calculate_unit_scale(f, 'VOLUMEUNIT')
    lines = []

    def it(e, val=None):
        st = m._storey(e)
        return dict(gid=e.GlobalId, label=m.label(e), cls=e.is_a(), value=val, storey=st.Name if st is not None else None)

    def add(sec, desc, qty, unit, method, source, items, note=None, check=None):
        items = [dict(x, n=i + 1) for i, x in enumerate(items)]
        lines.append(dict(id=f'{sec}.{sum(1 for l in lines if l["sec"][0] == sec) + 1:02d}', sec=(sec, SECT[sec]), desc=desc, qty=qty, unit=unit,
                          method=method, source=source, note=note, check=check, items=items))

    # 1 spaces
    sp = m.elems(['IfcSpace'])
    if sp:
        tot, srcs, its = 0.0, collections.Counter(), []
        for s in sp:
            a = _qto(s, ['NetFloorArea', 'GrossFloorArea'])
            if a:
                v = a[0] * Ar; srcs[f'Qto {a[1]}'] += 1
            else:
                v = m.footprint(s); srcs['3D footprint'] += 1
            its.append(it(s, _r(v)))
            tot += v or 0
        add('1', f'Spaces (IfcSpace), {len(sp)} on {len({i["storey"] for i in its})} storeys', len(sp), 'pcs', 'count of IfcSpace', 'IfcSpace', its)
        add('1', 'Floor area of all spaces', _r(tot), 'm²', ' + '.join(f'{k} ×{v}' for k, v in srcs.items()), 'IfcSpace', its)
        for stn in [s for s in m.storeys if s]:
            ss = [i for i in its if i['storey'] == stn]
            if ss:
                add('1', f'Storey “{stn}” · {len(ss)} spaces', _r(sum(i['value'] or 0 for i in ss)), 'm²', 'sum of space floor areas on this storey', 'IfcSpace + IfcBuildingStorey', ss)
    # 2..9 elements
    for sec, lab, classes in CLASSES:
        els = m.elems(classes)
        if not els:
            continue
        by = collections.defaultdict(list)
        for e in els:
            by[e.is_a()].append(e)
        for cls, es in sorted(by.items()):
            add(sec, f'{cls[3:]} · all', len(es), 'pcs', f'count of {cls}', cls, [it(e) for e in es])
            if cls in ('IfcDoor', 'IfcWindow'):   # group by type and overall size (attributes in the model)
                grp = collections.defaultdict(list)
                for e in es:
                    t = ue.get_type(e)
                    wd, ht = getattr(e, 'OverallWidth', None), getattr(e, 'OverallHeight', None)
                    size = f'{round(wd * L * 100)} × {round(ht * L * 100)} cm' if wd and ht else 'size not in model'
                    grp[(t.Name if t is not None and t.Name else (e.Name or cls[3:]), size)].append(e)
                for (tn, size), xs in sorted(grp.items(), key=lambda kv: -len(kv[1]))[:40]:
                    add(sec, f'{tn} · {size}', len(xs), 'pcs', 'grouped by IfcTypeObject name + OverallWidth × OverallHeight', cls, [it(e) for e in xs])
            for kind, unit, scale in (('len', 'm', L), ('area', 'm²', Ar), ('vol', 'm³', Vo)):
                vals = [(e, _qto(e, QKEYS[kind])) for e in es]
                vals = [(e, q) for e, q in vals if q]
                if not vals or (kind == 'len' and cls in ('IfcDoor', 'IfcWindow', 'IfcSpace')):
                    continue
                keys = collections.Counter(re.sub(r' \(sum of \d+ layer components\)', ' (layers summed)', q[1]) for _, q in vals)
                add(sec, f'{cls[3:]} · {"length" if kind == "len" else "area" if kind == "area" else "volume"}'
                         + (f' ({len(vals)} of {len(es)} have it)' if len(vals) < len(es) else ''),
                    _r(sum(q[0] * scale for _, q in vals), 3), unit, 'sum of ' + ', '.join(f'Qto {k} ×{v}' for k, v in keys.items()),
                    cls, [it(e, _r(q[0] * scale, 3)) for e, q in vals])
    # M materials
    mats = collections.defaultdict(lambda: dict(els=[], vol=0.0, nv=0, thick=set()))
    for e in f.by_type('IfcElement'):
        try:
            mm = ue.get_material(e)
        except Exception:
            mm = None
        if mm is None:
            continue
        names = []
        if mm.is_a('IfcMaterial'):
            names = [mm.Name]
        elif mm.is_a('IfcMaterialLayerSetUsage'):
            for l in mm.ForLayerSet.MaterialLayers:
                if l.Material: names.append(l.Material.Name); mats[l.Material.Name]['thick'].add(round(l.LayerThickness * L * 1000))
        elif mm.is_a('IfcMaterialLayerSet'):
            names = [l.Material.Name for l in mm.MaterialLayers if l.Material]
        elif mm.is_a('IfcMaterialList'):
            names = [x.Name for x in mm.Materials]
        elif mm.is_a('IfcMaterialConstituentSet'):
            names = [c.Material.Name for c in (mm.MaterialConstituents or []) if c.Material]
        elif hasattr(mm, 'Material') and mm.Material is not None:
            names = [mm.Material.Name]
        single = len(set(names)) == 1
        for nm in set(n for n in names if n):
            d = mats[nm]
            d['els'].append(e)
            if single:
                q = _qto(e, QKEYS['vol'])
                if q: d['vol'] += q[0] * Vo; d['nv'] += 1
    for nm, d in sorted(mats.items(), key=lambda kv: -len(kv[1]['els']))[:60]:
        cls = collections.Counter(e.is_a()[3:] for e in d['els']).most_common(3)
        th = f" · layer {', '.join(str(t) for t in sorted(d['thick']))} mm" if d['thick'] else ''
        add('M', f'{nm} · {", ".join(f"{c} ×{k}" for c, k in cls)}{th}', len(d['els']), 'elements', 'elements associated with this material', 'IfcRelAssociatesMaterial',
            [it(e) for e in d['els']])
        if d['nv']:
            add('M', f'{nm} · volume ({d["nv"]} single-material elements with a Qto volume)', _r(d['vol'], 3), 'm³', 'sum of Qto volumes', 'IfcRelAssociatesMaterial + Qto', [it(e) for e in d['els']])

    from .wow import credit
    ndoor = len(m.elems(['IfcDoor'])); nwin = len(m.elems(['IfcWindow']))
    sp_area = next((l['qty'] for l in lines if l['desc'] == 'Floor area of all spaces'), None)
    pv = engine.plan_view(path)
    return dict(kind='ifc', title=os.path.basename(ifc), model=ifc, lines=lines, credit=credit(ifc), plan=pv,
                schema=f.schema, kpi=[dict(k='Space floor area', v=sp_area, u='m²'), dict(k='Spaces', v=len(sp), u=''),
                                      dict(k='Doors', v=ndoor, u=''), dict(k='Windows', v=nwin, u=''),
                                      dict(k='Storeys', v=len(m.storeys), u=''), dict(k='Materials', v=len(mats), u='')])


# ====================================================================== exports
def _evidence_ids(l):
    return '; '.join((i.get('gid') or i.get('label') or '') for i in l['items'][:400])


def to_csv(b, path):
    import csv, io, datetime
    o = io.StringIO()
    w = csv.writer(o)
    w.writerow(['PINPOINT bill of quantities', os.path.basename(path)])
    w.writerow(['Generated', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'every quantity measured from the file; nothing estimated'])
    if b.get('credit'):
        w.writerow(['Data credit', b['credit'].get('credit'), b['credit'].get('licence') or ''])
    w.writerow([])
    v = verify_cached(path) or {}
    w.writerow(['Item', 'Section', 'Description', 'Quantity', 'Unit', 'Method', 'Source', 'Printed label', 'Computed', 'Check',
                'Dataset ground truth', 'Deviation %', 'Dataset question', 'Evidence count', 'Evidence (GlobalId / label)'])
    for l in b['lines']:
        c = l.get('check') or {}
        g = (v.get(l['id']) or [None])[0]
        w.writerow([l['id'], l['sec'][1], l['desc'], l['qty'], l['unit'], l['method'], l['source'], c.get('printed', ''), c.get('computed', ''),
                    ('agree' if c.get('ok') else 'DISAGREE') if c else '', g['truth'] if g else '', g['dev'] if g else '', g['q'] if g else '',
                    len(l['items']), _evidence_ids(l)])
    return '﻿' + o.getvalue()   # BOM so Excel opens the umlauts correctly


def to_pdf(b, path):
    """Original drawing sheet first (unchanged), then the BoQ as a table. Returns PDF bytes."""
    import pymupdf, html, datetime
    from . import engine
    out = pymupdf.open()
    sheet = b.get('pdf')
    if not sheet and b.get('kind') == 'ifc' and b.get('plan') and b['plan'].get('name'):
        cand = os.path.join(os.path.dirname(b['model']), b['plan']['name'][:-4] + '.pdf')
        sheet = cand if os.path.exists(engine.abspath(cand)) else None
    if sheet and os.path.exists(engine.abspath(sheet)):
        src = pymupdf.open(engine.abspath(sheet))
        out.insert_pdf(src, from_page=0, to_page=0)
    E = lambda x: html.escape(str(x if x is not None else ''))
    fmt = lambda v: (f'{v:,.3f}'.rstrip('0').rstrip('.') if isinstance(v, float) else f'{v:,}' if isinstance(v, int) else E(v))
    rows, sec = [], None
    V = verify_cached(path) or {}
    for l in b['lines']:
        if l['sec'] != sec:
            sec = l['sec']
            rows.append(f'<tr class="s"><td colspan="5">{E(sec[0])} &nbsp; {E(sec[1])}</td></tr>')
        c = l.get('check')
        chk = '' if not c else (f' <span class="ok">✓ label {c["printed"]}</span>' if c['ok'] else f' <span class="bad">≠ label {c["printed"]}</span>')
        gt = (V.get(l['id']) or [None])[0]
        if gt:
            chk += f' <span class="gt">✓ dataset ground truth {E(gt["truth"])}{(" · Δ " + str(gt["dev"]) + "%") if gt["type"] != "count" else ""}</span>'
        rows.append(f'<tr><td class="id">{E(l["id"])}</td><td>{E(l["desc"])}{chk}<div class="m">{E(l["method"])} · {E(l["source"])} · {len(l["items"])} evidence item(s)</div></td>'
                    f'<td class="q">{fmt(l["qty"])}</td><td class="u">{E(l["unit"])}</td></tr>')
    kp = ' &nbsp;·&nbsp; '.join(f'<b>{fmt(k["v"])}</b> {E(k["u"])} {E(k["k"])}' for k in b.get('kpi', []))
    cr = b.get('credit') or {}
    doc = f'''<h1>Bill of quantities</h1>
<p class="sub">{E(os.path.basename(path))} · generated {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} by PINPOINT · measured from the file, nothing estimated</p>
<p class="kpi">{kp}</p>
<table><tr class="h"><td>Item</td><td>Description · method · source</td><td class="q">Qty</td><td class="u">Unit</td></tr>{"".join(rows)}</table>
<p class="cr"><b>Data credit:</b> {E(cr.get("credit"))} {("· " + E(cr.get("licence"))) if cr.get("licence") else ""}</p>'''
    css = '''* { font-family: sans-serif; } h1 { font-size: 17px; margin: 0; color: #111; } .sub { font-size: 8px; color: #555; margin: 2px 0 6px; }
.kpi { font-size: 9px; background: #fff4dc; padding: 4px; } table { width: 100%; border-collapse: collapse; font-size: 8px; }
td { border-bottom: 0.5px solid #ccc; padding: 2px 3px; vertical-align: top; } tr.h td { font-weight: bold; border-bottom: 1px solid #000; }
tr.s td { font-weight: bold; background: #1d2433; color: #ffffff; padding: 3px; font-size: 9px; } .id { font-family: monospace; width: 32px; color: #8a5a00; }
.q { text-align: right; font-weight: bold; width: 60px; } .u { width: 40px; color: #444; } .m { color: #777; font-size: 6.5px; }
.ok { color: #138a52; font-size: 7px; } .gt { color: #ffffff; background: #138a52; font-size: 6.5px; font-weight: bold; } .bad { color: #c0392b; font-size: 7px; font-weight: bold; } .cr { font-size: 7px; color: #444; margin-top: 8px; }'''
    story = pymupdf.Story(html=doc, user_css=css)
    import io
    buf = io.BytesIO()
    wr = pymupdf.DocumentWriter(buf)
    rect = pymupdf.paper_rect('a4')
    where = rect + (36, 36, -36, -40)
    more = True
    while more:
        dev = wr.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        wr.end_page()
    wr.close()
    tab = pymupdf.open('pdf', buf.getvalue())
    out.insert_pdf(tab)
    n0 = out.page_count - tab.page_count
    for i in range(n0, out.page_count):   # footer with credit on every BoQ page
        pg = out[i]
        pg.insert_text((36, pg.rect.height - 22), f'PINPOINT BoQ · {os.path.basename(path)} · page {i - n0 + 1}/{tab.page_count}', fontsize=6.5, color=(.4, .4, .4))
        pg.insert_text((36, pg.rect.height - 13), ('Data: ' + (cr.get('credit') or ''))[:190], fontsize=5.5, color=(.45, .45, .45))
    return out.tobytes(deflate=True)


# ====================================================================== cross-check against the dataset's own questions
def _key(it):
    if it.get('gid'):
        return it['gid']
    b = it.get('bbox')
    return tuple(round(v, 1) for v in b) if b else it.get('label')


_VER, _VLOCK = {}, __import__('threading').Lock()


def verify_cached(path):
    return _VER.get(path)


def warm(path):
    """Start verification in the background (IFC drawings can have hundreds of questions)."""
    import threading
    with _VLOCK:
        if path in _VER or ('busy', path) in _VER:
            return
        _VER[('busy', path)] = True
    def run():
        try:
            verify(path)
        finally:
            _VER.pop(('busy', path), None)
    t = threading.Thread(target=run, daemon=True); t._wow_warm = True; t.start()


def verify(path):
    import time
    while ('busy', path) in _VER and path not in _VER and not getattr(__import__('threading').current_thread(), '_wow_warm', False):
        time.sleep(0.2)
    if path in _VER:
        return _VER[path]
    out = _verify(path)
    _VER[path] = out
    return out


def _verify(path):
    """For every numeric ground-truth question on this drawing, answer it with the engine and find the BoQ line with
    the same evidence set (same elements). A line is 'verified' when that question's answer matches the ground truth
    under the challenge's grading (counts exact, measures within 2%). Matching is by evidence identity, not by number."""
    from . import engine
    from .wow import _num
    b = _num(build(path))
    if b.get('kind') == 'none':
        return {}
    idx = {}
    for l in b['lines']:
        k = frozenset(_key(i) for i in l['items'])
        if k:
            idx.setdefault(k, []).append(l)
    out, seen = {}, set()
    for q in engine.questions():
        if q['path'] != path or q['type'] not in ('count', 'area', 'length', 'volume') or q['question'] in seen:
            continue
        seen.add(q['question'])
        try:
            r = _num(engine.ask(path, q['question']))
        except Exception:
            continue
        k = frozenset(_key(i) for i in r.get('items') or [])
        for l in idx.get(k, []):
            unit_ok = (q['type'] == 'count') == (l['unit'] in ('pcs', 'elements'))
            same = l['qty'] is not None and r['value'] is not None and abs(float(l['qty']) - float(r['value'])) <= max(1e-6, 0.005 * abs(float(r['value'])))
            if not unit_ok or not same:
                continue
            t = q['answer']
            dev = abs(float(l['qty']) - float(t)) / abs(float(t)) * 100 if t else 0.0
            ok = engine.grade(l['qty'], q)
            out.setdefault(l['id'], []).append(dict(q=q['question'], truth=t, value=l['qty'], ok=bool(ok), dev=round(dev, 3), type=q['type']))
    return out
