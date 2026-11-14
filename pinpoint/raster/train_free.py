"""Train YOLOv8n on the LEAK-FREE CubiCasa5K subset (yolo_free, 213 non-Stoa plans), Apple MPS.

    nohup python -m pinpoint.raster.train_free [hours] > data/cubicasa_train/train.log 2>&1 &

Best weights -> data/models/cubicasa_yolo_free.pt.  Model: Ultralytics YOLOv8n (AGPL-3.0).
"""
import shutil, sys, time
from pathlib import Path
import torch
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/cubicasa_train/yolo_free/data.yaml"
RUNS = ROOT / "data/models/runs"


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 1.9
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    print("start", time.strftime("%X"), "budget h", hours, "device", dev,
          "ETA", time.strftime("%X", time.localtime(time.time() + hours * 3600)), flush=True)
    try:
        m = YOLO("yolov8n.pt")
    except Exception as e:  # offline fallback
        print("yolov8n.pt unavailable:", e, "-> yolo11n", flush=True)
        m = YOLO(str(RUNS / "yolo11n.pt"))
    m.train(data=str(DATA), imgsz=1024, epochs=80, time=hours, batch=8, device=dev, workers=4,
            project=str(RUNS), name="cubicasa_free", exist_ok=True, plots=False,
            flipud=0.5, fliplr=0.5, degrees=0.0, scale=0.5, translate=0.1,
            mosaic=1.0, close_mosaic=5, hsv_h=0.02, hsv_s=0.5, hsv_v=0.3,
            max_det=600, patience=100, seed=0, cache=False)
    best = RUNS / "cubicasa_free/weights/best.pt"
    shutil.copy(best, ROOT / "data/models/cubicasa_yolo_free.pt")
    print("saved", ROOT / "data/models/cubicasa_yolo_free.pt", time.strftime("%X"), flush=True)


if __name__ == "__main__":
    main()
