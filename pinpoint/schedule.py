"""Schedules on vector PDF sheets (door / window / finish / door-type schedules), no LLM.

1. words -> display coordinates (page rotation applied) -> text lines
2. a table = a run of lines whose first token looks like an id (101.A, 118.B2, U01, SS, 108 SF...) at the
   same x; columns = x-starts that recur in most rows; headers = words stacked above each column
3. the question picks a table (by title words) and an operation: count rows / count rows whose cell matches
   a code / look up a cell / sum an area column. Evidence = the matching rows, boxed on the sheet."""
import re
import collections, functools
from urllib.parse import quote
import pymupdf

ID_RX = re.compile(r"^(\d{2,4}\.[A-Z]{1,2}\d?|[A-Z]{1,2}\d{2,3}|[A-Z]{2}|\d{2,6}\s?SF|\d{3}[A-Z]?)$")


@functools.lru_cache(maxsize=16)
def sheet(path):
    pg = pymupdf.open(path)[0]
    M = pg.rotation_matrix
    words = []
    for w in pg.get_text('words'):
        r = pymupdf.Rect(w[:4]) * M
        words.append((r.x0, r.y0, r.x1, r.y1, w[4]))
    W, H = (pg.rect.width, pg.rect.height)
    return words, W, H, tables(words)


def lines_of(words, tol=3.0):
    ws = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in ws:
        y = (w[1] + w[3]) / 2
        if cy is None or abs(y - cy) <= tol:
            cur.append(w); cy = y if cy is None else (cy * (len(cur) - 1) + y) / len(cur)
        else:
            lines.append(sorted(cur)); cur, cy = [w], y
    if cur: lines.append(sorted(cur))
    return lines


def split_segments(line, gap=95):
    """a sheet line can cross several tables: split where words are far apart"""
    segs, cur = [], [line[0]]
    for w in line[1:]:
        if w[0] - cur[-1][2] > gap: segs.append(cur); cur = [w]
        else: cur.append(w)
    segs.append(cur)
    # drop sheet-border grid labels ("C", "4") glued to the left of a table row
    segs = [sg[1:] if len(sg) > 2 and len(sg[0][4]) == 1 and sg[0][4].isalpha() and sg[1][0] - sg[0][2] > 40 else sg for sg in segs]
    return segs


def tables(words):
    segs = [s for l in lines_of(words) for s in split_segments(l)]
    # candidate rows: segment starting with an id-like token and having >= 3 words
    def is_row(s):
        if len(s) < 3: return False
        if s[0][4].isdigit() and s[1][4] == 'SF': return True                        # "108 SF" area-first rows
        if s[0][4] == 'Redundant' and re.match(r'^\d{3}$', s[1][4]): return True     # finish rows without an area
        if re.match(r'^\d{1,4}$', s[0][4]) and re.match(r'^[A-Z]{1,2}\d{1,3}(-[A-Z]{1,2})?$|^[A-Z]{2}$', s[1][4]): return True   # "71 U01" count-first rows
        return bool(ID_RX.match(s[0][4]))
    cand = [s for s in segs if is_row(s)]
    # cluster rows by the alignment edge of their id (left for codes, right for right-aligned "108 SF")
    keyed = []
    for s in cand:
        if s[0][4].isdigit() and len(s) > 1 and s[1][4] == 'SF': keyed.append((('r', s[1][2]), s))
        elif s[0][4] == 'Redundant': keyed.append((('r', s[0][0] + 38), s))
        else: keyed.append((('l', s[0][0]), s))
    by_x = collections.defaultdict(list)
    for side in ('l', 'r'):
        pts = sorted((k[1], i) for i, (k, s) in enumerate(keyed) if k[0] == side)
        cl, last = 0, None
        for x, i in pts:
            if last is not None and x - last > 8: cl += 1
            by_x[(side, cl)].append(keyed[i][1]); last = x
    out = []
    for key, rows in by_x.items():
        rows.sort(key=lambda s: s[0][1])
        run = [rows[0]]
        def continues(a, b):
            gap = b[0][1] - a[0][1]
            if gap <= 45: return True
            if gap > 160: return False
            # multi-line descriptions: nothing else starts in the id column between the two rows
            x = a[0][0]
            return not any(a[0][1] + 3 < sg[0][1] < b[0][1] - 3 and abs(sg[0][0] - x) < 25 for sg in segs)
        for s in rows[1:]:
            if continues(run[-1], s): run.append(s)
            else:
                if len(run) >= 4: out.append(run)
                run = [s]
        if len(run) >= 4: out.append(run)
    return [build(t, segs) for t in out]


