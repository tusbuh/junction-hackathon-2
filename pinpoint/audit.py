"""Dataset audit: run every cross-check over every drawing and list the places where two independent readings
of the same fact disagree.   .venv/bin/python -m pinpoint.audit  ->  static/findings.json

Checks:
- Swiss CAD: printed m² label vs the area of the room polygon it labels
- IFC: elements with identical geometry (same world bbox to 2 cm and same volume) = duplicates that double-count
- IFC: same-class elements whose boxes overlap almost completely (IoU >= 0.9) = overlapping copies
- IFC: IfcSpace floor quantity vs the footprint of its own 3D body (gross figures compared)"""
import os, sys, glob, json, time
import numpy as np
from . import engine
from .engine import DATA, ROOT

OUT = os.path.join(ROOT, 'static', 'findings.json')
SKIP = ('IfcFeatureElement', 'IfcOpeningElement', 'IfcSpace', 'IfcVirtualElement', 'IfcAnnotation', 'IfcBuildingElementPart')


def rel(p):
    return os.path.relpath(p, DATA)


def swiss():
    out, n = [], 0
    for f in sorted(glob.glob(os.path.join(DATA, 'data/swiss_dwellings/*.dxf'))):
        stem = os.path.basename(f)[:-4]
        p = engine.swiss_plan(stem)
        for r in p.rooms:
            if r['printed'] is None or r['area'] is None: continue
            n += 1
            if abs(r['printed'] - r['area']) > max(0.02 * r['printed'], 0.06):
                out.append(dict(kind='label_vs_geometry', severity='amber', source='swiss_dwellings', path=f'data/swiss_dwellings/{stem}.pdf',
                                title=f"Room {r['num']} {r['name'] or ''}: printed {r['printed']} m², outline {r['area']} m²",
                                printed=r['printed'], computed=r['area'], unit='m²',
                                question=f"What is the area of room {r['num']} in m²?"))
    return out, n


def ifc_models():
    files = sorted(glob.glob(os.path.join(DATA, 'data/ifc_models/*.ifc')) + glob.glob(os.path.join(DATA, 'data/ifc_bench/*.ifc')))
    out, stats = [], dict(elements=0, spaces=0, models=len(files))
    for f in files:
        t = time.time()
        r = rel(f)
        m = engine.ifc_model(r)
        st = lambda e: (m._storey(e).Name if m._storey(e) is not None else None)
        els = [e for e in m.f.by_type('IfcElement') if not e.is_a(SKIP[0]) and not any(e.is_a(c) for c in SKIP) and e.Representation is not None]
        stats['elements'] += len(els)
        boxes = {}
        for e in els:
            k = m.gkey(e)
            if k: boxes[e.id()] = (e, k)
        groups = {}
        for e, k in boxes.values():
            groups.setdefault((e.is_a(), k), []).append(e)
        dup_ids = set()
        for (cls, k), g in groups.items():
            if len(g) < 2: continue
            dup_ids |= {e.id() for e in g}
            storeys = sorted({st(e) or '?' for e in g})
            out.append(dict(kind='duplicate', severity='amber', source=r.split('/')[1], path=r, cls=cls,
                            title=f"{len(g)}× {g[0].Name or cls} with identical geometry" + (f" on {' and '.join(storeys)}" if storeys else ''),
                            gids=[e.GlobalId for e in g], storeys=[st(e) for e in g], volume=k[2],
                            detail=f"Same world bounding box (to 2 cm) and same volume {k[2]} m³: any count, area or volume over {cls} includes it {len(g)} times."))
        # near-complete overlaps between different same-class elements (copies that were nudged or trimmed)
        bycls = {}
        for e, k in boxes.values():
            if e.id() in dup_ids or k[2] <= 0.05: continue
            bycls.setdefault(e.is_a(), []).append((e, np.array(k[0]) * 0.02, np.array(k[1]) * 0.02, k[2]))
        for cls, lst in bycls.items():
            if len(lst) > 3000: continue
            lo = np.array([a for _, a, _, _ in lst]); hi = np.array([b for _, _, b, _ in lst])
            vol = np.prod(np.maximum(hi - lo, 1e-6), axis=1)
            for i in range(len(lst)):
                il = np.maximum(lo[i], lo[i + 1:]); ih = np.minimum(hi[i], hi[i + 1:])
                inter = np.prod(np.clip(ih - il, 0, None), axis=1)
                iou = inter / (vol[i] + vol[i + 1:] - inter)
                for j in np.nonzero(iou >= 0.9)[0]:
                    a, b = lst[i], lst[i + 1 + j]
                    if abs(a[3] - b[3]) > 0.2 * max(a[3], b[3]): continue     # very different volumes: e.g. a slab and a thin finish
                    out.append(dict(kind='overlap', severity='amber', source=r.split('/')[1], path=r, cls=cls,
                                    title=f"Two {a[0].Name or cls} overlap almost completely ({iou[j] * 100:.0f}% of their boxes)",
                                    gids=[a[0].GlobalId, b[0].GlobalId], storeys=[st(a[0]), st(b[0])], volume=[a[3], b[3]],
                                    detail=f"Volumes {a[3]} m³ and {b[3]} m³ occupy the same place: likely a copy left behind."))
        # spaces: floor quantity vs the footprint of the 3D body
        for s in m.f.by_type('IfcSpace'):
            qa = m.q(s, 'GrossFloorArea') or m.q(s, 'NetFloorArea')
            if not qa: continue
            stats['spaces'] += 1
            g = m.footprint(s)
            if g and abs(g - qa) > 0.1 * qa and abs(g - qa) > 0.5:
                out.append(dict(kind='space_body', severity='amber', source=r.split('/')[1], path=r, cls='IfcSpace',
                                title=f"Space {s.Name} {getattr(s, 'LongName', '') or ''}: floor quantity {qa:.2f} m², 3D body footprint {g:.2f} m²",
                                gids=[s.GlobalId], storeys=[st(s)], printed=round(qa, 2), computed=round(g, 2), unit='m²',
                                detail="The space's 3D solid is larger or smaller than the floor area it reports, so anyone measuring the model in 3D gets a different number."))
        print(f'  {os.path.basename(f)}: {len(els)} elements, {time.time() - t:.0f}s, findings so far {len(out)}', file=sys.stderr, flush=True)
    return out, stats


if __name__ == '__main__':
    sw, n_rooms = swiss()
    ifc, st = ifc_models()
    res = dict(generated=time.strftime('%Y-%m-%d %H:%M'), checked=dict(swiss_rooms=n_rooms, **st), findings=sw + ifc)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print(f'{len(res["findings"])} findings -> {OUT}')
    for f in res['findings']:
        print(' -', f['source'], os.path.basename(f['path']), '|', f['title'])
