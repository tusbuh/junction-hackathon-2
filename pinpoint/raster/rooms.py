"""Room-type counts on Finnish raster floor plans from OCR'd room labels (see ocr.py).

Finnish plans name every room with a short printed code: MH = makuuhuone (bedroom), K / KK / TK / AK =
keittiö / keittokomero / tupakeittiö / avokeittiö (kitchen), KH / KPH / PH / PESUH / SH = kylpy- / pesu- /
suihkuhuone (bathroom), WC, S / SAUNA / LH = sauna (löylyhuone), PARV / PARVEKE (balcony), and storeys are
captioned "1. kerros", "2. krs", "kellari" ... Counting rooms = counting label instances of a class; every
counted label is returned with its box so the reader can check it on the plan.
"""
import re

# token -> room class.  Combined labels ("KHH+PH", "OH+RT+K", "PH/S") are split on + / & , and spaces.
CLASS_TOKENS = {
    'bedroom': {'MH', 'MAKUUHUONE', 'MAKUUH', 'MAKUU'},
    'kitchen': {'K', 'KK', 'TK', 'KT', 'AK', 'KEITTIÖ', 'KEITTIO', 'KEITTOKOMERO', 'TUPAKEITTIÖ', 'AVOKEITTIÖ', 'APUK', 'APUKEITTIÖ'},
    'bathroom': {'KH', 'KPH', 'PH', 'PESUH', 'PESUHUONE', 'SH', 'KYLPYH', 'KYLPYHUONE', 'SUIHKU', 'SUIHKUH'},
    'wc': {'WC'},
    'sauna': {'S', 'SAUNA', 'LÖYLYH', 'LÖYLYHUONE'},      # 'LH' dropped: ambiguous in practice ("LH+K")
    'balcony': {'PARV', 'PARVEKE', 'LASPARV', 'LASITETTUPARVEKE', 'RANSKALAINENPARVEKE'},
}
ONE_LETTER_MIN_CONF = 70      # single-letter labels (K, S) are easy to hallucinate from symbols
TWO_LETTER_MIN_CONF = 75
TWO_LETTER_MIN_CONF_BY = {'bedroom': 50}   # 'MH' is rarely hallucinated; recall matters more (dev set sweep 50/60/75)
# a lone "K" is too often a fixture/symbol misread (dev set: 18 false vs 8 true); kitchens keep their minimum of 1
ONE_LETTER_OK = set()   # lone 'S' (sauna) is net-neutral on the dev set and only adds false positives; the detector supplies recall


def tokens(text):
    t = text.upper().replace('0', 'O').replace('|', 'I')
    t = re.sub(r'^[^A-ZÄÖÅ0-9]+|[^A-ZÄÖÅ0-9.]+$', '', t)
    parts = [p.strip('.:;,()[]{}') for p in re.split(r'[+/&,\s]+', t)]
    out = []
    for p in parts:
        p = re.sub(r'\d+$', '', p)          # MH1, MH2 -> MH
        if p: out.append(p)
    return out


# a label read in the wrong orientation comes back reversed ("HM" for MH, "HO" for OH): accept reversals
# of multi-letter tokens that are not themselves another class's token
_ALL = {t for v in CLASS_TOKENS.values() for t in v}
_UPSIDE = str.maketrans('MW', 'WM')     # read upside down, M looks like W: "MH" -> "HW"
REVERSED = {}
for _c, _v in CLASS_TOKENS.items():
    for _t in _v:
        for _r in (_t[::-1], _t[::-1].translate(_UPSIDE)):
            if len(_t) >= 2 and _r not in _ALL and _r != _t:
                REVERSED.setdefault(_r, _c)
# "3H+K+S", "2h+kt", or the same split by OCR into "H+KK+S" / "SH+K": an apartment-type caption, not a room
DESCRIPTOR = re.compile(r'^\d+\s*[HM]\b|^\d*\s*S?H\s*\+\s*(K|KK|KT|TK|AK|RT|S)\b|=\s*\d', re.I)


def _ed1(a, b):
    """edit distance <= 1"""
    if abs(len(a) - len(b)) > 1: return False
    if len(a) == len(b): return sum(x != y for x, y in zip(a, b)) <= 1
    if len(a) > len(b): a, b = b, a
    return any(a == b[:i] + b[i + 1:] for i in range(len(b)))


LONG = [(t, c) for c, v in CLASS_TOKENS.items() for t in v if len(t) >= 5]


def classify(word, label_h=None):
    """room classes a single OCR'd label word stands for"""
    if DESCRIPTOR.match(word['text'].strip()):
        return []
    cls = []
    for p in tokens(word['text']):
        c = next((c for c, toks in CLASS_TOKENS.items() if p in toks), None)
        rev = c is None and p in REVERSED
        c = c or REVERSED.get(p) or (next((c for t, c in LONG if _ed1(p, t)), None) if len(p) >= 5 else None)
        if c is None:
            continue
        if len(p) <= 2 and word['conf'] < (85 if rev else TWO_LETTER_MIN_CONF_BY.get(c, TWO_LETTER_MIN_CONF)):
            continue
        if len(p) == 1:
            if c not in ONE_LETTER_OK and not word.get('_combined'):
                continue
            h = word['bbox'][3] - word['bbox'][1]
            if word['conf'] < ONE_LETTER_MIN_CONF or not label_h or not (0.7 * label_h <= h <= 1.4 * label_h):
                continue
        cls.append(c)
    return cls