def build(rows, segs):
    x0 = min(s[0][0] for s in rows); x1 = max(s[-1][2] for s in rows)
    y0 = rows[0][0][1]; y1 = max(w[3] for w in rows[-1])
    # column starts recurring in >= 35% of rows
    starts = collections.Counter()
    for s in rows:
        prev = None
        for w in s:
            if prev is None or w[0] - prev[2] > 4.5:
                starts[round(w[0] / 4)] += 1
            prev = w
    cols = sorted(k * 4 for k, n in starts.items() if n >= 0.35 * len(rows))
    merged = []
    for c in cols:
        if not merged or c - merged[-1] > 9: merged.append(c)
    cols = merged

    def cells(s):
        out = [''] * len(cols)
        for w in s:
            i = max([j for j, c in enumerate(cols) if c <= w[0] + 5] or [0])
            out[i] = (out[i] + ' ' + w[4]).strip()
        return out

    # headers: words in the 60 pt above the first row inside the table's x-span
    hdr = [''] * len(cols)
    above = sorted([w for seg in segs for w in seg if y0 - 70 < w[1] < y0 - 1 and x0 - 10 < w[0] < x1 + 10], key=lambda w: (w[1], w[0]))
    for w in above:
        i = max([j for j, c in enumerate(cols) if c <= w[0] + 8] or [0])
        hdr[i] = (hdr[i] + ' ' + w[4]).strip()
    title = ' '.join(w[4] for w in above if w[1] < y0 - 40)[:80]
    # title: nearest line containing 'schedule' above the table
    tl = [s for s in segs if any('schedul' in w[4].lower() for w in s) and s[0][1] < y0 and y0 - s[0][1] < 260 and x0 - 60 < s[0][0] < x1]
    if tl:
        title = ' '.join(w[4] for w in max(tl, key=lambda s: s[0][1]))
    return dict(title=title, cols=cols, headers=hdr, bbox=[x0, y0, x1, y1],
                rows=[dict(count=(int(s[0][4]) if s[1][4] != 'SF' and re.match(r'^\d{1,4}$', s[0][4]) and re.match(r'^[A-Z]{1,2}\d{1,3}(-[A-Z]{1,2})?$|^[A-Z]{2}$', s[1][4]) else None),
                           desc=' '.join(w[4] for w in s[2:]), id=(s[1][4] if s[1][4] != 'SF' and re.match(r'^\d{1,4}$', s[0][4]) and re.match(r'^[A-Z]{1,2}\d{1,3}(-[A-Z]{1,2})?$|^[A-Z]{2}$', s[1][4]) else
                               s[0][4] + (' SF' if len(s) > 1 and s[1][4] == 'SF' else '')), cells=cells(s), bbox=[min(w[0] for w in s), min(w[1] for w in s), max(w[2] for w in s), max(w[3] for w in s)]) for s in rows])


def nz(t):
    return re.sub(r'\s+', '', t or '').upper()


def pick_table(tabs, q):
    ql = q.lower()
    def score(t):
        tl = (t['title'] + ' ' + ' '.join(t['headers'])).lower()
        s = 0
        for kw in ('door', 'window', 'finish', 'room', 'type', 'hardware'):
            if kw in ql and kw in tl: s += 2
        if 'door type schedule' in ql and 'type' in tl: s += 3
        if re.search(r'finish|room schedule', ql) and 'finish' in tl: s += 4
        if 'door schedule' in ql and 'door' in tl and 'finish' not in tl: s += 3
        if 'window' in ql and 'window' in tl: s += 4
        return s + len(t['rows']) / 1000
    return max(tabs, key=score) if tabs else None


def col_for(t, *keys):
    for k in keys:
        for i, h in enumerate(t['headers']):
            if k in h.lower(): return i
    return None


