"""Tessellate an IFC model once (ifcopenshell.geom, world coords) into one compact binary blob for three.js.

Layout of <cache>/<stem>.mesh.bin:
  uint32 header_len | header JSON (utf-8) | float32 positions (x,y,z, Z-up metres) | uint32 indices
header = {"elements": [{gid, cls, name, storey, v0, nv, i0, ni, rgb}], "bbox": [...]}
The browser recolours an element's vertex range [v0, v0+nv) to highlight it, so one draw call
renders the whole building and highlighting stays instant even for 70 MB models.
"""
import json, os, struct, sys, time, multiprocessing
import numpy as np
import ifcopenshell, ifcopenshell.geom, ifcopenshell.util.element as ue

SKIP = {'IfcOpeningElement', 'IfcSpace', 'IfcAnnotation', 'IfcGrid', 'IfcVirtualElement'}
PALETTE = {  # calm architectural palette (linear-ish sRGB 0..1)
    'IfcWall': (0.86, 0.85, 0.82), 'IfcWallStandardCase': (0.86, 0.85, 0.82),
    'IfcSlab': (0.70, 0.71, 0.73), 'IfcRoof': (0.62, 0.45, 0.38), 'IfcCovering': (0.78, 0.77, 0.74),
    'IfcWindow': (0.55, 0.75, 0.92), 'IfcDoor': (0.72, 0.56, 0.40), 'IfcStair': (0.66, 0.66, 0.70),
    'IfcStairFlight': (0.66, 0.66, 0.70), 'IfcRailing': (0.45, 0.47, 0.50), 'IfcColumn': (0.80, 0.80, 0.82),
    'IfcBeam': (0.74, 0.74, 0.76), 'IfcFurnishingElement': (0.80, 0.70, 0.55),
    'IfcFlowTerminal': (0.92, 0.94, 0.97), 'IfcSanitaryTerminal': (0.92, 0.94, 0.97),
    'IfcFlowSegment': (0.40, 0.65, 0.55), 'IfcPipeSegment': (0.40, 0.65, 0.55), 'IfcFlowFitting': (0.35, 0.58, 0.50),
    'IfcPlate': (0.60, 0.78, 0.90), 'IfcMember': (0.55, 0.55, 0.58),
}


def storey_of(e):
    c = ue.get_container(e)
    while c is not None and not c.is_a('IfcBuildingStorey'):
        c = ue.get_aggregate(c) or ue.get_container(c)
    return c.Name if c is not None else None


def build(ifc_path, out_path, include_spaces=True):
    t = time.time()
    f = ifcopenshell.open(ifc_path)
    s = ifcopenshell.geom.settings()
    s.set('use-world-coords', True)
    s.set('weld-vertices', True)
    s.set('apply-default-materials', True)
    it = ifcopenshell.geom.iterator(s, f, multiprocessing.cpu_count())
    pos, idx, elements = [], [], []
    nv = ni = 0
    if it.initialize():
        while True:
            sh = it.get()
            e = f.by_id(sh.id)
            cls = e.is_a()
            if cls in SKIP and not (include_spaces and cls == 'IfcSpace'):
                if not it.next(): break
                continue
            g = sh.geometry
            v = np.asarray(g.verts, dtype=np.float32)
            fa = np.asarray(g.faces, dtype=np.uint32)
            if len(v) and len(fa):
                rgb = PALETTE.get(cls)
                if rgb is None:
                    try:
                        m = g.materials[0]
                        rgb = tuple(float(c) for c in m.diffuse.components) if hasattr(m.diffuse, 'components') else tuple(m.diffuse)
                    except Exception:
                        rgb = (0.75, 0.75, 0.75)
                elements.append(dict(gid=e.GlobalId, cls=cls, name=e.Name, storey=storey_of(e),
                                     v0=nv, nv=len(v) // 3, i0=ni, ni=len(fa), rgb=[round(c, 3) for c in rgb[:3]]))
                pos.append(v); idx.append(fa + nv)
                nv += len(v) // 3; ni += len(fa)
            if not it.next():
                break
    P = np.concatenate(pos) if pos else np.zeros(0, np.float32)
    I = np.concatenate(idx) if idx else np.zeros(0, np.uint32)
    P3 = P.reshape(-1, 3)
    hdr = dict(elements=elements, bbox=[*P3.min(0).tolist(), *P3.max(0).tolist()] if len(P3) else None,
               schema=f.schema, secs=round(time.time() - t, 1))
    hb = json.dumps(hdr, separators=(',', ':')).encode()
    hb += b' ' * ((4 - len(hb) % 4) % 4)
    with open(out_path, 'wb') as fo:
        fo.write(struct.pack('<I', len(hb))); fo.write(hb); fo.write(P.tobytes()); fo.write(I.tobytes())
    return hdr


if __name__ == '__main__':
    out = sys.argv[2]
    h = build(sys.argv[1], out)
    print(os.path.basename(sys.argv[1]), len(h['elements']), 'elements', h['secs'], 's', os.path.getsize(out) // 1024, 'KB')
