"""Deterministic answer engine for vector floor plans (Swiss Dwellings DXF+PDF).
Every answer returns evidence: list of (label, bbox in DXF metres) that we map onto the PDF page."""
import re, ezdxf, numpy as np
from ezdxf import bbox as ebbox
from shapely.geometry import Polygon, Point, box

# Parse one entity query at import time (single-threaded, under the import lock) so pyparsing settles the arity of
# ezdxf's parse actions before request threads run their first queries concurrently. Seen once after a cold restart:
# "TypeError: <lambda>() missing 1 required positional argument: 't'" from msp.query(); not reproduced since.
try:
    from ezdxf.query import entity_matcher as _em
    _em('LWPOLYLINE[layer=="DOOR"]')
except Exception:
    pass

OUTDOOR = {'balcon','balcone','balkon','loggia','terrasse','terrazza'}
UNIT_RE = re.compile(r'^(Whg\.|App\.)\s*([A-Z])$')
NUM_RE = re.compile(r'^U?\d+\.\d+$')
AREA_RE = re.compile(r'^([\d.]+)\s*m²$')

def bb(e):
    b = ebbox.extents([e]); return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)

def groups(boxes, tol=0.05):
    """union-find merge of overlapping bboxes -> one group per drawn symbol"""
    n=len(boxes); par=list(range(n))
    def f(i):
        while par[i]!=i: par[i]=par[par[i]]; i=par[i]
        return i
    for i in range(n):
        a=boxes[i]
        for j in range(i+1,n):
            b=boxes[j]
            if a[0]-tol<=b[2] and b[0]-tol<=a[2] and a[1]-tol<=b[3] and b[1]-tol<=a[3]:
                par[f(i)]=f(j)
    out={}
    for i in range(n): out.setdefault(f(i),[]).append(boxes[i])
    return [(min(b[0] for b in g),min(b[1] for b in g),max(b[2] for b in g),max(b[3] for b in g)) for g in out.values()]