def answer(path, q):
    words, W, H, tabs = sheet(path)
    t = pick_table(tabs, q)
    base = [f"Read {len(words)} vector words from the sheet (rotation applied); found {len(tabs)} schedule tables by their id columns"]
    if t is None:
        return dict(value=None, unit=None, items=[], method='no schedule found', steps=base, view=None)
    ql = q.lower()
    steps = base + [f"Chose “{t['title'] or 'untitled'}”: {len(t['rows'])} rows, columns: " + ' | '.join(h or '·' for h in t['headers'])]
    rows = t['rows']
    item = lambda r, i: dict(kind='row', label=' · '.join(c for c in r['cells'][:4] if c), bbox=r['bbox'], value=None)

    # lookup: "door 121.A", "room 128"
    m = re.search(r'door (\d{2,4}\.[A-Z]\d?)', q)
    key = m.group(1) if m else None
    if key and re.search(r'what|which', ql) and not re.search(r'how many', ql):
        r = next((r for r in rows if nz(r['id']) == nz(key)), None)
        if r:
            ci = col_for(t, 'width') if 'width' in ql and 'height' not in ql else col_for(t, 'height') if 'height' in ql and 'width' not in ql else \
                col_for(t, 'hardware') if 'hardware' in ql else col_for(t, 'type') if 'type' in ql else col_for(t, 'matl', 'material') if 'material' in ql else None
            if 'width' in ql and 'height' in ql:
                a, b = col_for(t, 'width'), col_for(t, 'height')
                val = f"{r['cells'][a]} wide x {r['cells'][b]} high"
            else:
                val = r['cells'][ci] if ci is not None else ' | '.join(r['cells'])
            return dict(value=val, unit='text', items=[item(r, 0)], method=f'schedule lookup: row {key}', steps=steps + [f"Row {key}, column “{t['headers'][ci] if ci is not None else 'all'}”"])

    # area questions on a finish/room schedule
    ai = col_for(t, 'area')
    num = lambda c: float(re.sub(r'[^\d.]', '', c) or 0) if re.search(r'\d', c or '') else None
    rm = re.search(r'room (\d{2,4})', q)
    if ai is not None and 'area' in ql:
        ni = col_for(t, 'number', 'no')
        sel = rows
        if rm and ni is not None:
            sel = [r for r in rows if nz(r['cells'][ni]) == rm.group(1)]
        elif re.search(r"named (\w+)", q):
            nm = re.search(r"named (\w+)", q).group(1).upper()
            ni2 = col_for(t, 'name')
            sel = [r for r in rows if ni2 is not None and nz(r['cells'][ni2]) == nm]
        elif 'locker' in ql:
            ni2 = col_for(t, 'name'); sel = [r for r in rows if ni2 is not None and 'LOCKER' in nz(r['cells'][ni2])]
        else:
            fm = re.search(r'floor finish (F\d)', q)
            if fm:
                fi = col_for(t, 'floor'); sel = [r for r in rows if fi is not None and fm.group(1) in r['cells'][fi]]
        if 'largest' in ql:
            r = max(rows, key=lambda r: num(r['cells'][ai]) or 0)
            return dict(value=' '.join(r['cells'][:3]), unit='text', items=[item(r, 0)], method='max of Area column', steps=steps + ["Compared the Area column"])
        sel = [r for r in sel if num(r['cells'][ai])]
        tot = sum(num(r['cells'][ai]) for r in sel)
        its = [dict(item(r, 0), value=num(r['cells'][ai])) for r in sel]
        if re.search(r'how many rooms', ql):
            return dict(value=f"{len(sel)} rooms, {tot:g} SF", unit='text', items=its, method='count + sum of Area column', steps=steps + [f"{len(sel)} matching rows; summed Area"])
        return dict(value=round(tot, 2), unit='SF', items=its, method='sum of Area column', steps=steps + [f"Selected {len(sel)} rows; summed the Area column"])

    # counting rows
    if re.search(r'how many', ql):
        codes = re.findall(r"\b(?:[A-Z]{1,3}-\d{1,2}|[A-Z]\d{1,2}|U\d{2})\b", q)
        tm = re.search(r"\btypes? ((?:[A-Z]{2}\b(?:,? (?:and |or )?)?)+)", q)
        if tm: codes += re.findall(r'[A-Z]{2}', tm.group(1))
        codes = [c for c in codes if c not in ('WI', 'SF')]
        dims = re.findall(r"(\d+'-\d+(?: \d+/\d+)?\")", q)
        note = re.search(r'note ([A-Z])\b', q)
        sel = rows
        why = 'all rows'
        if note:
            # the Notes column sits far right of the row: read same-baseline single-letter tokens up to 300 pt to the right
            def notes(r):
                yc = (r['bbox'][1] + r['bbox'][3]) / 2
                return [w[4].strip(',') for w in words if abs((w[1] + w[3]) / 2 - yc) < 2.5 and r['bbox'][2] < w[0] < r['bbox'][2] + 300
                        and re.match(r'^[A-Z],?$', w[4])]
            sel = [r for r in rows if note.group(1) in notes(r)]
            for r in sel:
                xs = [w[2] for w in words if abs((w[1] + w[3]) / 2 - (r['bbox'][1] + r['bbox'][3]) / 2) < 2.5 and r['bbox'][2] < w[0] < r['bbox'][2] + 300]
                r = r
            why = f"the Notes column (same row, right of the table body) lists {note.group(1)}"
        elif codes:
            want = set(codes)
            sel = [r for r in rows if any(p in want for c in r['cells'] for p in re.split(r'[/\s,]+', c))]
            why = 'a cell equals ' + ' or '.join(sorted(want))
        elif rm and 'door' in ql:
            ci = col_for(t, 'room number', 'number')
            ci = 2 if ci == 0 else ci
            sel = [r for r in rows if any(nz(c) == rm.group(1) for c in r['cells'][1:4])]
            why = f"room number = {rm.group(1)}"
        elif dims:
            ci = col_for(t, 'height') if re.search(r'high|height', ql) else col_for(t, 'width')
            sel = [r for r in rows if ci is not None and nz(r['cells'][ci]) == nz(dims[0])]
            why = f"{t['headers'][ci] if ci is not None else '?'} = {dims[0]}"
        if rows and rows[0].get('count') is not None:   # count-first type schedule ("71 U01 UNIT DOOR")
            if not codes and not dims:
                # product / floor words from the question that appear in row descriptions (e.g. MARVIN, VISTAGRANDE, 3RD FLOOR)
                stop = {'SHEET', 'DRAWINGS', 'CANNERY', 'TRAIL', 'RESIDENCES', 'OXFORD', 'CLAIRE', 'SCHEDULED', 'TOTAL', 'DOORS', 'WINDOWS', 'FLOOR'}
                kws = [w.upper() for w in re.findall(r"[A-Za-z]{5,}", q) if w.upper() not in stop and any(w.upper() in r['desc'] for r in rows)]
                fl = re.search(r'(\d)(?:st|nd|rd|th) floor', ql)
                sw = re.search(r"starts? with '([A-Z]+)'", q)
                sel = rows
                if re.search(r'in total|all type marks', ql) and not sw:
                    sel = rows; why = 'all type marks'
                elif sw:
                    sel = [r for r in sel if r['desc'].startswith(sw.group(1))]; why = 'description starts with ' + sw.group(1)
                elif kws:
                    sel = [r for r in sel if all(k in r['desc'] for k in kws)]; why = 'description contains ' + ' + '.join(kws)
                else:
                    why = 'all rows'
                if fl:
                    sel = [r for r in sel if re.search(fl.group(1) + r'(ST|ND|RD|TH) FLOOR', r['desc'])]; why += ', ' + fl.group(0)
            its = [dict(item(r, 0), value=r['count']) for r in sel]
            tot = sum(r['count'] for r in sel)
            return dict(value=tot, unit='count', items=its, method=f'sum of the Count column where {why}',
                        steps=steps + [f"Kept type rows where {why}: {len(sel)}", f"Each row carries its own quantity → summed Count = {tot}"])
        qi = col_for(t, 'count', 'qty', 'quantity')
        if qi is not None and qi > 0:   # aggregated schedule: one row per type, quantity in a Count column
            its = [dict(item(r, 0), value=num(r['cells'][qi])) for r in sel]
            tot = int(sum(num(r['cells'][qi]) or 0 for r in sel))
            return dict(value=tot, unit='count', items=its, method=f'sum of Count column where {why}',
                        steps=steps + [f"Kept rows where {why}: {len(sel)}", f"Schedule is aggregated → summed its Count column = {tot}"])
        its = [item(r, 0) for r in sel]
        return dict(value=len(sel), unit='count', items=its, method=f'count schedule rows where {why}', steps=steps + [f"Kept rows where {why}: {len(sel)}"])
    return dict(value=None, unit=None, items=[], method='not routed', steps=steps + ['No schedule operation matched'])


def view(path, rel):
    words, W, H, _ = sheet(path)
    return dict(kind='sheet', url=f'/api/sheet?path={quote(rel)}', w=W, h=H)
