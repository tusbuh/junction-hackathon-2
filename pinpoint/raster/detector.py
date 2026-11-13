"""Raster floor-plan symbol detector (YOLO trained on CubiCasa5K, CC BY-NC 4.0).

    from pinpoint.raster.detector import detect, count_answers
    dets = detect("plan.png")            # [{cls, conf, bbox=[x0,y0,x1,y1]}, ...]
    counts = count_answers(dets)          # {"windows": 13, "toilets": 2, ...}

Detections are returned above a low floor confidence; `count_answers` applies
the per-class thresholds tuned on a held-out split of the training data
(data/models/cubicasa_thresholds.json).
"""
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "data/models/cubicasa_yolo.pt"
THRESH = ROOT / "data/models/cubicasa_thresholds.json"
IMGSZ = 1024
FLOOR_CONF = 0.05

_model = None
_lock = threading.Lock()
_thr = None


def _device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def model():
    global _model
    with _lock:
        if _model is None:
            from ultralytics import YOLO
            _model = YOLO(str(WEIGHTS))
    return _model


def thresholds():
    global _thr
    if _thr is None:
        _thr = json.loads(THRESH.read_text()) if THRESH.exists() else {}
    return _thr


def detect(png_path, conf=FLOOR_CONF, imgsz=IMGSZ):
    """Run the detector on one image. bbox is in original image pixels."""
    m = model()
    with _lock:
        r = m.predict(str(png_path), imgsz=imgsz, conf=conf, iou=0.5, device=_device(),
                      verbose=False, max_det=600)[0]
    names = r.names
    out = []
    for b, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
        out.append({"cls": names[int(k)], "conf": round(float(c), 4),
                    "bbox": [round(v, 1) for v in b]})
    return out


def class_counts(dets, thr=None):
    thr = thresholds() if thr is None else thr
    n = {}
    for d in dets:
        if d["conf"] >= thr.get(d["cls"], 0.25):
            n[d["cls"]] = n.get(d["cls"], 0) + 1
    return n


def count_answers(dets, thr=None):
    """Map detections to the count-question templates."""
    n = class_counts(dets, thr)
    g = lambda k: n.get(k, 0)
    return {
        "windows": g("window"),
        "doors": g("door"),
        "toilets": g("toilet"),
        "sinks": g("sink"),
        "showers_bathtubs": g("shower") + g("bathtub"),
        "floors": max(1, g("floor")),
        "bedrooms": g("room_bedroom"),
        "kitchens": g("room_kitchen"),
        "bathrooms": g("room_bath"),
        "wc_rooms": g("room_wc"),
        "saunas": max(g("room_sauna"), g("sauna_stove")),
        "balconies": g("room_balcony"),
    }


# question template prefix (EN / FI) -> count_answers key
TEMPLATES = [
    ("How many windows", "windows"), ("Kuinka monta ikkunaa", "windows"),
    ("How many toilet bowls", "toilets"), ("Kuinka monta WC-istuinta", "toilets"),
    ("How many sinks", "sinks"), ("Kuinka monta pesu- ja tiskiallasta", "sinks"),
    ("How many showers", "showers_bathtubs"), ("Kuinka monta suihkua", "showers_bathtubs"),
    ("How many floors", "floors"), ("Kuinka monta kerrosta", "floors"),
    ("How many doors", "doors"), ("Kuinka monta ovea", "doors"),
    ("How many bedrooms", "bedrooms"), ("Kuinka monta makuuhuonetta", "bedrooms"),
    ("How many kitchens", "kitchens"), ("Kuinka monta keittiötä", "kitchens"),
    ("How many bathrooms", "bathrooms"), ("Kuinka monta kylpy", "bathrooms"),
    ("How many separate WC", "wc_rooms"), ("Kuinka monta erillistä WC", "wc_rooms"),
    ("How many saunas", "saunas"), ("Kuinka monta saunaa", "saunas"),
    ("How many balconies", "balconies"), ("Kuinka monta parveketta", "balconies"),
]


def template_key(question):
    for p, k in TEMPLATES:
        if question.startswith(p):
            return k
    return None


def answer(png_path, question):
    """Answer one count question, or None if the template is unknown."""
    k = template_key(question)
    if k is None:
        return None
    return count_answers(detect(png_path))[k]
