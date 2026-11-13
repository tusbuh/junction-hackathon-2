"""Deterministic IFC answer engine: counts and quantities straight from the model, with GlobalIds as evidence."""
import re, os, ifcopenshell, ifcopenshell.geom, ifcopenshell.util.element as ue, ifcopenshell.util.shape as us, ifcopenshell.util.unit as uu
TYPES = [  # (regex over question in en/et/da/de/fi, IFC classes)
 (r'sanitary|sanitaar|sanitet|sanitär', ['IfcSanitaryTerminal','IfcFlowTerminal']),
 (r'doors?\b|uks|ust\b|uste|døre|dør\b|türen|ovi', ['IfcDoor']),
 (r'windows?|aken|akna|vindue|fenster|ikkun', ['IfcWindow']),
 (r'rooms|spaces|ruum|rum\b|rummene|räume|huone', ['IfcSpace']),
 (r'walls?|sein|vægge|væg|wände|wand|seinte', ['IfcWall','IfcWallStandardCase']),
 (r'columns?|post|søjle|stütze|pilar', ['IfcColumn']),
 (r'beams?|tala|bjælke|träger|palk', ['IfcBeam']),
 (r'stairs?|trepp|trapp|treppe', ['IfcStair']),
 (r'slabs?|plaat|dæk|decke|laatta', ['IfcSlab']),
]
class Model:
    def __init__(self, path):
        self.f = ifcopenshell.open(path)
        self.storeys = {s.Name: s for s in self.f.by_type('IfcBuildingStorey')}
        self.lscale = uu.calculate_unit_scale(self.f)   # model length unit -> metres
        self.gs = ifcopenshell.geom.settings(); self.gs.set('use-world-coords', True)
    def footprint(self, e):
        try: return us.get_footprint_area(ifcopenshell.geom.create_shape(self.gs, e).geometry)
        except Exception: return None
    def space_area(self, s):
        a=self.q(s,'NetFloorArea')
        return (a, 'Qto NetFloorArea') if a else (self.footprint(s), 'computed from IfcSpace 3D geometry (footprint)')
    def elems(self, classes, storey=None):
        out=[]
        for c in classes:
            try: out += self.f.by_type(c, include_subtypes=False) if c=='IfcWall' else self.f.by_type(c)
            except RuntimeError: pass
        out=list({e.id():e for e in out}.values())
        # assemblies (e.g. a stair made of riser/flight sub-stairs) count once: drop parts aggregated into the same class
        out=[e for e in out if not ((a:=ue.get_aggregate(e)) is not None and a.is_a(e.is_a()))]
        if storey is not None:
            out=[e for e in out if self._storey(e)==storey]
        return out
    def _storey(self, e):
        c=ue.get_container(e) or (ue.get_aggregate(e) if e.is_a('IfcSpace') else None)
        while c is not None and not c.is_a('IfcBuildingStorey'):
            c=ue.get_aggregate(c) or ue.get_container(c)
        return c
    def q(self, e, *names):
        ps=ue.get_psets(e, qtos_only=True)
        for qto in ps.values():
            for n in names:
                if n in qto and qto[n]: return float(qto[n])
        return None
    def label(self, e):
        n = e.Name or ''
        ln = getattr(e, 'LongName', None)
        return f"{n} {ln}".strip() if ln and ln != n else (n or e.is_a())

    def answer(self, question):
        """Returns dict(value, unit, items[{gid,label,value}], method, steps)."""
        ql = question.lower()
        quoted = re.findall(r"[«“„']\s*([^»”“']+?)\s*[»”“']", question)
        storey = None
        for name, s in self.storeys.items():
            if name and any(name == x for x in quoted): storey = s
        self.last_storey = storey.Name if storey is not None else None
        st0 = [f"Opened {self.f.schema} model: {len(self.f.by_type('IfcProduct'))} products on {len(self.storeys)} storeys"]
        if storey is not None: st0.append(f"Filtered to storey “{storey.Name}” (IfcRelContainedInSpatialStructure)")
        it = lambda els, val=None: [dict(gid=e.GlobalId, label=self.label(e), cls=e.is_a(), value=val(e) if val else None,
                                         parts=[c.GlobalId for c in ue.get_decomposition(e) if hasattr(c, 'GlobalId')][:400]) for e in els]
        m = re.search(r"['„«]([^'“»]+?)\s*\((?:Rum nr\. )?([^()]+)\)['“»]", question)
        if m and re.search(r'area|pind|areal|fläche', ql):
            long, num = m.group(1).strip(), m.group(2).strip()
            sp = self.elems(['IfcSpace'], storey)
            norm = lambda x: re.sub(r'[^0-9a-zæøåäöüõšž]', '', (x or '').lower().replace('rum nr.', ''))
            cand = [s for s in sp if norm(s.Name) == norm(num) and norm(s.LongName) == norm(long)] \
                or [s for s in sp if norm(s.Name) == norm(num)]
            if cand:
                a, how = self.space_area(cand[0])
                steps = st0 + [f"Matched IfcSpace Name “{num}” / LongName “{long}” → {cand[0].GlobalId}", f"Area from {how}"]
                chk = None
                qa = self.q(cand[0], 'NetFloorArea')
                if qa:
                    g = self.footprint(cand[0])
                    if g:
                        chk = dict(printed=round(qa, 2), computed=round(g, 2), ok=abs(qa - g) <= 0.05 * qa, what='Qto vs 3D footprint')
                        steps.append(f"Cross-check: Qto {qa:.2f} m² vs 3D geometry footprint {g:.2f} m²")
                items = it(cand[:1], lambda e: round(a, 2) if a else None)
                items[0]['check'] = chk
                return dict(value=round(a, 3) if a else None, unit='m²', items=items, method=how, steps=steps)
            return dict(value=None, unit='m²', items=[], method='room not found', steps=st0 + ['No IfcSpace with that name'])
        cls = None
        for rx, c in TYPES:
            if re.search(rx, ql): cls = c; break
        if cls is None:
            return dict(value=None, unit=None, items=[], method='not routed', steps=st0 + ['No rule matched'])
        els = self.elems(cls, storey)
        st = st0 + [f"Selected {len(els)} elements of class {' / '.join(cls)}"]
        if re.search(r'length|pikkus|længde|länge', ql):
            v = lambda e: round((self.q(e, 'Length') or 0) * self.lscale, 3)
            return dict(value=round(sum(v(e) for e in els), 3), unit='m', items=it(els, v), method='sum of Qto Length', steps=st + ['Summed BaseQuantities Length (unit-scaled to m)'])
        if re.search(r'side area|külgpind|sideareal|seitenfläche', ql):
            v = lambda e: round(self.q(e, 'NetSideArea') or 0, 3)
            return dict(value=round(sum(v(e) for e in els), 3), unit='m²', items=it(els, v), method='sum of Qto NetSideArea', steps=st + ['Summed BaseQuantities NetSideArea'])
        if re.search(r'volume|maht|volumen|rumfang', ql):
            v = lambda e: round(self.q(e, 'NetVolume') or 0, 3)
            return dict(value=round(sum(v(e) for e in els), 3), unit='m³', items=it(els, v), method='sum of Qto NetVolume', steps=st + ['Summed BaseQuantities NetVolume'])
        if re.search(r'area|pind|areal|fläche', ql):
            v = lambda e: round(self.space_area(e)[0] or 0, 3)
            return dict(value=round(sum(v(e) for e in els), 2), unit='m²', items=it(els, v), method='sum of IfcSpace net floor areas', steps=st + ['Summed NetFloorArea (3D footprint when Qto missing)'])
        return dict(value=len(els), unit='count', items=it(els), method=f'count of {"/".join(cls)}', steps=st + [f"Counted {len(els)} distinct GlobalIds"])

    # ------------------------------------------------------------------ cross-checks (second, independent reading)
    def volume(self, e):
        try: return us.get_volume(ifcopenshell.geom.create_shape(self.gs, e).geometry)
        except Exception: pass
        parts = [p for p in ue.get_parts(e) or [] if p.is_a('IfcElement') and not p.is_a('IfcFeatureElement') and p.Representation is not None]
        vs = [self.volume(p) for p in parts[:50]]
        return sum(vs) if vs and all(v for v in vs) else None

    def xchecks(self, r, plan_svg=None):
        """Answer-level checks: Qto volumes vs mesh volume, counted elements vs the elements drawn on the 2D plan."""
        out = []
        items = [i for i in r.get('items') or [] if i.get('gid')]
        if r.get('unit') == 'm³' and 0 < len(items) <= 300:
            byid = {i['gid']: i for i in items}
            qs, gs, n = 0.0, 0.0, 0
            for gid, it in byid.items():
                e = self.f.by_guid(gid)
                v = self.volume(e)
                if v and it.get('value'):
                    qs += it['value']; gs += v; n += 1
                    it['check'] = dict(printed=round(it['value'], 3), computed=round(v, 3), ok=abs(v - it['value']) <= max(0.05 * it['value'], 0.01),
                                       what='Qto vs 3D mesh volume')
            if n:
                out.append(dict(what='Σ Qto NetVolume vs Σ 3D mesh volume', printed=round(qs, 2), computed=round(gs, 2), unit='m³',
                                ok=abs(qs - gs) <= 0.05 * max(qs, 1e-9), note=f'{n} of {len(items)} elements measured from their geometry'))
        if r.get('unit') == 'count' and plan_svg and items:
            try:
                txt = open(plan_svg, encoding='utf-8', errors='replace').read()
                drawn = set(re.findall(r'data-guid="([^"]+)"', txt))
            except Exception:
                drawn = set()
            if drawn and any(i['gid'] in drawn or any(p in drawn for p in i.get('parts') or []) for i in items):
                hit = sum(1 for i in items if i['gid'] in drawn or any(p in drawn for p in i.get('parts') or []))
                out.append(dict(what='counted in the model vs drawn on the 2D plan', printed=len(items), computed=hit, unit='count',
                                ok=hit == len(items), note=f"{os.path.basename(plan_svg)}: {hit} of {len(items)} GlobalIds appear on the sheet"))
        return out