class Plan:
    def __init__(self, dxf):
        self.msp = ezdxf.readfile(dxf).modelspace()
        q = lambda layer, t='*': list(self.msp.query(f'{t}[layer=="{layer}"]'))
        self.doors = [bb(e) for e in q('DOOR','LWPOLYLINE') if len(e)==5]   # one door-leaf outline per door
        self.windows = [bb(e) for e in q('WINDOW','LWPOLYLINE') if len(e)==4 and e.closed]  # one frame per window
        self.units_poly = [Polygon([(p[0],p[1]) for p in e.get_points()]) for e in q('UNIT_OUTLINE','LWPOLYLINE')]
        self.texts = [(e.dxf.text.strip(), e.dxf.insert.x, e.dxf.insert.y, bb(e)) for e in q('ROOM_TEXT','TEXT')]
        # fixtures: classify open polylines by vertex count + aspect
        self.wc=[]; self.basin=[]; self.tub=[]; self.shower=[]
        fx = q('FIXTURE')
        bowls=[]; hinges=[]
        for e in fx:
            if e.dxftype()!='LWPOLYLINE' or e.closed: continue
            n=len(e); b=bb(e)
            if n==69: self.tub.append(b)
            elif n==48: bowls.append(b)
            elif n==2:
                L=max(b[2]-b[0],b[3]-b[1])
                if 0.3<L<0.6: hinges.append(b)
        def touch(a,b,t=0.08): return a[0]-t<=b[2] and b[0]-t<=a[2] and a[1]-t<=b[3] and b[1]-t<=a[3]
        # showers: closed square tray containing a drain circle, not inside a tub
        drains=[(e.dxf.center.x,e.dxf.center.y) for e in fx if e.dxftype()=='CIRCLE' and e.dxf.radius<0.05]
        # bowl with a drain circle inside = washbasin; bowl without = WC (130/130 on preview)
        for b in bowls:
            (self.basin if any(b[0]<x<b[2] and b[1]<y<b[3] for x,y in drains) else self.wc).append(b)
        # showers: a free drain circle (r≈0.045 m; hob burners are 0.08) not inside a basin, WC or bathtub;
        # evidence box = smallest closed tray outline around it, else a 0.9 m square
        trays=[bb(e) for e in fx if e.dxftype()=='LWPOLYLINE' and e.closed]
        inn=lambda x,y,b: b[0]<x<b[2] and b[1]<y<b[3]
        for x,y in drains:
            if any(inn(x,y,b) for b in self.basin+self.wc+self.tub): continue
            t=sorted([b for b in trays if inn(x,y,b) and (b[2]-b[0])<1.6 and (b[3]-b[1])<1.6],key=lambda b:(b[2]-b[0])*(b[3]-b[1]))
            self.shower.append(t[0] if t else (x-.45,y-.45,x+.45,y+.45))
        self._rooms()
    def _rooms(self):
        from ezdxf import path as epath
        polys=[]
        for e in self.msp.query('LWPOLYLINE[layer=="ROOM_OUTLINE"]'):
            pts=[(v.x,v.y) for v in epath.make_path(e).flattening(0.005)]
            if len(pts)>=3: polys.append(Polygon(pts).buffer(0))
        units=[]
        for t,x,y,_ in self.texts:
            m=UNIT_RE.match(t)
            if m:
                for up in self.units_poly:
                    if up.contains(Point(x,y)): units.append((m.group(2),up))
        nums=[t for t in self.texts if NUM_RE.match(t[0])]
        others=[t for t in self.texts if not NUM_RE.match(t[0])]
        self.rooms=[]
        for num,x,y,b in nums:
            pt=Point(x,y)
            cand=sorted([p for p in polys if p.contains(pt)],key=lambda p:p.area)
            poly=cand[0] if cand else None
            holes=[]
            if poly is not None:
                # enclosed rooms (a lift shaft inside a stair hall) are islands: subtract them (550/550 printed labels agree)
                inner=[p for p in polys if p.area<poly.area-1e-6 and poly.buffer(0.01).contains(p)]
                if inner:
                    from shapely.ops import unary_union
                    cut=poly.difference(unary_union(inner))
                    if not cut.is_empty and cut.geom_type=='Polygon':
                        holes=[list(i.coords) for i in cut.interiors]; poly=cut
                    elif not cut.is_empty:
                        holes=[list(p.exterior.coords) for p in inner]; poly=Polygon(poly.exterior.coords, holes)
            near=[o for o in others if abs(o[1]-x)<0.05 and 0<o[2]-y<0.6 and not AREA_RE.match(o[0]) and not UNIT_RE.match(o[0])]
            near.sort(key=lambda o:o[2]-y)
            name=near[0][0] if near else None
            lab=[o for o in others if abs(o[1]-x)<0.05 and 0<y-o[2]<0.6 and AREA_RE.match(o[0])]
            printed=float(AREA_RE.match(lab[0][0]).group(1)) if lab else None
            geo=round(poly.area,2) if poly else None
            unit=None; inunit=False
            if poly:
                # a room belongs to the smallest UNIT_OUTLINE around it; a nested outline without a Whg./App. label
                # (e.g. a shared corridor drawn inside an apartment's outline) owns its rooms, so they are in no apartment
                rp=poly.representative_point()
                own=sorted([up for up in self.units_poly if up.buffer(0.05).contains(rp)],key=lambda up:up.area)
                if own:
                    inunit=True
                    unit=next((u for u,up in units if up is own[0]),None)
            bbx=poly.bounds if poly else b
            # an unlabelled (no name, no printed m²) strip under 1.3 m wide inside an apartment, with at most 2 doors and
            # no sanitary fixture, is a loggia / service shaft drawn outside the facade line: not net floor area
            shaft=False
            if poly is not None and name is None and printed is None and inunit and min(bbx[2]-bbx[0],bbx[3]-bbx[1])<1.3 and poly.area>=1.0:
                g=poly.buffer(0.05)
                nd=sum(box(*d).intersects(g) for d in self.doors)
                nf=sum(box(*d).intersects(poly) for d in self.wc+self.basin+self.tub+self.shower)
                shaft=nd<=2 and nf==0
            self.rooms.append(dict(num=num,name=name,area=geo if geo else printed,printed=printed,unit=unit,bbox=bbx,
                                   poly=list(poly.exterior.coords) if poly else None,holes=holes,shaft=shaft))

    # ------------------------------------------------------------------ answering
    def answer(self, q):
        """Multilingual keyword router -> exact lookup over the geometry index.
        Returns dict(value, unit, items, method, steps, checks); items carry DXF-space bbox/poly."""
        ql = q.lower()
        quoted = re.findall(r"[«“„]\s*([^»”“]+?)\s*[»”“]|'([^']+(?:'[a-zé][^']*)?)'", q)
        quoted = [a or b for a, b in quoted]
        is_area = re.search(r'm²|area|fläche|surface|superficie', ql)
        indoor = lambda r: r['area'] and (r['name'] or '').lower() not in OUTDOOR and not r.get('shaft')

        def rooms(lst, how):
            items = []
            for r in lst:
                chk = None
                if r['printed'] is not None and r['area'] is not None:
                    d = abs(r['printed'] - r['area'])
                    chk = dict(printed=r['printed'], computed=r['area'], ok=d <= max(0.02 * r['printed'], 0.06))
                items.append(dict(kind='room', label=f"{r['num']} {r['name'] or ''}".strip(), value=r['area'],
                                  bbox=r['bbox'], poly=r['poly'], holes=r.get('holes') or None, check=chk))
            steps = [f"Read {len(self.rooms)} numbered rooms from DXF layer ROOM_TEXT; each matched to the smallest ROOM_OUTLINE polygon around its label",
                     how]
            checks = [i['check'] for i in items if i['check']]
            if checks:
                bad = sum(not c['ok'] for c in checks)
                steps.append(f"Cross-check: printed m² label vs computed polygon area on {len(checks)} rooms: "
                             + ("all agree within 2%" if not bad else f"{bad} disagree (amber)"))
            return items, steps

        def excluded(lst):
            out = []
            for r in lst:
                if not r['area'] or indoor(r): continue
                why = 'outdoor space (balcony/loggia/terrace)' if (r['name'] or '').lower() in OUTDOOR else \
                      'unlabelled strip < 1.3 m wide, no fixtures: loggia / shaft, not net floor area'
                out.append(dict(kind='excluded', label=f"{r['num']} {r['name'] or '(no label)'}".strip(), value=r['area'],
                                bbox=r['bbox'], poly=r['poly'], reason=why))
            return out

        def syms(lst, kind, how, layer):
            return dict(value=len(lst), unit='count', items=[dict(kind=kind, label=f"{kind} {i+1}", bbox=b) for i, b in enumerate(lst)],
                        method=how, steps=[f"Parsed DXF layer {layer}", how, f"Counted {len(lst)} distinct symbols"])

        m = re.search(r"(?:room|raum|pièce|locale)\s+(U?\d+\.\d+)", ql, re.I)
        if m and is_area:
            r = [r for r in self.rooms if r['num'].lower() == m.group(1)]
            it, st = rooms(r, f"Room {m.group(1)}: area = shoelace area of its outline polygon")
            return dict(value=r[0]['area'] if r else None, unit='m²', items=it, method='room polygon area', steps=st)
        m = re.search(r"(?:apartment|wohnung|appartement|appartamento)\s+([a-z])\b", ql)
        if m and is_area:
            u = m.group(1).upper()
            r = [r for r in self.rooms if r['unit'] == u and indoor(r)]
            it, st = rooms(r, f"Kept the {len(r)} indoor rooms inside apartment {u}'s UNIT_OUTLINE (balconies/loggias/terraces excluded), summed polygon areas")
            return dict(value=round(sum(x['area'] for x in r), 2), unit='m²', items=it, excluded=excluded([x for x in self.rooms if x['unit'] == u]),
                        method=f'sum of room polygons in apartment {u}', steps=st)
        if quoted and re.search(r'labelled|bezeichnung|désignation|désignées|denominazione|denominati', ql):
            lab = quoted[0]
            r = [r for r in self.rooms if r['name'] == lab]
            it, st = rooms(r, f"Selected rooms whose name label is exactly “{lab}”: {len(r)}")
            if is_area:
                return dict(value=round(sum(x['area'] or 0 for x in r), 2), unit='m²', items=it, method='sum of labelled room polygons', steps=st)
            return dict(value=len(r), unit='count', items=it, method='room name labels', steps=st)
        if is_area and re.search(r'numbered|nummerierten|numérotées|numerati|interni|intérieures', ql):
            r = [r for r in self.rooms if indoor(r)]
            it, st = rooms(r, f"Kept {len(r)} indoor numbered rooms (outdoor spaces excluded), summed polygon areas")
            return dict(value=round(sum(x['area'] for x in r), 2), unit='m²', items=it, excluded=excluded(self.rooms), method='sum of indoor room polygons', steps=st)
        if re.search(r'apartments|wohnungen|appartements|appartamenti', ql):
            labs = [t for t in self.texts if UNIT_RE.match(t[0])]
            items = []
            for t in labs:
                poly = next((list(up.exterior.coords) for up in self.units_poly if up.contains(Point(t[1], t[2]))), None)
                items.append(dict(kind='apartment', label=t[0], bbox=Polygon(poly).bounds if poly else t[3], poly=poly))
            return dict(value=len(labs), unit='count', items=items, method='apartment labels inside UNIT_OUTLINE',
                        steps=["Found apartment labels (Whg./App. + letter) on layer ROOM_TEXT", f"{len(labs)} labels, each inside its own UNIT_OUTLINE polygon"])
        if re.search(r'\bdoors\b|türen|portes|porte\b', ql):
            return syms(self.doors, 'door', 'one 5-vertex door-leaf outline per door', 'DOOR')
        if re.search(r'windows|fenster|fenêtres|finestre', ql):
            return syms(self.windows, 'window', 'one closed 4-vertex frame per window', 'WINDOW')
        if re.search(r'washbasin|lavabo|lavabi', ql):
            return syms(self.basin, 'basin', 'bowl symbol (48-vertex) with a drain circle inside = washbasin', 'FIXTURE')
        if re.search(r'toilets|\bwc', ql):
            return syms(self.wc, 'WC', 'bowl symbol (48-vertex) with no drain circle = WC (basins have one)', 'FIXTURE')
        if re.search(r'bathtub|badewanne|baignoire|vasche|vasca', ql):
            return syms(self.tub, 'bathtub', 'bathtub outline (69-vertex polyline)', 'FIXTURE')
        if re.search(r'shower|dusche|douche|docce|doccia', ql):
            return syms(self.shower, 'shower', 'free floor-drain circle (r≈4.5 cm) not inside a basin, WC or bathtub', 'FIXTURE')
        return dict(value=None, unit=None, items=[], method='not routed', steps=['No rule matched this question'])
