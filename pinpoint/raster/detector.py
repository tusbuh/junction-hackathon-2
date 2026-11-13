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

import cv2
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "data/models/cubicasa_yolo.pt"
THRESH = ROOT / "data/models/cubicasa_thresholds.json"
IMGSZ = 1024
FLOOR_CONF = 0.05
TTA = True  # 4-rotation test-time augmentation (set per thresholds file)

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


def _predict(im, conf, imgsz):
    m = model()
    with _lock:
        r = m.predict(im, imgsz=imgsz, conf=conf, iou=0.5, device=_device(),
                      verbose=False, max_det=600)[0]
    return r.names, r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy().astype(int)


def _iou(a, b):
    x0, y0 = np.maximum(a[0], b[:, 0]), np.maximum(a[1], b[:, 1])
    x1, y1 = np.minimum(a[2], b[:, 2]), np.minimum(a[3], b[:, 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter
    return inter / np.maximum(ua, 1e-9)


def detect(png_path, conf=FLOOR_CONF, imgsz=IMGSZ, tta=None):
    """Run the detector on one image. bbox is in original image pixels.

    tta=True runs the model on 4 rotations (0/90/180/270 deg) and fuses the boxes:
    a fused box's conf is the mean over rotations (0 where a rotation missed it),
    which makes counts robust to how the plan is oriented.
    """
    tta = TTA if tta is None else tta
    im = cv2.imread(str(png_path), cv2.IMREAD_COLOR)
    H, W = im.shape[:2]
    if not tta:
        names, b, c, k = _predict(im, conf, imgsz)
        return [{"cls": names[int(kk)], "conf": round(float(cc), 4), "bbox": [round(float(v), 1) for v in bb]}
                for bb, cc, kk in zip(b, c, k)]
    allb, allc, allk, alla = [], [], [], []
    for r in range(4):
        names, b, c, k = _predict(np.ascontiguousarray(np.rot90(im, r)), conf, imgsz)
        allb.append(_unrotate_k(b, r, W, H)); allc.append(c); allk.append(k); alla.append(np.full(len(c), r))
    b, c, k, a = np.concatenate(allb), np.concatenate(allc), np.concatenate(allk), np.concatenate(alla)
    out = []
    used = np.zeros(len(c), bool)
    for i in np.argsort(-c):
        if used[i]:
            continue
        cand = np.where(~used & (k == k[i]))[0]
        ious = _iou(b[i], b[cand])
        grp = cand[ious >= 0.45]
        used[grp] = True
        score = sum(c[grp][a[grp] == r].max() for r in set(a[grp].tolist())) / 4.0
        w = c[grp][:, None]
        box = (b[grp] * w).sum(0) / w.sum()
        out.append({"cls": names[int(k[i])], "conf": round(float(score), 4),
                    "bbox": [round(float(v), 1) for v in box]})
    return out


def _unrotate_k(b, r, W, H):
    """Boxes predicted on np.rot90(img, r) (CCW) -> original image frame (W x H)."""
    if r == 0:
        return b
    x0, y0, x1, y1 = b.T
    if r == 1:   # rotated frame is H x W (width H). orig x = W - y', orig y = x'
        return np.stack([W - y1, x0, W - y0, x1], 1)
    if r == 2:   # orig x = W - x', orig y = H - y'
        return np.stack([W - x1, H - y1, W - x0, H - y0], 1)
    # r == 3: orig x = y', orig y = H - x'
    return np.stack([y0, H - x1, y1, H - x0], 1)


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
