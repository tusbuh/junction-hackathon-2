"""Train the CubiCasa5K symbol/room detector (ultralytics YOLO11n, Apple MPS).

    python -m pinpoint.raster.train [hours]

Orientation robustness: half the training images are transposed offline
(build_dataset.py); flipud/fliplr=0.5 here -> all 8 rotations/flips are seen.
Best weights are copied to data/models/cubicasa_yolo.pt.
"""
import shutil, sys
from pathlib import Path
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/cubicasa_train/yolo/data.yaml"
RUNS = ROOT / "data/models/runs"


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 1.9
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    m = YOLO(str(RUNS / "yolo11n.pt") if (RUNS / "yolo11n.pt").exists() else "yolo11n.pt")
    m.train(data=str(DATA), imgsz=896, epochs=40, time=hours, batch=8, device=dev, workers=4,
            project=str(RUNS), name="cubicasa", exist_ok=True, plots=False,
            flipud=0.5, fliplr=0.5, degrees=0.0, scale=0.3, translate=0.1,
            mosaic=1.0, close_mosaic=3, hsv_h=0.02, hsv_s=0.5, hsv_v=0.3,
            max_det=600, patience=100, seed=0)
    best = RUNS / "cubicasa/weights/best.pt"
    shutil.copy(best, ROOT / "data/models/cubicasa_yolo.pt")
    print("saved", ROOT / "data/models/cubicasa_yolo.pt")


if __name__ == "__main__":
    main()
