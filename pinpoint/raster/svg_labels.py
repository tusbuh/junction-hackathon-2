"""Parse CubiCasa5K model.svg annotations into object boxes.

Coordinates in model.svg are pixels of F1_scaled.png; callers rescale to
F1_original.png (the resolution of the hackathon preview images).
"""
import re
import xml.etree.ElementTree as ET
import numpy as np

NS = "{http://www.w3.org/2000/svg}"

CLASSES = [
    "door", "window", "toilet", "sink", "bathtub", "shower",
    "sauna_stove", "sauna_bench",
    "room_bedroom", "room_kitchen", "room_bath", "room_wc", "room_balcony",
    "floor",
]
CID = {c: i for i, c in enumerate(CLASSES)}

_num = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _mat(tr):
    m = np.eye(3)
    if not tr:
        return m
    for kind, args in re.findall(r"(\w+)\s*\(([^)]*)\)", tr):
        v = [float(x) for x in _num.findall(args)]
        t = np.eye(3)
        if kind == "matrix" and len(v) == 6:
            t = np.array([[v[0], v[2], v[4]], [v[1], v[3], v[5]], [0, 0, 1]])
        elif kind == "translate":
            t[0, 2] = v[0]
            t[1, 2] = v[1] if len(v) > 1 else 0
        elif kind == "scale":
            t[0, 0] = v[0]
            t[1, 1] = v[1] if len(v) > 1 else v[0]
        elif kind == "rotate":
            a = np.deg2rad(v[0])
            t = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        m = m @ t
    return m


def _poly_pts(el):
    if el.tag == NS + "polygon" or el.tag == NS + "polyline":
        v = [float(x) for x in _num.findall(el.get("points", ""))]
        return np.array(v[: len(v) // 2 * 2]).reshape(-1, 2)
    if el.tag == NS + "rect":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width", 0)), float(el.get("height", 0))
        return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    return None


def _apply(m, pts):
    p = np.c_[pts, np.ones(len(pts))] @ m.T
    return p[:, :2]


def _bbox(pts):
    return [pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()]


def _label(g):
    for gg in g.iter(NS + "g"):
        if gg.get("class", "") == "TextLabel NameLabel":
            return " ".join((t.text or "") for t in gg.iter(NS + "text")).strip().upper()
    return ""


def furniture_class(cl):
    n = cl.split()
    if len(n) < 2:
        return None
    name = n[-1] if n[1] == "ElectricalAppliance" else n[1]
    if name == "Toilet":
        return "toilet"
    if "Sink" in name:
        return "sink"
    if name in ("Bathtub", "Jacuzzi") or name.startswith("Bathtub"):
        return "bathtub"
    if name in ("Shower", "ShowerCab", "ShowerPlatform") or name.startswith("ShowerCab"):
        return "shower"
    if name.startswith("SaunaStove"):
        return "sauna_stove"
    if name.startswith("SaunaBench"):
        return "sauna_bench"
    return None


WC_RE = re.compile(r"^(WC|W\.C\.?)(\b|$)")


def room_class(cl, label):
    lab = label.replace(".", "").strip()
    toks = re.split(r"[\s/+,]+", lab)
    if cl.startswith("Space Bedroom") or "MH" in toks:
        return "room_bedroom"
    if cl.startswith("Space Kitchen") or any(t in ("K", "KK", "KEITTIÖ", "APUK", "TUPAK", "KEITTOKOMERO") for t in toks):
        return "room_kitchen"
    if cl.startswith("Space Outdoor Balcony") or any(t.startswith("PARV") and t != "PARVI" for t in toks):
        return "room_balcony"
    if cl.startswith("Space Bath") or any(t in ("KH", "KPH", "PH", "PESUH", "SH", "PSH", "WC") for t in toks):
        if toks and toks[0] == "WC" and len(toks) == 1:
            return "room_wc"
        return "room_bath"
    return None


def parse_svg(path):
    """Return list of (cls, [x0,y0,x1,y1]) in SVG (F1_scaled) pixel coords, plus n_floors."""
    root = ET.parse(path).getroot()
    out = []
    floors = []

    def walk(el, m, floor_acc):
        cl = el.get("class", "") or ""
        m = m @ _mat(el.get("transform"))
        if el.tag == NS + "g":
            if cl.startswith("Floorplan Floor"):
                acc = []
                for ch in el:
                    walk(ch, m, acc)
                if acc:
                    pts = np.vstack(acc)
                    floors.append(_bbox(pts))
                return
            if cl.startswith("Door") or cl.startswith("Window"):
                kind = "door" if cl.startswith("Door") else "window"
                if cl.startswith("Door None"):
                    kind = None
                pts = None
                for ch in el:
                    pts = _poly_pts(ch)
                    if pts is not None:
                        break
                if pts is not None and kind:
                    out.append((kind, _bbox(_apply(m, pts))))
                    if floor_acc is not None:
                        floor_acc.append(_apply(m, pts))
                return
            if cl.startswith("FixedFurniture"):
                fc = furniture_class(cl)
                bp = None
                for gg in el.iter(NS + "g"):
                    if gg.get("class", "") == "BoundaryPolygon":
                        for ch in gg:
                            bp = _poly_pts(ch)
                            if bp is not None:
                                bp = _apply(m @ _mat(gg.get("transform")), bp)
                                break
                        break
                if fc and bp is not None:
                    out.append((fc, _bbox(bp)))
                return
            if cl.startswith("Space ") or cl.startswith("Wall"):
                pts = None
                for ch in el:
                    pts = _poly_pts(ch)
                    if pts is not None:
                        break
                if pts is not None:
                    pts = _apply(m, pts)
                    if floor_acc is not None:
                        floor_acc.append(pts)
                    if cl.startswith("Space "):
                        rc = room_class(cl, _label(el))
                        if rc:
                            out.append((rc, _bbox(pts)))
                for ch in el:  # doors/windows are nested inside walls
                    if ch.tag == NS + "g":
                        walk(ch, m, floor_acc)
                return
        for ch in el:
            walk(ch, m, floor_acc)

    walk(root, np.eye(3), None)
    for f in floors:
        out.append(("floor", f))
    return out, len(floors)
