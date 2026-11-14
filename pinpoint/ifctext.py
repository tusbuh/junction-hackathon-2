"""Deterministic answers to free-text BIM questions (IFC-Bench style), each citing the IFC elements it used.
Intent (list types / extreme / total / levels / rooms / materials / metadata / count) x element class, all
detected with the multilingual lexicon. No LLM: the answer text is assembled from model facts, and the
cited GlobalIds light up in the 3D view."""
import re, collections
import ifcopenshell.util.element as ue
from .lexicon import has, first

CLASSES = {
    'door': ['IfcDoor'], 'window': ['IfcWindow'], 'wall': ['IfcWall', 'IfcWallStandardCase'], 'slab': ['IfcSlab'], 'room': ['IfcSpace'],
    'stair': ['IfcStair'], 'beam': ['IfcBeam'], 'column': ['IfcColumn'], 'sanitary': ['IfcSanitaryTerminal', 'IfcFlowTerminal'],
    'railing': ['IfcRailing'], 'covering': ['IfcCovering'], 'furniture': ['IfcFurnishingElement', 'IfcFurniture'],
    'roof': ['IfcRoof'], 'mep': ['IfcFlowSegment', 'IfcFlowFitting', 'IfcFlowTerminal', 'IfcDistributionElement'],
    'toilet': ['IfcSanitaryTerminal', 'IfcFlowTerminal'], 'member': ['IfcMember'], 'footing': ['IfcFooting'],
}
EXTRA = {'railing': ['railing', 'geländer', 'garde-corps'], 'covering': ['covering', 'ceiling', 'flooring', 'finish'],
         'furniture': ['furniture', 'furnishing', 'möbel'], 'roof': ['roof', 'dach'], 'mep': ['mep', 'pipe', 'duct', 'system type'],
         'member': ['member'], 'footing': ['footing', 'foundation']}


def _has(c, t):
    return has(c, t) if c in ('door', 'window', 'wall', 'slab', 'room', 'stair', 'beam', 'column', 'sanitary', 'toilet') \
        else any(w in t.lower() for w in EXTRA.get(c, []))


def type_name(e):
    t = ue.get_type(e)
    return (t.Name if t is not None and t.Name else None) or getattr(e, 'ObjectType', None) or e.Name or e.is_a()


def psv(e, *names):
    for ps in ue.get_psets(e).values():
        for n in names:
            if ps.get(n) not in (None, ''):
                return ps[n]
    return None