def label_height(words):
    """typical printed room-label height on this plan, from confidently read multi-letter labels"""
    hs = sorted(w['bbox'][3] - w['bbox'][1] for w in words
                if w['conf'] >= 80 and any(len(p) >= 2 and (p in _ALL or p in REVERSED or p in ('OH', 'ET', 'VH', 'RT', 'KHH', 'TEKN', 'VAR'))
                                           for p in tokens(w['text'])))
    return hs[len(hs) // 2] if hs else None


FLOOR_RX = re.compile(r'^(\d\.?)?(KERROS|KRS\.?|KELLARI|ULLAKKO|POHJAKERROS|PARVI|VINTTI|KELLARIKERROS|ALAKERTA|YLÄKERTA|YLAKERTA)$', re.I)
FLOOR_WORDS = ['KERROS', 'ALAKERTA', 'YLÄKERTA', 'KELLARI', 'POHJAKERROS', 'KELLARIKERROS']
PAIRED = {'ALAKERTA', 'YLÄKERTA', 'YLAKERTA'}     # "lower floor" / "upper floor": the other one is drawn too


def floors(words):
    caps = []
    for w in words:
        t = w['text'].strip('.,:;').upper()
        if FLOOR_RX.match(t) or (len(t) >= 6 and w['conf'] >= 60 and any(_ed1(t, f) for f in FLOOR_WORDS)):
            caps.append(w)
    # one caption read twice (two binarisations / rotations) counts once
    out = []
    for w in sorted(caps, key=lambda w: -w['conf']):
        if not any(abs(w['bbox'][0] - k['bbox'][0]) < 20 and abs(w['bbox'][1] - k['bbox'][1]) < 20 for k in out):
            out.append(w)
    return out


# every dwelling has at least one kitchen and one bathroom: if no label is legible we answer the minimum and
# say so (receipt marks it low-confidence) instead of answering 0
MINIMUM = {'kitchen': 1, 'bathroom': 1}


def count(ocr, cls):
    ws = ocr['words']
    if cls == 'floors':
        caps = floors(ws)
        n = len(caps)
        if any(re.sub(r'[^A-ZÄ]', '', c['text'].upper()) in PAIRED for c in caps):
            n = max(n, 2)
        return max(1, n), caps
    lh = label_height(ws)
    # a lone "K" on the same line right after OH / RT is the kitchen part of a combined "OH + RT + K" label
    for w in ws:
        if w['text'].upper().strip('.:') == 'K' and lh:
            cy = (w['bbox'][1] + w['bbox'][3]) / 2
            w['_combined'] = any(v['text'].upper().strip('+.') in ('OH', 'RT', 'RK', 'TUPA') and abs((v['bbox'][1] + v['bbox'][3]) / 2 - cy) < 0.5 * lh
                                 and 0 < w['bbox'][0] - v['bbox'][2] < 5 * lh for v in ws)
    hit = []
    for w in sorted((w for w in ws if cls in classify(w, lh)), key=lambda w: -w['conf']):
        cx, cy = (w['bbox'][0] + w['bbox'][2]) / 2, (w['bbox'][1] + w['bbox'][3]) / 2
        r = 1.5 * (lh or (w['bbox'][3] - w['bbox'][1]))
        if any(abs(cx - (k['bbox'][0] + k['bbox'][2]) / 2) < r and abs(cy - (k['bbox'][1] + k['bbox'][3]) / 2) < r for k in hit):
            continue   # same label read twice (two binarisations / rotations)
        hit.append(w)
    return len(hit), hit


LABEL = {'bedroom': 'bedroom (MH)', 'kitchen': 'kitchen (K/KK/TK/KEITTIÖ)', 'bathroom': 'bathroom (KH/KPH/PH/SH)', 'wc': 'WC room',
         'sauna': 'sauna (SAUNA/LH)', 'balcony': 'balcony (PARVEKE)', 'floors': 'storey caption (n. kerros)'}
KINDS = {'bedrooms': 'bedroom', 'kitchens': 'kitchen', 'bathrooms': 'bathroom', 'wc_rooms': 'wc', 'saunas': 'sauna',
         'balconies': 'balcony', 'floors': 'floors'}     # keys used by raster/qa.py routing


def answer(path, kind):
    """kind: bedroom|kitchen|bathroom|wc|sauna|balcony|floors (or the qa.py keys in KINDS).
    Returns dict(value, unit, items[bbox in plan pixels], method, steps, confident)."""
    from . import ocr
    kind = KINDS.get(kind, kind)
    o = ocr.words(path)
    n, hits = count(o, kind)
    val, confident = n, n > 0
    steps = [f"Tesseract fin+eng OCR on the plan (x{ocr.SCALE} upscale, 2 binarisations, 4 rotations): {len(o['words'])} text fragments",
             f"Matched {n} {LABEL[kind]} label{'s' if n != 1 else ''}" + (f" (read as: {', '.join(sorted({h['text'] for h in hits}))})" if hits else '')]
    if kind == 'floors':
        confident = len(hits) > 0
        if not hits:
            steps.append('No storey caption ("1. kerros", "krs", "kellari") found: answered 1 storey')
    elif n < MINIMUM.get(kind, 0):
        val = MINIMUM[kind]
        steps.append(f"No legible {kind} label: a dwelling has at least one {kind}, so answered {val} (low confidence: check the plan)")
    items = [dict(kind=f'label_{kind}', label=f"{h['text']} · OCR {h['conf']:.0f}", bbox=h['bbox'], value=None,
                  check=None if h['conf'] >= 80 else dict(printed=h['text'], computed=h['conf'], ok=False, what='low OCR confidence'))
             for h in sorted(hits, key=lambda h: (h['bbox'][1], h['bbox'][0]))]
    return dict(value=val, unit='count', items=items, method=f'OCR room labels: {LABEL[kind]}', steps=steps, confident=confident)
