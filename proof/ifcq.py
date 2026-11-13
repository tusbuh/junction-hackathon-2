"""Deterministic IFC answer engine: counts and quantities straight from the model, with GlobalIds as evidence."""
import re, ifcopenshell, ifcopenshell.geom, ifcopenshell.util.element as ue, ifcopenshell.util.shape as us, ifcopenshell.util.unit as uu
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
    def answer(self, question):
        ql=question.lower()
        quoted=re.findall(r"[«“„']\s*([^»”“']+?)\s*[»”“']",question)
        storey=None
        for name,s in self.storeys.items():
            if name and any(name==x for x in quoted): storey=s
        # room area by name 'LONG (NUM)'
        m=re.search(r"['„«]([^'“»]+?)\s*\((?:Rum nr\. )?([^()]+)\)['“»]",question)
        if m and re.search(r'area|pind|areal|fläche',ql):
            long,num=m.group(1).strip(),m.group(2).strip()
            sp=self.elems(['IfcSpace'],storey)
            cand=[s for s in sp if (s.Name or '').replace('Rum nr. ','')==num and (s.LongName or '').strip()==long] \
                 or [s for s in sp if (s.Name or '').replace('Rum nr. ','')==num]
            if cand:
                a,how=self.space_area(cand[0])
                return (round(a,3) if a else None),[cand[0].GlobalId],how
            return None,[],'room not found'
        cls=None
        for rx,c in TYPES:
            if re.search(rx,ql): cls=c; break
        if cls is None: return None,[],'not routed'
        els=self.elems(cls, storey)
        if re.search(r'length|pikkus|længde|länge',ql):
            return round(sum(self.q(e,'Length') or 0 for e in els)*self.lscale,3),[e.GlobalId for e in els],'sum Qto Length'
        if re.search(r'side area|külgpind|sideareal|seitenfläche',ql):
            return round(sum(self.q(e,'NetSideArea') or 0 for e in els),3),[e.GlobalId for e in els],'sum Qto NetSideArea'
        if re.search(r'volume|maht|volumen|rumfang',ql):
            return round(sum(self.q(e,'NetVolume') or 0 for e in els),3),[e.GlobalId for e in els],'sum Qto NetVolume'
        if re.search(r'area|pind|areal|fläche',ql):
            return round(sum(self.space_area(e)[0] or 0 for e in els),2),[e.GlobalId for e in els],'sum of IfcSpace net floor areas'
        return len(els),[e.GlobalId for e in els],f'count of {"/".join(cls)}'
