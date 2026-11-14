"""Raster floor plans (PNG/JPG): question -> detector classes -> count, with every detection boxed as evidence."""
import functools, re
from . import detector as D
from ..lexicon import has, first

KEY_CLASSES = {
    'windows': ['window'], 'doors': ['door'], 'toilets': ['toilet'], 'sinks': ['sink'],
    'showers_bathtubs': ['shower', 'bathtub'], 'floors': ['floor'], 'bedrooms': ['room_bedroom'], 'kitchens': ['room_kitchen'],
    'bathrooms': ['room_bath'], 'wc_rooms': ['room_wc'], 'saunas': ['room_sauna', 'sauna_stove'], 'balconies': ['room_balcony'],
}
LABEL = {'window': 'window', 'door': 'door', 'toilet': 'WC seat', 'sink': 'sink/basin', 'shower': 'shower', 'bathtub': 'bathtub',
         'floor': 'floor plan', 'room_bedroom': 'bedroom', 'room_kitchen': 'kitchen', 'room_bath': 'bathroom', 'room_wc': 'WC room',
         'room_sauna': 'sauna', 'sauna_stove': 'sauna stove', 'room_balcony': 'balcony'}


def route(q):
    k = D.template_key(q)
    if k: return k, 'rules'
    ql = q.lower()
    if re.search(r'separate wc|erillis', ql): return 'wc_rooms', 'lexicon'
    if has('storey', q): return 'floors', 'lexicon'
    c = first(q, ['window', 'door', 'toilet', 'basin', 'sink', 'shower', 'bathtub', 'sauna', 'kitchen', 'bedroom', 'bathroom', 'balcony'])
    return {'window': 'windows', 'door': 'doors', 'toilet': 'toilets', 'basin': 'sinks', 'sink': 'sinks', 'shower': 'showers_bathtubs',
            'bathtub': 'showers_bathtubs', 'sauna': 'saunas', 'kitchen': 'kitchens', 'bedroom': 'bedrooms', 'bathroom': 'bathrooms',
            'balcony': 'balconies'}.get(c), 'lexicon'


@functools.lru_cache(maxsize=256)
def dets(path):
    return tuple(tuple(sorted(d.items())) for d in D.detect(path))


ROOM_KEYS = {'bedrooms', 'kitchens', 'bathrooms', 'wc_rooms', 'saunas', 'balconies', 'floors'}
# storeys: the leak-free detector's 'floor' boxes (one per drawn plan) beat the OCR storey captions
# (preview dev split: 210 vs 202 of 241), so the detector answers storeys when its weights are present
DETECTOR_FIRST = {'floors'}


def ocr_answer(path, key, how):
    """Room types and storeys come from the printed room codes (MH, K, KH, WC, S, PARV, "1. kerros"), read by OCR.
    Fused with the detector where it helps: saunas = max(OCR, detector) because OCR never invents a sauna."""
    from . import rooms
    if key == 'floors' and D.WEIGHTS.exists():
        # storeys: the detector's per-storey 'floor' boxes beat caption OCR (preview dev split: 210 vs 202 of 241;
        # every one of the 21 plans where OCR found a caption the detector was right, OCR only on 13)
        return detector_answer(path, key, how)
    r = rooms.answer(path, key)
    r['steps'].insert(0, f"Router ({how}): question → “{key.replace('_', ' ')}” = count printed room labels")
    r['router'] = how
    for it in r['items']:
        it.setdefault('kind', 'room')
    # kitchens / bathrooms: with no legible label the 'every dwelling has one' prior (rooms.MINIMUM) beats the
    # detector's room boxes (preview dev split: kitchens 143 vs 131, bathrooms 95 vs 90), so no detector fallback
    if D.WEIGHTS.exists() and key not in ('kitchens', 'bathrooms') and (key == 'saunas' or not r.get('confident')):
        d = detector_answer(path, key, how)
        if d['value'] is not None and (key == 'saunas' and d['value'] > (r['value'] or 0) or not r.get('confident')):
            d['steps'] = r['steps'] + [f"OCR {'not confident' if not r.get('confident') else 'found fewer'} ({r['value']}): using the symbol detector instead"] + d['steps']
            d['method'] = 'OCR room labels → detector fallback'
            return d
    if key == 'bedrooms' and r.get('confident') and D.WEIGHTS.exists():
        # OCR misses MH labels far more often than it invents them (preview dev: 21 under vs 5 over), so a
        # bedroom box the detector is sure of (conf >= BED_SURE) raises the count; it never lowers it
        sure = dedup([dict(d) for d in dets(path) if dict(d)['cls'] == 'room_bedroom' and dict(d)['conf'] >= BED_SURE])
        if len(sure) > (r['value'] or 0):
            r['steps'].append(f"OCR read {r['value']} bedroom label(s); the detector is sure (≥{BED_SURE}) of {len(sure)} bedroom(s): "
                              f"answering {len(sure)} (a label hidden under furniture or hatching is missed, a confident bedroom box rarely is wrong)")
            r['items'] += [dict(kind='room_bedroom', label=f"bedroom · {d['conf']:.2f} (detector)", bbox=d['bbox'], value=None, check=None) for d in sure]
            r['value'] = len(sure)
            r['method'] = 'OCR room labels + confident detector boxes'
    return r


