"""Tune per-class thresholds (on held-out TRAINING plans) and evaluate on preview.

    python -m pinpoint.raster.eval_detector tune   # val split of CubiCasa subset -> thresholds json
    python -m pinpoint.raster.eval_detector eval   # 241 preview PNGs, exact-match per template
"""
import json, sys, time
from collections import defaultdict
from pathlib import Path
import numpy as np

from pinpoint.raster import detector as D
from pinpoint.raster.svg_labels import CLASSES

ROOT = D.ROOT
VAL = ROOT / "data/cubicasa_train/yolo"
PREV = ROOT / "data/preview/junction-dataset-preview"
CACHE = ROOT / "data/cubicasa_train/det_cache"


def run(paths, tag):
    """Raw detections (floor conf) for each path, cached on disk."""
    f = CACHE / f"{tag}.json"
    if f.exists():
        j = json.loads(f.read_text())
        return j["dets"], j["dt"]
    CACHE.mkdir(parents=True, exist_ok=True)
    D.detect(paths[0])  # warm-up
    out, t = {}, []
    for p in paths:
        t0 = time.time()
        out[Path(p).stem] = D.detect(p)
        t.append(time.time() - t0)
    f.write_text(json.dumps({"dets": out, "dt": float(np.mean(t))}))
    return out, float(np.mean(t))


def tune():
    counts = json.loads((VAL / "val_counts.json").read_text())
    paths = [str(VAL / "images/val" / f"{k}.png") for k in counts]
    dets, dt = run(paths, "val")
    grid = np.round(np.arange(0.05, 0.91, 0.025), 3)
    thr = {}
    print(f"{len(paths)} held-out plans, {dt and round(dt, 3)} s/img")
    for c in CLASSES:
        best = (-1, 0.25)
        for g in grid:
            ok = sum(sum(d["cls"] == c and d["conf"] >= g for d in dets[k]) == counts[k].get(c, 0)
                     for k in counts)
            if ok > best[0] or (ok == best[0] and abs(g - 0.3) < abs(best[1] - 0.3)):
                best = (ok, float(g))
        thr[c] = best[1]
        print(f"  {c:14s} thr={best[1]:.3f} exact={best[0]}/{len(counts)}")
    D.THRESH.write_text(json.dumps(thr, indent=1))
    # template-level accuracy on held-out (SVG-derived truth)
    acc = defaultdict(list)
    for k, cnt in counts.items():
        pred = D.count_answers(dets[k], thr)
        truth = {
            "windows": cnt.get("window", 0), "doors": cnt.get("door", 0),
            "toilets": cnt.get("toilet", 0), "sinks": cnt.get("sink", 0),
            "showers_bathtubs": cnt.get("shower", 0) + cnt.get("bathtub", 0),
            "floors": max(1, cnt.get("_floors", 1)), "bedrooms": cnt.get("room_bedroom", 0),
            "kitchens": cnt.get("room_kitchen", 0), "bathrooms": cnt.get("room_bath", 0),
            "wc_rooms": cnt.get("room_wc", 0), "balconies": cnt.get("room_balcony", 0),
            "saunas": max(cnt.get("room_sauna", 0), cnt.get("sauna_stove", 0)),
        }
        for t, v in truth.items():
            acc[t].append(pred[t] == v)
    print("held-out template accuracy:")
    for t, v in acc.items():
        print(f"  {t:18s} {np.mean(v):.3f}")


def evaluate():
    rows = [json.loads(l) for l in open(PREV / "questions.jsonl")]
    rows = [r for r in rows if "cubicasa5k" in r["path"]]
    paths = sorted({str(PREV / r["path"]) for r in rows})
    dets, dt = run(paths, "preview")
    answers = {k: D.count_answers(v) for k, v in dets.items()}
    res = defaultdict(lambda: [0, 0, 0])  # ok, total, off-by-one
    for r in rows:
        k = D.template_key(r["question"])
        lang = "FI" if r["question"].startswith("Kuinka") else "EN"
        if lang == "FI":
            continue  # FI duplicates EN exactly
        p = answers[Path(r["path"]).stem][k]
        res[k][0] += p == r["answer"]
        res[k][1] += 1
        res[k][2] += abs(p - r["answer"]) <= 1
    tot = [0, 0]
    print(f"{len(paths)} preview images; inference {dt and round(dt, 3)} s/img (mean, incl. load)")
    for k, (ok, n, near) in sorted(res.items()):
        print(f"  {k:18s} {ok:4d}/{n:<4d} = {ok / n:.3f}   (within ±1: {near / n:.3f})")
        tot[0] += ok
        tot[1] += n
    print(f"  {'OVERALL':18s} {tot[0]:4d}/{tot[1]:<4d} = {tot[0] / tot[1]:.3f}")


if __name__ == "__main__":
    {"tune": tune, "eval": evaluate}[sys.argv[1]]()
