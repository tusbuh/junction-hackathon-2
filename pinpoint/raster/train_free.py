"""Train YOLOv8n on the LEAK-FREE CubiCasa5K subset (yolo_free, 213 non-Stoa plans), Apple MPS.

    nohup python -m pinpoint.raster.train_free [hours] > data/cubicasa_train/train.log 2>&1 &

Best weights -> data/models/cubicasa_yolo_free.pt.  Model: Ultralytics YOLOv8n (AGPL-3.0).
"""
import re, shutil, sys, time
from pathlib import Path
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/cubicasa_train/yolo_free/data.yaml"
RUNS = ROOT / "data/models/runs"


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 1.9
    arch = sys.argv[2] if len(sys.argv) > 2 else "yolov8n"   # e.g. yolo11s (RASTER4: bigger backbone, same leak-free data)
    batch = 8 if arch == "yolov8n" else 4
    name = "cubicasa_free" if arch == "yolov8n" else f"cubicasa_free_{arch}"
    out = ROOT / ("data/models/cubicasa_yolo_free.pt" if arch == "yolov8n" else f"data/models/cubicasa_{arch}_free.pt")
    import json
    free, stoa = set(json.loads((ROOT / "data/full/cubicasa_free_ids.json").read_text())), set(json.loads((ROOT / "data/full/cubicasa_stoa_ids.json").read_text()))
    on_disk = {re.sub(r"_(r90|tf|s60)$", "", p.stem) for p in (DATA.parent / "images").glob("*/*.png")}
    assert not free & stoa and not on_disk & stoa and on_disk <= free, "STOA LEAK"
    print("leak check OK:", len(on_disk), "plans, 0 Stoa IDs", flush=True)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    print("start", time.strftime("%X"), "budget h", hours, "device", dev,
          "ETA", time.strftime("%X", time.localtime(time.time() + hours * 3600)), flush=True)
    local = RUNS / f"{arch}.pt"
    m = YOLO(str(local) if local.exists() else f"{arch}.pt")
    m.train(data=str(DATA), imgsz=1024, epochs=80, time=hours, batch=batch, device=dev, workers=4 if arch == "yolov8n" else 2,
            project=str(RUNS), name=name, exist_ok=True, plots=False,
            flipud=0.5, fliplr=0.5, degrees=0.0, scale=0.5, translate=0.1,
            mosaic=1.0, close_mosaic=5, hsv_h=0.02, hsv_s=0.5, hsv_v=0.3,
            max_det=600, patience=100, seed=0, cache=False)
    best = RUNS / name / "weights/best.pt"
    shutil.copy(best, out)
    (RUNS / name / "weights/last.pt").unlink(missing_ok=True)   # disk-light: keep best.pt only
    print("saved", out, time.strftime("%X"), flush=True)


if __name__ == "__main__":
    main()
