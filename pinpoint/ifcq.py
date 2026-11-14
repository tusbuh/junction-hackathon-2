"""Deterministic IFC answer engine: counts and quantities straight from the model, with GlobalIds as evidence."""
import re, ifcopenshell, ifcopenshell.geom, ifcopenshell.util.element as ue, ifcopenshell.util.shape as us, ifcopenshell.util.unit as uu
TYPES = [  # (regex over question in en/et/da/de/fi/nl, IFC classes); quoted names are removed before matching
 (r'light fixtures?|luminaires?|leuchten|valaisi|verlichtingsarmatu|armaturen', ['IfcLightFixture','IfcFlowTerminal']),
 (r'sanitary|sanitaar|sanitet|sanitär|sanitaire', ['IfcSanitaryTerminal','IfcFlowTerminal']),
 (r'doors?\b|uks|ust\b|uste|døre|dør\b|türen|ovi|deuren|deur\b', ['IfcDoor']),
 (r'windows?|aken|akna|vindue|fenster|ikkun|ramen\b|raam', ['IfcWindow']),
 (r'rooms|spaces|ruum|rum\b|rummene|räume|huone|ruimtes?\b|vertrekken', ['IfcSpace']),
 (r'walls?|sein|vægge|væg|wände|wand|seinte|wanden|muren', ['IfcWall','IfcWallStandardCase']),
 (r'columns?|post|søjle|stütze|pilar|kolom', ['IfcColumn']),
 (r'beams?|tala|bjælke|träger|palk|balken|balk\b|liggers?', ['IfcBeam']),
 (r'stairs?|trepp|trapp|treppe|trappen', ['IfcStair']),
 (r'slabs?|plaat|dæk|decke|laatta|vloeren|platen', ['IfcSlab']),
]
AREA_RX = r'area|pind|areal|fläche|oppervlak|superficie|área|powierzchni|suprafa|pinta-ala'


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
        typed_terms = 'IfcFlowTerminal' in classes and ('IfcSanitaryTerminal' in classes or 'IfcLightFixture' in classes)
        for c in classes:
            if c == 'IfcFlowTerminal' and typed_terms:
                continue
            try: out += self.f.by_type(c, include_subtypes=False) if c=='IfcWall' else self.f.by_type(c)
            except RuntimeError: pass
        # IFC2x3 has no IfcSanitaryTerminal / IfcLightFixture occurrences: they are IfcFlowTerminals typed by
        # IfcSanitaryTerminalType / IfcLightFixtureType. Keep only the terminals whose type matches.
        if typed_terms:
            want = {f'{c}Type' for c in classes if c != 'IfcFlowTerminal'}
            ft = self.f.by_type('IfcFlowTerminal') if self.f.schema == 'IFC2X3' else []
            typed = [(e, ue.get_type(e)) for e in ft]
            if any(t is not None for _, t in typed):
                out += [e for e, t in typed if t is not None and t.is_a() in want]
            elif 'IfcFlowTerminal' in classes:
                out += ft
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
        if m and re.search(AREA_RX, ql):
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
                        chk = dict(printed=round(qa, 2), computed=round(g, 2), ok=abs(qa - g) <= 0.03 * qa, what='Qto vs 3D footprint')
                        steps.append(f"Cross-check: Qto {qa:.2f} m² vs 3D geometry footprint {g:.2f} m²")
                items = it(cand[:1], lambda e: round(a, 2) if a else None)
                items[0]['check'] = chk
                return dict(value=round(a, 3) if a else None, unit='m²', items=items, method=how, steps=steps)
            return dict(value=None, unit='m²', items=[], method='room not found', steps=st0 + ['No IfcSpace with that name'])
        # route on the question without its quoted names: a model called "Gymzaal Hambakendreef" must not
        # match the Estonian "aken" (window)
        qr = re.sub(r"[«“„'\"]\s*[^»”“'\"]+?\s*[»”“'\"]", ' ', question).lower()
        if True:
            # a single room by its quoted name ("the room 'Schacht 5' on 'OG1'")
            names = [x for x in quoted if x not in self.storeys]
            if names and re.search(r'room|raum|raums|ruum|rum\b|huone|ruimte|pièce|habitaci|stanza|pomieszcz|încăper', ql) \
                    and re.search(AREA_RX, ql) and not re.search(r'all |alle |kõigi|kaikkien|alle ', ql):
                norm = lambda x: re.sub(r'[^0-9a-zæøåäöüõšž]', '', (x or '').lower())
                sp = self.elems(['IfcSpace'], storey)
                cand = [x for x in sp if any(norm(x.Name) == norm(n) or norm(getattr(x, 'LongName', None)) == norm(n) for n in names)]
                if len(cand) == 1:
                    a, how = self.space_area(cand[0])
                    steps = st0 + [f"Matched IfcSpace “{self.label(cand[0])}” by its quoted name → {cand[0].GlobalId}", f"Area from {how}"]
                    return dict(value=round(a, 3) if a else None, unit='m²', items=it(cand, lambda e: round(a, 2) if a else None), method=how, steps=steps)
        cls = None
        for rx, c in TYPES:
            if re.search(rx, qr): cls = c; break
        if cls is None:
            return dict(value=None, unit=None, items=[], method='not routed', steps=st0 + ['No rule matched'])
        els = self.elems(cls, storey)
        st = st0 + [f"Selected {len(els)} elements of class {' / '.join(cls)}"]
        if re.search(r'lengte|length|how long|pikkus|kui pikk|længde|hvor lang|länge|wie lang|lengte|hoe lang|längd|hur lång|pituus|kuinka pitk|longueur|lunghezza|longitud', ql):
            v = lambda e: round((self.q(e, 'Length') or 0) * self.lscale, 3)
            return dict(value=round(sum(v(e) for e in els), 3), unit='m', items=it(els, v), method='sum of Qto Length', steps=st + ['Summed BaseQuantities Length (unit-scaled to m)'])
        if re.search(r'side area|külgpind|sideareal|seitenfläche|zijoppervlak', ql):
            v = lambda e: round(self.q(e, 'NetSideArea') or 0, 3)
            return dict(value=round(sum(v(e) for e in els), 3), unit='m²', items=it(els, v), method='sum of Qto NetSideArea', steps=st + ['Summed BaseQuantities NetSideArea'])
        if re.search(r'volume|maht|volumen|rumfang|tilavuus|volym|inhoud', ql):
            v = lambda e: round(self.q(e, 'NetVolume') or 0, 3)
            return dict(value=round(sum(v(e) for e in els), 3), unit='m³', items=it(els, v), method='sum of Qto NetVolume', steps=st + ['Summed BaseQuantities NetVolume'])
        if re.search(AREA_RX, ql):
            v = lambda e: round(self.space_area(e)[0] or 0, 3)
            return dict(value=round(sum(v(e) for e in els), 2), unit='m²', items=it(els, v), method='sum of IfcSpace net floor areas', steps=st + ['Summed NetFloorArea (3D footprint when Qto missing)'])
        return dict(value=len(els), unit='count', items=it(els), method=f'count of {"/".join(cls)}', steps=st + [f"Counted {len(els)} distinct GlobalIds"])