def answer(model, q):
    f = model.f
    ql = q.lower()
    # element class = the earliest-mentioned one (questions name their object first)
    cls_key, best = None, 10 ** 9
    for c in ['toilet', 'sanitary', 'door', 'window', 'railing', 'covering', 'furniture', 'stair', 'slab', 'beam', 'column', 'roof', 'mep', 'member', 'footing', 'wall', 'room']:
        if _has(c, q):
            words = (EXTRA.get(c) or []) + [{'toilet': 'toilet', 'sanitary': 'sanitary', 'door': 'door', 'window': 'window', 'stair': 'stair', 'slab': 'slab',
                                              'beam': 'beam', 'column': 'column', 'wall': 'wall', 'room': 'room'}.get(c, c)]
            pos = min([ql.find(w) for w in words if ql.find(w) >= 0] or [10 ** 8])
            if pos < best: cls_key, best = c, pos
    els = model.elems(CLASSES[cls_key]) if cls_key else []
    if cls_key == 'toilet':
        els = [e for e in els if re.search(r'toilet|wc|closet|klosett', (e.Name or '') + type_name(e), re.I)]
    if re.search(r'exterior|external|outer|outside|facade|façade', ql) and cls_key in ('wall', 'door', 'window', 'slab'):
        els = [e for e in els if psv(e, 'IsExternal') is True]; scope = 'exterior '
    elif re.search(r'interior|internal|inner|inside', ql) and cls_key in ('wall', 'door', 'window', 'slab'):
        els = [e for e in els if psv(e, 'IsExternal') is not True]; scope = 'interior '
    else:
        scope = ''
    steps = [f"Opened {f.schema} model: {len(f.by_type('IfcProduct'))} products, {len(model.storeys)} storeys"]
    R = lambda text, items, how, extra=(): dict(value=text, unit='text', items=items, method=how, steps=steps + list(extra))
    item = lambda e, v=None: dict(gid=e.GlobalId, label=model.label(e), cls=e.is_a(), value=v,
                                  parts=[c.GlobalId for c in ue.get_decomposition(e) if hasattr(c, 'GlobalId')][:200])
    noun = (scope + (cls_key or 'element')).replace('room', 'space')

    # --- information that a BIM model normally does not carry: check the property sets before saying so
    nm = re.search(r'warrant|lifespan|life span|embodied carbon|carbon|cost|price|u-value|thermal bridge|air ?tightness|solar heat|live load|'
                   r'recyclab|glazing type|vapou?r barrier|acoustic|escape|emergency|fire exit|north|orientation', ql)
    if nm:
        key = re.sub(r'[\s-]', '', nm.group(0))[:9]
        hits = [(e, n, v) for e in f.by_type('IfcProduct') for ps in [ue.get_psets(e)] for p in ps.values() for n, v in p.items()
                if isinstance(n, str) and key in re.sub(r'[\s_-]', '', n.lower()) and v not in (None, '')][:50]
        if not hits:
            return R(f"This information (“{nm.group(0)}”) is not available in the BIM model: no property, quantity or element carries it.", [],
                     'searched all property sets', [f"Searched every Pset/Qto of {len(f.by_type('IfcProduct'))} products for “{key}…”: no match",
                                                    "Answering “not in model” instead of guessing"])
        return R('\n'.join(f"{model.label(e)}: {n} = {v}" for e, n, v in hits[:20]), [item(e) for e, _, _ in hits], 'property-set search',
                 [f"Found {len(hits)} properties matching “{key}…”"])
    # --- one element cited by its GlobalId (22-char IFC base64): answer its attributes and quantities directly
    gm = re.search(r'(?<![0-9A-Za-z_$])([0-9A-Za-z_$]{22})(?![0-9A-Za-z_$])', q)
    if gm:
        try:
            e = f.by_guid(gm.group(1))
        except Exception:
            e = None
        if e is not None:
            facts = {}
            sc = model.lscale
            for a in ('OverallWidth', 'OverallHeight'):
                v = getattr(e, a, None)
                if v: facts[a.replace('Overall', '').lower()] = f"{v * sc:.2f} m"
            for qn, unit in (('Width', 'm'), ('Height', 'm'), ('Length', 'm'), ('Depth', 'm'), ('Thickness', 'm'), ('NetArea', 'm²'), ('GrossArea', 'm²'),
                             ('NetFloorArea', 'm²'), ('NetSideArea', 'm²'), ('NetVolume', 'm³'), ('GrossVolume', 'm³')):
                v = model.q(e, qn)
                k = re.sub(r'(?<!^)([A-Z])', r' \1', qn).lower()
                if v and k not in facts:
                    facts[k] = f"{v * (sc if unit == 'm' else 1):.2f} {unit}"
            st = model._storey(e)
            mats = [m.Name for m in (ue.get_materials(e) or []) if getattr(m, 'Name', None)]
            asked = next((k for k in facts if k.split()[-1] in ql), None)
            head = f"The {asked} of {e.is_a()[3:].lower()} {gm.group(1)} ({model.label(e)}) is {facts[asked]}." if asked else \
                f"{e.is_a()} {gm.group(1)}: {model.label(e)}."
            rest = [f"{k}: {v}" for k, v in facts.items() if k != asked] + ([f"type: {type_name(e)}"] if type_name(e) else []) + \
                ([f"storey: {st.Name}"] if st is not None else []) + ([f"material: {', '.join(mats[:4])}"] if mats else [])
            return R(head + ('\n' + '; '.join(rest) if rest else ''), [item(e)], 'element lookup by GlobalId',
                     [f"Looked up GlobalId {gm.group(1)} → {e.is_a()} “{model.label(e)}”", 'Read its attributes and base quantities (unit-scaled)'])
    # --- metadata
    if re.search(r'software|ifc standard|schema|authoring|application', ql):
        h = f.header.file_name
        app = ', '.join(x for x in (h.originating_system, h.preprocessor_version) if x)
        return R(f"Authoring software: {app or 'not stated'}. IFC schema: {f.schema}.", [], 'IFC header (FILE_NAME, FILE_SCHEMA)',
                 ["Read STEP header FILE_NAME.originating_system / preprocessor_version and FILE_SCHEMA"])
    if re.search(r"building'?s? (type|function|name)|type of building|building type", ql):
        b = (f.by_type('IfcBuilding') or [None])[0]
        txt = f"Building name: {b.Name if b else '?'}; type/description: {(b.ObjectType or b.Description or psv(b, 'OccupancyType') or 'not stated') if b else '?'}; levels: {len(model.storeys)}."
        return R(txt, [item(b)] if b else [], 'IfcBuilding attributes', ["Read IfcBuilding.Name / ObjectType / Description and Pset OccupancyType"])
    if re.search(r'ceiling', ql) and re.search(r'height|tall', ql):
        sp = model.elems(['IfcSpace'])
        hs = [(s, model.q(s, 'Height', 'FinishCeilingHeight', 'GrossHeight', 'NetHeight') or psv(s, 'FinishCeilingHeight', 'Height')) for s in sp]
        hs = [(s, float(h) * (model.lscale if float(h) > 50 else 1)) for s, h in hs if h]
        src = 'IfcSpace height quantities'
        if not hs:   # no quantity: measure the space solid's vertical extent
            import ifcopenshell.geom, numpy as np
            for s_ in sp:
                try:
                    v = np.array(ifcopenshell.geom.create_shape(model.gs, s_).geometry.verts).reshape(-1, 3)
                    hs.append((s_, float(v[:, 2].max() - v[:, 2].min())))
                except Exception: pass
            src = 'vertical extent of each IfcSpace solid (no height quantity in model)'
        if hs:
            low = bool(re.search(r'lowest|smallest|minimum', ql))
            hs.sort(key=lambda x: x[1] if low else -x[1])
            nmx = re.search(r'top (\d+)|(\d+) (?:rooms|spaces)', ql)
            top = hs[:int(nmx.group(1) or nmx.group(2))] if nmx else [x for x in hs if abs(x[1] - hs[0][1]) < 0.005]
            m = re.search(r'room ([A-Z]?\d+)', q, re.I)
            if m:
                top = [x for x in hs if m.group(1).lower() in model.label(x[0]).lower()] or top
            return R('; '.join(f"{model.label(s)}: {h:.2f} m" for s, h in top[:15]) + (f" (and {len(top) - 15} more)" if len(top) > 15 else ''),
                     [item(s, round(h, 2)) for s, h in top], src, [f"Heights of {len(hs)} spaces from {src}"])
    # --- levels
    if re.search(r'height of each level|heights of each level|floor-to-floor|storey height|level heights|elevation', ql):
        sts = sorted(f.by_type('IfcBuildingStorey'), key=lambda s: s.Elevation or 0)
        sc = model.lscale
        rows = [f"{s.Name}: elevation {(s.Elevation or 0) * sc:.2f} m" + (f", floor-to-floor {((n.Elevation or 0) - (s.Elevation or 0)) * sc:.2f} m" if n else '')
                for s, n in zip(sts, sts[1:] + [None])]
        return R('\n'.join(rows), [], 'IfcBuildingStorey.Elevation differences', ["Sorted storeys by Elevation; height = next elevation − this elevation"])
    # --- rooms
    if cls_key == 'room' or re.search(r'\brooms?\b|spaces?|bedroom|bathroom|kitchen', ql):
        sp = model.elems(['IfcSpace'])
        area = lambda s: model.space_area(s)[0] or 0
        if re.search(r'largest|biggest', ql):
            s = max(sp, key=area)
            return R(f"The largest space is {model.label(s)} with {area(s):.2f} m².", [item(s, round(area(s), 2))], 'max IfcSpace net floor area',
                     [f"Compared net floor area of {len(sp)} IfcSpaces"])
        if re.search(r'names?|list', ql):
            return R("Spaces: " + ', '.join(sorted(model.label(s) for s in sp)), [item(s) for s in sp], 'IfcSpace names', [f"Listed {len(sp)} IfcSpace Name/LongName"])
        if re.search(r'bedroom|bathroom|kitchen|toilet|office', ql):
            w = re.search(r'bedroom|bathroom|kitchen|toilet|office', ql).group(0)
            m = [s for s in sp if w[:5] in model.label(s).lower()]
            return R(f"{len(m)} {w}s: " + ', '.join(model.label(s) for s in m), [item(s) for s in m], f'IfcSpace names containing “{w}”',
                     [f"Filtered {len(sp)} spaces by name"])
        if re.search(r'area|breakdown|distribution', ql):
            by = collections.defaultdict(list)
            for s in sp:
                st = model._storey(s); by[st.Name if st else '—'].append(s)
            lines = [f"{k}: {len(v)} spaces, {sum(area(s) for s in v):.1f} m²" for k, v in by.items()]
            tot = sum(area(s) for s in sp)
            return R(f"Total net floor area {tot:.1f} m² in {len(sp)} spaces.\n" + '\n'.join(lines), [item(s, round(area(s), 2)) for s in sp],
                     'sum of IfcSpace areas by storey', ["Grouped IfcSpaces by containing storey; summed net floor areas"])
    if not cls_key:
        cnt = collections.Counter(e.is_a() for e in f.by_type('IfcBuildingElement'))
        txt = "This is not directly answerable from the model's data. Model facts: " + ', '.join(f"{n} {c[3:]}" for c, n in cnt.most_common(8))
        return R(txt, [], 'model summary (no matching intent)', ["No element class or intent recognised; returned a model summary instead of guessing"])
    if not els:
        return R(f"No {noun} elements are present in the model.", [], f'count of {noun}', [f"Searched {'/'.join(CLASSES[cls_key])}: none"])
    steps.append(f"Selected {len(els)} {noun} elements ({'/'.join(CLASSES[cls_key])})")
    # --- extremes
    dim = 'OverallWidth' if re.search(r'wid|narrow', ql) else 'OverallHeight' if re.search(r'height|tall', ql) else None
    if dim and re.search(r'widest|greatest|largest|narrowest|smallest|tallest|highest|lowest|max|min', ql):
        vals = [(e, float(getattr(e, dim, None) or 0) * model.lscale) for e in els if getattr(e, dim, None)]
        rev = not re.search(r'narrowest|smallest|lowest|min', ql)
        vals.sort(key=lambda x: -x[1] if rev else x[1])
        k = 2 if re.search(r'\btwo\b|\b2\b', ql) else 1
        top = vals[:k]
        txt = '; '.join(f"{model.label(e)} ({e.GlobalId}): {v:.3f} m" for e, v in top)
        return R(txt, [item(e, round(v, 3)) for e, v in top], f'sorted by {dim}', [f"Sorted {len(vals)} elements by {dim}"])
    if dim and re.search(r'each|per type|sizes?|dimensions?', ql) or re.search(r'sizes?|dimensions?', ql):
        by = collections.defaultdict(list)
        for e in els: by[type_name(e)].append(e)
        fmt = lambda e: ' x '.join(f"{float(getattr(e, d)) * model.lscale:.2f} m" for d in ('OverallWidth', 'OverallHeight') if getattr(e, d, None))
        txt = '\n'.join(f"{k}: {fmt(v[0]) or 'no overall dimensions'} ({len(v)}×)" for k, v in by.items())
        return R(txt, [item(e) for e in els], 'OverallWidth/OverallHeight per type', ["Grouped by type; read OverallWidth/OverallHeight"])
    # --- totals
    if re.search(r'total|combined|sum', ql) and re.search(r'length|volume|area', ql):
        qn = 'Length' if 'length' in ql else 'NetVolume' if 'volume' in ql else 'NetSideArea' if cls_key == 'wall' else 'NetArea'
        vals = [(e, (model.q(e, qn, 'GrossVolume' if qn == 'NetVolume' else qn) or 0) * (model.lscale if qn == 'Length' else 1)) for e in els]
        tot = sum(v for _, v in vals)
        unit = {'Length': 'm', 'NetVolume': 'm³'}.get(qn, 'm²')
        by = collections.defaultdict(float)
        for e, v in vals: by[type_name(e)] += v
        txt = f"Total {qn} of {len(els)} {noun}s: {tot:.2f} {unit}." + ("\nBy type: " + '; '.join(f"{k}: {v:.2f}" for k, v in sorted(by.items(), key=lambda x: -x[1])[:12]) if len(by) > 1 else '')
        return R(txt, [item(e, round(v, 3)) for e, v in vals], f'sum of Qto {qn}', [f"Summed BaseQuantities {qn} over {len(els)} elements"])
    # --- materials
    if 'material' in ql:
        by = collections.defaultdict(list)
        for e in els:
            m = ue.get_material(e, should_skip_usage=True)
            names = []
            if m is not None:
                if m.is_a('IfcMaterial'): names = [m.Name]
                elif m.is_a('IfcMaterialLayerSet'): names = [l.Material.Name for l in m.MaterialLayers if l.Material]
                elif m.is_a('IfcMaterialList'): names = [x.Name for x in m.Materials]
                elif hasattr(m, 'ForLayerSet'): names = [l.Material.Name for l in m.ForLayerSet.MaterialLayers if l.Material]
            for n in names or ['(none)']: by[n].append(e)
        txt = '\n'.join(f"{k}: used by {len(v)} {noun}s" for k, v in sorted(by.items(), key=lambda x: -len(x[1])))
        return R(txt, [item(e) for e in els], 'IfcRelAssociatesMaterial', ["Collected material / layer-set names per element"])
    # --- thickness
    if 'thick' in ql:
        by = collections.defaultdict(list)
        for e in els:
            m = ue.get_material(e, should_skip_usage=True)
            t = None
            if m is not None and m.is_a('IfcMaterialLayerSet'): t = sum(l.LayerThickness for l in m.MaterialLayers)
            elif m is not None and hasattr(m, 'ForLayerSet'): t = sum(l.LayerThickness for l in m.ForLayerSet.MaterialLayers)
            by[(type_name(e), round(t * model.lscale * 1000) if t else None)].append(e)
        txt = '\n'.join(f"{k[0]}: {k[1]} mm ({len(v)}×)" if k[1] else f"{k[0]}: thickness not stated ({len(v)}×)" for k, v in by.items())
        return R(txt, [item(e) for e in els], 'material layer thickness per type', ["Summed IfcMaterialLayer thicknesses per wall type"])
    # --- load bearing
    if 'load' in ql and 'bearing' in ql:
        lb = [e for e in els if psv(e, 'LoadBearing') is True]
        nlb = [e for e in els if psv(e, 'LoadBearing') is False]
        return R(f"{len(lb)} load-bearing, {len(nlb)} non-load-bearing, {len(els) - len(lb) - len(nlb)} unspecified ({noun}s).", [item(e) for e in lb],
                 'Pset_*Common.LoadBearing', ["Read LoadBearing from Pset_WallCommon etc.; cited elements are the load-bearing ones"])
    if 'fire' in ql:
        fr = [(e, psv(e, 'FireRating')) for e in els]
        fr = [(e, v) for e, v in fr if v]
        txt = (f"{len(fr)} of {len(els)} {noun}s carry a FireRating: " + ', '.join(sorted({str(v) for _, v in fr}))) if fr else f"No {noun} in the model has a FireRating property."
        return R(txt, [item(e, v) for e, v in fr], 'Pset_*Common.FireRating', ["Read FireRating property"])
    # --- types with quantities (default for 'which/what types', 'list')
    if re.search(r'type|which|what|list|kinds?|present|installed|used|available', ql):
        by = collections.defaultdict(list)
        for e in els: by[type_name(e)].append(e)
        txt = f"{len(els)} {noun}s in {len(by)} types:\n" + '\n'.join(f"{k}: {len(v)}" for k, v in sorted(by.items(), key=lambda x: -len(x[1])))
        return R(txt, [item(e) for e in els], 'grouped by IfcTypeObject / ObjectType', ["Grouped elements by their type object (IfcRelDefinesByType) or ObjectType"])
    return R(f"There are {len(els)} {noun}s.", [item(e) for e in els], f'count of {noun}', [f"Counted {len(els)} distinct GlobalIds"])
