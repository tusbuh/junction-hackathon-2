"""Text on scanned / raster floor plans with Tesseract (fin+eng), robust to rotated labels.

CubiCasa plans carry Finnish room labels (MH, K, KH, KPH, PH, WC, SAUNA, PARVEKE ...) and storey captions
("1. kerros") in any of four orientations, a few pixels tall, on top of wall linework and coloured fills.
Recipe: upscale x4 -> two binarisations (Otsu for clean prints, adaptive for text on coloured fills) ->
strip long horizontal/vertical lines -> Tesseract sparse-text mode (psm 11) on all 4 rotations -> map every
word box back to plan pixels -> merge identical duplicates.
Results are cached per plan in data/cache/ocr/<name>.json, so a question costs one dictionary lookup.
"""
import os, re, json, hashlib
import numpy as np
import cv2

# Tesseract spawns one OpenMP thread per core per call; with several plans in flight that oversubscribes the
# machine (load > 200 observed). One thread per call, parallelism across plans instead.
os.environ.setdefault('OMP_THREAD_LIMIT', '1')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CACHE = os.path.join(ROOT, 'data/cache/ocr')
SCALE = 4
VERSION = 2
ROTS = ((0, None), (90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180), (270, cv2.ROTATE_90_COUNTERCLOCKWISE))


def _binarize(big, mode):
    if mode == 'otsu':
        _, bw = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        bw = cv2.adaptiveThreshold(big, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 18)
    for k in ((25 * SCALE, 1), (1, 25 * SCALE)):   # walls and dimension lines
        ln = cv2.morphologyEx(255 - bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
        bw = cv2.bitwise_or(bw, ln)
    return bw


def _unrotate(rot, x0, y0, x1, y1, W, H):
    """box in the rotated (scaled) image -> box in the scaled original (W, H = scaled original size)"""
    pts = [(x0, y0), (x1, y1)]
    if rot == 90:      # clockwise: (x, y) -> (H-1-y, x)
        pts = [(yn, H - 1 - xn) for xn, yn in pts]
    elif rot == 180:
        pts = [(W - 1 - xn, H - 1 - yn) for xn, yn in pts]
    elif rot == 270:   # counter-clockwise: (x, y) -> (y, W-1-x)
        pts = [(W - 1 - yn, xn) for xn, yn in pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0


def run(path, min_conf=40):
    import pytesseract
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return []
    h0, w0 = im.shape
    big = cv2.resize(im, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    H, W = big.shape
    words = []
    for mode in ('otsu', 'adaptive'):
        bw = _binarize(big, mode)
        for rot, code in ROTS:
            r = bw if code is None else cv2.rotate(bw, code)
            d = pytesseract.image_to_data(r, lang='fin+eng', config='--psm 11', output_type=pytesseract.Output.DICT)
            for t, c, x, y, w, h in zip(d['text'], d['conf'], d['left'], d['top'], d['width'], d['height']):
                t = t.strip()
                c = float(c)
                if not t or c < min_conf or not re.search(r'[A-Za-zÄÖÅäöå0-9]', t):
                    continue
                bx = _unrotate(rot, x, y, x + w, y + h, W, H)
                words.append(dict(text=t, conf=round(c, 1), rot=rot, mode=mode,
                                  bbox=[round(v / SCALE, 1) for v in bx]))
    # merge identical readings of the same word (two binarisations); different readings of one spot are all
    # kept: a confident misreading in the wrong rotation ("m") must not hide the true label ("MH", conf 58)
    words.sort(key=lambda w: -w['conf'])
    keep = []
    for w in words:
        if any(_iou(w['bbox'], k['bbox']) > 0.4 and w['text'].upper() == k['text'].upper() for k in keep):
            continue
        keep.append(w)
    return dict(size=[w0, h0], words=keep)


def cache_path(path):
    st = os.stat(path)
    key = hashlib.md5(f'{os.path.basename(path)}|{st.st_size}|{VERSION}'.encode()).hexdigest()[:10]
    return os.path.join(CACHE, f'{os.path.splitext(os.path.basename(path))[0]}-{key}.json')


def cached(path):
    """OCR result if already computed, else None (never runs Tesseract)."""
    f = cache_path(path)
    return json.load(open(f)) if os.path.exists(f) else None


def words(path):
    """Cached OCR of a plan image."""
    os.makedirs(CACHE, exist_ok=True)
    f = cache_path(path)
    if os.path.exists(f):
        return json.load(open(f))
    out = run(path)
    tmp = f + '.part'
    json.dump(out, open(tmp, 'w'), ensure_ascii=False)
    os.replace(tmp, f)
    return out


if __name__ == '__main__':
    # batch:  python -m pinpoint.raster.ocr <dir-or-files...>   (parallel, fills the cache)
    import sys, glob, time
    from concurrent.futures import ProcessPoolExecutor
    os.environ.setdefault('OMP_THREAD_LIMIT', '1')
    files = []
    for a in sys.argv[1:]:
        files += sorted(glob.glob(os.path.join(a, '*.png')) + glob.glob(os.path.join(a, '*.jpg'))) if os.path.isdir(a) else [a]
    t = time.time()
    with ProcessPoolExecutor(int(os.environ.get('OCR_WORKERS', 4))) as ex:
        for i, _ in enumerate(ex.map(words, files)):
            if i % 20 == 0:
                print(f'{i}/{len(files)} {time.time() - t:.0f}s', flush=True)
    print('done', len(files), f'{time.time() - t:.0f}s')
