"""Deterministic answer engine for vector floor plans (Swiss Dwellings DXF+PDF).
Every answer returns evidence: list of (label, bbox in DXF metres) that we map onto the PDF page."""
import re, ezdxf, numpy as np
from ezdxf import bbox as ebbox
from shapely.geometry import Polygon, Point, box

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
        for b in bowls:
            h=[x for x in hinges if touch(b,x)]
            (self.wc if h else self.basin).append(b)
        # showers: closed square tray containing a drain circle, not inside a tub
        drains=[(e.dxf.center.x,e.dxf.center.y) for e in fx if e.dxftype()=='CIRCLE' and e.dxf.radius<0.05]
        for e in fx:
            if e.dxftype()=='LWPOLYLINE' and e.closed:
                b=bb(e); w=b[2]-b[0]; h=b[3]-b[1]
                if 0.7<w<1.3 and 0.7<h<1.3 and max(w,h)/min(w,h)<1.4 and any(b[0]<x<b[2] and b[1]<y<b[3] for x,y in drains) \
                   and not any(t[0]<=b[0]+.05 and t[2]>=b[2]-.05 for t in self.tub):
                    self.shower.append(b)
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
            near=[o for o in others if abs(o[1]-x)<0.05 and 0<o[2]-y<0.6 and not AREA_RE.match(o[0]) and not UNIT_RE.match(o[0])]
            near.sort(key=lambda o:o[2]-y)
            name=near[0][0] if near else None
            lab=[o for o in others if abs(o[1]-x)<0.05 and 0<y-o[2]<0.6 and AREA_RE.match(o[0])]
            printed=float(AREA_RE.match(lab[0][0]).group(1)) if lab else None
            geo=round(poly.area,2) if poly else None
            unit=None
            if poly:
                for u,up in units:
                    if up.buffer(0.05).contains(poly.representative_point()): unit=u
            bbx=poly.bounds if poly else b
            self.rooms.append(dict(num=num,name=name,area=geo if geo else printed,printed=printed,unit=unit,bbox=bbx,
                                   poly=list(poly.exterior.coords) if poly else None))

    def answer(self, q):
        """returns (value, evidence [(label,bbox)], method). Multilingual keyword router; LLM router only as fallback."""
        ql=q.lower()
        quoted=re.findall(r"[«“„]\s*([^»”“]+?)\s*[»”“]|'([^']+(?:'[a-zé][^']*)?)'",q)
        quoted=[a or b for a,b in quoted]
        def ev(lst,label): return [(label,b) for b in lst]
        def R(x): return [(f"{r['num']} {r['name'] or ''} {r['area']} m²",r['bbox']) for r in x]
        indoor=lambda r: r['area'] and (r['name'] or '').lower() not in OUTDOOR
        is_area = re.search(r'm²|area|fläche|surface|superficie',ql)
        m=re.search(r"(?:room|raum|pièce|locale)\s+(U?\d+\.\d+)",ql,re.I)
        if m and is_area:
            r=[r for r in self.rooms if r['num'].lower()==m.group(1)]
            return (r[0]['area'] if r else None), R(r), 'room polygon area'
        m=re.search(r"(?:apartment|wohnung|appartement|appartamento)\s+([a-z])\b",ql)
        if m and is_area:
            r=[r for r in self.rooms if r['unit']==m.group(1).upper() and indoor(r)]
            return round(sum(x['area'] for x in r),2), R(r), 'sum of room polygons in apartment outline'
        if quoted and re.search(r'labelled|bezeichnung|désignation|désignées|denominazione|denominati',ql):
            lab=quoted[0]
            r=[r for r in self.rooms if r['name']==lab]
            if is_area: return round(sum(x['area'] or 0 for x in r),2), R(r), 'sum of labelled room polygons'
            return len(r), R(r), 'room name labels'
        if is_area and re.search(r'numbered|nummerierten|numérotées|numerati|interni|intérieures',ql):
            r=[r for r in self.rooms if indoor(r)]
            return round(sum(x['area'] for x in r),2), R(r), 'sum of indoor room polygons'
        if re.search(r'apartments|wohnungen|appartements|appartamenti',ql):
            labs=[t for t in self.texts if UNIT_RE.match(t[0])]
            return len(labs), [(t[0],t[3]) for t in labs], 'apartment labels'
        if re.search(r'\bdoors\b|türen|portes|porte\b',ql): return len(self.doors), ev(self.doors,'door'), 'door swing arcs'
        if re.search(r'windows|fenster|fenêtres|finestre',ql): return len(self.windows), ev(self.windows,'window'), 'window symbols'
        if re.search(r'washbasin|lavabo|lavabi',ql): return len(self.basin), ev(self.basin,'basin'), 'basin symbols'
        if re.search(r'toilets|\bwc',ql): return len(self.wc), ev(self.wc,'WC'), 'WC symbols (bowl+seat line)'
        if re.search(r'bathtub|badewanne|baignoire|vasche|vasca',ql): return len(self.tub), ev(self.tub,'bathtub'), 'bathtub symbols'
        if re.search(r'shower|dusche|douche|docce|doccia',ql): return len(self.shower), ev(self.shower,'shower'), 'shower trays'
        return None, [], 'not routed -> LLM fallback'
