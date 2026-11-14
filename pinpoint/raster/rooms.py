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
    'sauna': {'S', 'SAUNA', 'LH', 'LÖYLYH', 'LÖYLYHUONE'},
    'balcony': {'PARV', 'PARVEKE', 'LASPARV', 'LASITETTUPARVEKE', 'RANSKALAINENPARVEKE'},
}
ONE_LETTER_MIN_CONF = 70      # single-letter labels (K, S) are easy to hallucinate from symbols


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
REVERSED = {t[::-1]: c for c, v in CLASS_TOKENS.items() for t in v if len(t) >= 2 and t[::-1] not in _ALL}
DESCRIPTOR = re.compile(r'^\d+\s*[HM]\b|^\d+[HM]\+', re.I)     # "3H+K+S", "2h+kt": apartment type, not a room


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
        c = c or REVERSED.get(p) or (next((c for t, c in LONG if _ed1(p, t)), None) if len(p) >= 4 else None)
        if c is None:
            continue
        if len(p) <= 2 and word['conf'] < (85 if rev else 75):
            continue
        if len(p) == 1:
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


FLOOR_RX = re.compile(r'^(KERROS|KRS\.?|KELLARI|ULLAKKO|POHJAKERROS|PARVI|VINTTI|KELLARIKERROS)$', re.I)


def floors(words):
    caps = [w for w in words if FLOOR_RX.match(w['text'].strip('.,:'))]
    return caps


# every dwelling has at least one kitchen and one bathroom: if no label is legible we answer the minimum and
# say so (receipt marks it low-confidence) instead of answering 0
MINIMUM = {'kitchen': 1, 'bathroom': 1}


def count(ocr, cls):
    ws = ocr['words']
    if cls == 'floors':
        caps = floors(ws)
        return max(1, len(caps)), caps
    lh = label_height(ws)
    hit = []
    for w in sorted((w for w in ws if cls in classify(w, lh)), key=lambda w: -w['conf']):
        cx, cy = (w['bbox'][0] + w['bbox'][2]) / 2, (w['bbox'][1] + w['bbox'][3]) / 2
        r = 1.5 * (lh or (w['bbox'][3] - w['bbox'][1]))
        if any(abs(cx - (k['bbox'][0] + k['bbox'][2]) / 2) < r and abs(cy - (k['bbox'][1] + k['bbox'][3]) / 2) < r for k in hit):
            continue   # same label read twice (two binarisations / rotations)
        hit.append(w)
    return len(hit), hit
