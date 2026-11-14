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


def ocr_answer(path, key, how):
    """Room types and storeys come from the printed room codes (MH, K, KH, WC, S, PARV, "1. kerros"), read by OCR.
    Fused with the detector where it helps: saunas = max(OCR, detector) because OCR never invents a sauna."""
    from . import rooms
    r = rooms.answer(path, key)
    r['steps'].insert(0, f"Router ({how}): question → “{key.replace('_', ' ')}” = count printed room labels")
    r['router'] = how
    for it in r['items']:
        it.setdefault('kind', 'room')
    if D.WEIGHTS.exists() and (key == 'saunas' or not r.get('confident')):
        d = detector_answer(path, key, how)
        if d['value'] is not None and (key == 'saunas' and d['value'] > (r['value'] or 0) or not r.get('confident')):
            d['steps'] = r['steps'] + [f"OCR {'not confident' if not r.get('confident') else 'found fewer'} ({r['value']}): using the symbol detector instead"] + d['steps']
            d['method'] = 'OCR room labels → detector fallback'
            return d
    return r


def answer(path, q):
    key, how = route(q)
    if key is None:
        return dict(value=None, unit=None, items=[], method='not routed', steps=['No raster template matched'])
    if key in ROOM_KEYS:
        try:
            return ocr_answer(path, key, how)
        except Exception as e:   # OCR unavailable: fall through to the detector
            if not D.WEIGHTS.exists():
                return dict(value=None, unit=None, items=[], method='OCR unavailable', steps=[f'OCR failed: {e}'])
    return detector_answer(path, key, how)


def detector_answer(path, key, how):
    if not D.WEIGHTS.exists():
        return dict(value=None, unit=None, items=[], method='detector weights not trained yet', steps=['Raster symbol detector is still training'])
    ds = [dict(d) for d in dets(path)]
    thr = D.thresholds()
    cls = KEY_CLASSES[key]
    keep = [d for d in ds if d['cls'] in cls and d['conf'] >= thr.get(d['cls'], 0.25)]
    near = [d for d in ds if d['cls'] in cls and thr.get(d['cls'], 0.25) * 0.6 <= d['conf'] < thr.get(d['cls'], 0.25)]
    val = len(keep)
    if key == 'floors': val = max(1, val)
    if key == 'saunas':   # a sauna room and its stove are the same sauna
        rooms = [d for d in keep if d['cls'] == 'room_sauna']
        val = max(len(rooms), len([d for d in keep if d['cls'] == 'sauna_stove']))
    items = [dict(kind=d['cls'], label=f"{LABEL[d['cls']]} · {d['conf']:.2f}", bbox=d['bbox'], value=None,
                  check=None if d['conf'] >= 0.5 else dict(printed='', computed=d['conf'], ok=False, what='low confidence'))
             for d in sorted(keep, key=lambda d: (d['bbox'][1], d['bbox'][0]))]
    steps = [f"Router ({how}): question → “{key.replace('_', ' ')}” = detector classes {', '.join(cls)}",
             f"YOLO detector (fine-tuned on CubiCasa5K plans, preview plans excluded) on 4 rotations, boxes fused: {len(ds)} detections",
             f"Kept {len(keep)} {'/'.join(LABEL[c] for c in cls)} above the per-class threshold tuned on held-out training plans"]
    if near:
        steps.append(f"{len(near)} borderline detection(s) just below threshold not counted — check them if the count looks off")
    return dict(value=val, unit='count', items=items, method=f"detector count of {'/'.join(cls)}", steps=steps, router=how)