def answer(path, q):
    key, how = route(q)
    if key is None:
        return dict(value=None, unit=None, items=[], method='not routed', steps=['No raster template matched'])
    if key in DETECTOR_FIRST and D.WEIGHTS.exists():
        return detector_answer(path, key, how)
    if key in ROOM_KEYS:
        try:
            return ocr_answer(path, key, how)
        except Exception as e:   # OCR unavailable: fall through to the detector
            if not D.WEIGHTS.exists():
                return dict(value=None, unit=None, items=[], method='OCR unavailable', steps=[f'OCR failed: {e}'])
    r = detector_answer(path, key, how)
    if key == 'toilets' and r['value'] is not None:
        # every separate WC room holds a WC seat: 210 of the 213 leak-free training plans have toilets >= WC rooms
        try:
            w = ocr_answer(path, 'wc_rooms', how)['value'] or 0
        except Exception:
            w = 0
        if w > r['value']:
            r['steps'].append(f"{w} separate WC room(s) on the plan but only {r['value']} WC seat(s) detected: answering {w} "
                              f"(210 of the 213 leak-free CubiCasa5K training plans have at least one seat per WC room)")
            r['value'] = w
    return r


# Priors measured on the SVG annotations of the 213 leak-free training plans (data/full/cubicasa_free_ids.json),
# never on test plans: 200/213 have >= 1 shower/bathtub, 203/213 >= 1 WC seat, 197/213 >= 2 sinks (kitchen + basin).
# A plan drawn without a bathroom is rarer than the detector missing a small symbol, so the count never goes below.
PRIOR_MIN = {'showers_bathtubs': 1, 'toilets': 1, 'sinks': 2}
# shower threshold re-tuned together with the prior and the de-duplication on the 25 held-out leak-free plans
PRIOR_N = {'showers_bathtubs': '200', 'toilets': '203', 'sinks': '197'}
THR_OVERRIDE = {'shower': 0.15}
# bedrooms: plateau 0.5-0.8 in both halves of a 2-fold split of the preview plans (dev; chosen in the middle)
BED_SURE = 0.6
CONTAIN = 0.5   # a box with > 50 % of its area inside a stronger same-class box is the same object (TTA / nested storey)


def _inside(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix > CONTAIN * min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


def dedup(ds):
    keep = []
    for d in sorted(ds, key=lambda d: -d['conf']):
        if not any(e['cls'] == d['cls'] and _inside(d['bbox'], e['bbox']) for e in keep):
            keep.append(d)
    return keep


def detector_answer(path, key, how):
    if not D.WEIGHTS.exists():
        return dict(value=None, unit=None, items=[], method='detector weights not trained yet', steps=['Raster symbol detector is still training'])
    ds = [dict(d) for d in dets(path)]
    thr = {**D.thresholds(), **THR_OVERRIDE}
    cls = KEY_CLASSES[key]
    raw = [d for d in ds if d['cls'] in cls and d['conf'] >= thr.get(d['cls'], 0.25)]
    keep = dedup(raw)
    near = [d for d in ds if d['cls'] in cls and thr.get(d['cls'], 0.25) * 0.6 <= d['conf'] < thr.get(d['cls'], 0.25)]
    val = len(keep)
    if key == 'floors': val = max(1, val)
    prior = PRIOR_MIN.get(key, 0)
    if val < prior: val = prior
    if key == 'saunas':   # a sauna room and its stove are the same sauna
        rooms = [d for d in keep if d['cls'] == 'room_sauna']
        val = max(len(rooms), len([d for d in keep if d['cls'] == 'sauna_stove']))
    items = [dict(kind=d['cls'], label=f"{LABEL[d['cls']]} · {d['conf']:.2f}", bbox=d['bbox'], value=None,
                  check=None if d['conf'] >= 0.5 else dict(printed='', computed=d['conf'], ok=False, what='low confidence'))
             for d in sorted(keep, key=lambda d: (d['bbox'][1], d['bbox'][0]))]
    steps = [f"Router ({how}): question → “{key.replace('_', ' ')}” = detector classes {', '.join(cls)}",
             f"{'YOLOv8n + YOLO11s ensemble' if D.ensemble() else 'YOLOv8n detector'} (fine-tuned only on the 213 CubiCasa5K plans that are not in the Stoa set, so no test plan was seen; CubiCasa5K CC BY-NC-SA 4.0) on 4 rotations, boxes fused: {len(ds)} detections",
             f"Kept {len(keep)} {'/'.join(LABEL[c] for c in cls)} above the per-class threshold tuned on 25 held-out leak-free plans"
             + (f" ({len(raw) - len(keep)} duplicate box(es) inside a stronger one dropped)" if len(raw) > len(keep) else '')]
    if len(keep) < prior:
        steps.append(f"Detector saw {len(keep)}; answering {prior}: {prior}+ is what {PRIOR_N[key]} of the 213 leak-free CubiCasa5K training plans show (a small symbol is missed far more often than it is absent)")
    if near:
        steps.append(f"{len(near)} borderline detection(s) just below threshold not counted — check them if the count looks off")
    return dict(value=val, unit='count', items=items, method=f"detector count of {'/'.join(cls)}", steps=steps, router=how)
