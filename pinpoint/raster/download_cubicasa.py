"""Fetch a subset of CubiCasa5K (Zenodo record 2613548) via HTTP range requests.

Only F1_original.png + model.svg (+ the PNG header of F1_scaled.png, which gives
the SVG coordinate frame) are fetched, one or two range requests per plan.
Plans whose id appears in the hackathon preview set are EXCLUDED (no leakage).

Usage: python -m pinpoint.raster.download_cubicasa [n_hqa]
"""
import json, random, struct, sys, time, zlib, pickle
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests

URL = "https://zenodo.org/records/2613548/files/cubicasa5k.zip?download=1"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/cubicasa_train/raw"
IDX = ROOT / "data/cubicasa_train/zipindex.pkl"
PREVIEW = ROOT / "data/preview/junction-dataset-preview/data/cubicasa5k"
S = requests.Session()


def get_range(a, b):
    for attempt in range(12):
        try:
            r = S.get(URL, headers={"Range": f"bytes={a}-{b}"}, timeout=120)
            if r.status_code == 206:
                return r.content
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", 20))
                time.sleep(max(wait, 5))
                continue
            r.raise_for_status()
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"range {a}-{b} failed")


def index():
    if IDX.exists():
        return pickle.load(open(IDX, "rb"))
    from remotezip import RemoteZip
    with RemoteZip(URL) as z:
        idx = {i.filename: (i.header_offset, i.compress_size, i.file_size, i.compress_type)
               for i in z.infolist()}
    pickle.dump(idx, open(IDX, "wb"))
    return idx


def extract(blob, base_off, info):
    off = info[0] - base_off
    n, m = struct.unpack("<HH", blob[off + 26:off + 30])
    data = blob[off + 30 + n + m: off + 30 + n + m + info[1]]
    if info[3] == 8:
        data = zlib.decompress(data, -15)
    return data


def fetch(idx, folder, pid):
    d = OUT / folder / pid
    if (d / "meta.json").exists():
        return "skip"
    base = f"cubicasa5k/{folder}/{pid}/"
    o, s = idx[base + "F1_original.png"], idx[base + "model.svg"]
    a = min(o[0], s[0])
    b = max(o[0] + o[1], s[0] + s[1]) + 512
    blob = get_range(a, b)
    png, svg = extract(blob, a, o), extract(blob, a, s)
    sc = idx[base + "F1_scaled.png"]
    hdr = get_range(sc[0], sc[0] + 400)
    n, m = struct.unpack("<HH", hdr[26:30])
    raw = hdr[30 + n + m:]
    if sc[3] == 8:
        raw = zlib.decompressobj(-15).decompress(raw)
    w, h = struct.unpack(">II", raw[16:24])
    d.mkdir(parents=True, exist_ok=True)
    (d / "F1_original.png").write_bytes(png)
    (d / "model.svg").write_bytes(svg)
    (d / "meta.json").write_text(json.dumps({"scaled_wh": [w, h]}))
    return "ok"


def main():
    n_hqa = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    excl = {p.stem.rsplit("-", 1)[1] for p in PREVIEW.glob("*.png")}
    idx = index()
    plans = {}
    for n in idx:
        p = n.split("/")
        if len(p) == 4 and p[3] == "model.svg" and f"cubicasa5k/{p[1]}/{p[2]}/F1_original.png" in idx:
            plans.setdefault(p[1], []).append(p[2])
    rnd = random.Random(0)
    todo = []
    for folder in sorted(plans):
        ids = sorted(i for i in plans[folder] if i not in excl)
        rnd.shuffle(ids)
        if folder == "high_quality_architectural":
            ids = ids[:n_hqa]
        todo += [(folder, i) for i in ids]
    rnd.shuffle(todo)
    print("excluded preview ids:", len(excl), "to fetch:", len(todo), flush=True)
    done = 0
    def job(a):
        try:
            return fetch(idx, *a)
        except Exception as e:
            return f"fail {a} {e}"
    with ThreadPoolExecutor(3) as ex:
        for r in ex.map(job, todo):
            done += 1
            if r.startswith("fail"):
                print(r, flush=True)
            if done % 100 == 0:
                print(done, time.strftime("%X"), flush=True)


if __name__ == "__main__":
    main()
