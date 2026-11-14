"""Build a LEAK-FREE YOLO dataset from the 213 CubiCasa5K plans that are NOT in the
Stoa/Junction dataset (data/full/cubicasa_free_ids.json).

  data/cubicasa_train/raw/<folder>/<id>  ->  data/cubicasa_train/yolo_free/{images,labels}/{train,val}

Hard guarantee: asserts that no plan ID in data/full/cubicasa_stoa_ids.json (which covers
4787 of the 5000 CubiCasa5K plans, including every preview/eval plan) is written.

Offline augmentation for the train split (the set is small): original, rot90, rot270+flip,
and a 0.6x downscale (the preview images range from ~240 px to ~1800 px). Online
flips/scale/mosaic in train_free.py add the rest.
CubiCasa5K: CC BY-NC-SA 4.0 (Kalervo et al. 2019) - derived labels keep that licence.
"""
import json, random, re, shutil
from collections import Counter
from pathlib import Path
import cv2

from pinpoint.raster.svg_labels import parse_svg, CLASSES, CID

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/cubicasa_train/raw"
OUT = ROOT / "data/cubicasa_train/yolo_free"
FREE = ROOT / "data/full/cubicasa_free_ids.json"
STOA = ROOT / "data/full/cubicasa_stoa_ids.json"
MAX_SIDE = 1600
N_VAL = 25


def rot90(im, lines):  # clockwise
    im = cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)
    return im, [[c, 1 - y, x, h, w] for c, x, y, w, h in lines]


def tflip(im, lines):  # transpose (= rot90 ccw + flip)
    return cv2.transpose(im), [[c, y, x, h, w] for c, x, y, w, h in lines]


def main():
    free = sorted(json.loads(FREE.read_text()))
    stoa = set(json.loads(STOA.read_text()))
    assert len(free) == 213 and not set(free) & stoa
    if OUT.exists():
        shutil.rmtree(OUT)
    for s in ("train", "val"):
        (OUT / "images" / s).mkdir(parents=True)
        (OUT / "labels" / s).mkdir(parents=True)
    rnd = random.Random(7)
    order = free[:]
    rnd.shuffle(order)
    split = {pid: ("val" if i < N_VAL else "train") for i, pid in enumerate(order)}
    stats, val_counts, n_img = Counter(), {}, Counter()
    written = set()
    for pid in free:
        folder, num = pid.rsplit("-", 1)
        p = RAW / folder / num
        objs, nf = parse_svg(p / "model.svg")
        im = cv2.imread(str(p / "F1_original.png"))
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
        s = split[pid]
        variants = [("", im, lines)]
        if s == "train":
            variants.append(("_r90",) + rot90(im, lines))
            variants.append(("_tf",) + tflip(*rot90(*rot90(im, lines))))
            h2, w2 = im.shape[:2]
            if max(h2, w2) > 700:
                small = cv2.resize(im, (round(w2 * .6), round(h2 * .6)), interpolation=cv2.INTER_AREA)
                variants.append(("_s60", small, lines))
        else:
            val_counts[pid] = dict(Counter(CLASSES[l[0]] for l in lines))
            val_counts[pid]["_floors"] = nf
        for suf, img, ls in variants:
            cv2.imwrite(str(OUT / "images" / s / f"{pid}{suf}.png"), img)
            (OUT / "labels" / s / f"{pid}{suf}.txt").write_text(
                "".join(f"{l[0]} {l[1]:.6f} {l[2]:.6f} {l[3]:.6f} {l[4]:.6f}\n" for l in ls))
            n_img[s] += 1
        written.add(pid)
    # leakage check on what is actually on disk
    on_disk = {re.sub(r"_(r90|tf|s60)$", "", f.stem) for f in OUT.glob("images/*/*.png")}
    assert not on_disk & stoa, "STOA LEAK"
    assert on_disk <= set(free)
    (OUT / "val_counts.json").write_text(json.dumps(val_counts))
    (OUT / "data.yaml").write_text(
        f"path: {OUT}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    print(len(written), "plans", dict(n_img), "images; leak check OK (0 Stoa IDs);", dict(stats))


if __name__ == "__main__":
    main()
