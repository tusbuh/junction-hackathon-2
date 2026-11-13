"""Build a YOLO dataset from the downloaded CubiCasa5K subset.

data/cubicasa_train/raw/<folder>/<id>/{F1_original.png,model.svg,meta.json}
  -> data/cubicasa_train/yolo/{images,labels}/{train,val}/<folder>-<id>.{jpg,txt}
plus data/cubicasa_train/yolo/val_counts.json (SVG-derived object counts for the
held-out split, used to tune per-class thresholds without touching the preview set).

Half of the training images are transposed offline (90-degree rotation + flip),
which together with flipud/fliplr augmentation covers all 8 orientations.
"""
import json, random, sys
from collections import Counter
from pathlib import Path
import cv2

from pinpoint.raster.svg_labels import parse_svg, CLASSES, CID

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/cubicasa_train/raw"
OUT = ROOT / "data/cubicasa_train/yolo"
MAX_SIDE = 1600  # cap stored resolution (preview images are F1_original-sized)


def main():
    rnd = random.Random(1)
    plans = sorted(p for p in RAW.glob("*/*") if (p / "meta.json").exists())
    rnd.shuffle(plans)
    n_val = max(100, len(plans) // 10)
    split = {p: ("val" if i < n_val else "train") for i, p in enumerate(plans)}
    for s in ("train", "val"):
        (OUT / "images" / s).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / s).mkdir(parents=True, exist_ok=True)
    val_counts = {}
    stats = Counter()
    for p in plans:
        s = split[p]
        name = f"{p.parent.name}-{p.name}"
        try:
            objs, nf = parse_svg(p / "model.svg")
        except Exception as e:
            print("skip", p, e)
            continue
        im = cv2.imread(str(p / "F1_original.png"))
        if im is None:
            continue
        sw, sh = json.loads((p / "meta.json").read_text())["scaled_wh"]
        H, W = im.shape[:2]
        sx, sy = W / sw, H / sh
        f = min(1.0, MAX_SIDE / max(H, W))
        if f < 1:
            im = cv2.resize(im, (round(W * f), round(H * f)), interpolation=cv2.INTER_AREA)
        lines = []
        for c, (x0, y0, x1, y1) in objs:
            x0, x1 = max(0, x0 * sx / W), min(1, x1 * sx / W)
            y0, y1 = max(0, y0 * sy / H), min(1, y1 * sy / H)
            if x1 - x0 <= 1e-3 or y1 - y0 <= 1e-3:
                continue
            lines.append([CID[c], (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0])
            stats[c] += 1
        if s == "train" and rnd.random() < 0.5:
            im = cv2.transpose(im)
            for l in lines:
                l[1], l[2], l[3], l[4] = l[2], l[1], l[4], l[3]
        if s == "val":
            val_counts[name] = dict(Counter(CLASSES[l[0]] for l in lines))
            val_counts[name]["_floors"] = nf
        cv2.imwrite(str(OUT / "images" / s / f"{name}.png"), im)
        (OUT / "labels" / s / f"{name}.txt").write_text(
            "".join(f"{l[0]} {l[1]:.6f} {l[2]:.6f} {l[3]:.6f} {l[4]:.6f}\n" for l in lines))
    (OUT / "val_counts.json").write_text(json.dumps(val_counts))
    (OUT / "data.yaml").write_text(
        f"path: {OUT}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    print(len(plans), "plans;", n_val, "val;", dict(stats))


if __name__ == "__main__":
    sys.exit(main())
