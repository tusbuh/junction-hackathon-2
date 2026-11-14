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
    words = glue_dims(words)
    return words, W, H, tables(words)


DIM_START = re.compile(r"^\d+'$")


def glue_dims(words):
    """Imperial dimensions are often stored as separate words: 2' | - | 11 | 3/16" -> one word 2'-11 3/16"."""
    out = []
    for l in lines_of(words):
        i = 0
        while i < len(l):
            w = l[i]
            if DIM_START.match(w[4]) and i + 1 < len(l) and l[i + 1][4].startswith('-') and l[i + 1][0] - w[2] < 10:
                parts, j = [w], i + 1
                while j < len(l) and l[j][0] - parts[-1][2] < 10 and len(parts) < 5:
                    parts.append(l[j]); j += 1
                    if parts[-1][4].endswith('"'): break
                if parts[-1][4].endswith('"'):
                    txt = parts[0][4] + '-' + ' '.join(x[4] for x in parts[1:]).lstrip('-').strip()
                    out.append((parts[0][0], min(x[1] for x in parts), parts[-1][2], max(x[3] for x in parts), txt))
                    i = j; continue
            out.append(w); i += 1
    return out


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
    # header band: words in the 70 pt above the first row, chained rightwards from the table's left edge
    band = sorted([w for seg in segs for w in seg if y0 - 70 < w[1] < y0 - 1 and x0 - 10 < w[0]], key=lambda w: w[0])
    xr = x1
    for w in band:
        if w[0] > xr + 120: break
        xr = max(xr, w[2])
    # full rows: every word on the row's baseline inside [x0, xr] (segments split at wide gaps lose finish columns)
    allw = [w for seg in segs for w in seg]
    full = []
    for s in rows:
        yc = (s[0][1] + s[0][3]) / 2
        ws = sorted([w for w in allw if abs((w[1] + w[3]) / 2 - yc) < 3 and x0 - 5 <= w[0] <= xr + 5], key=lambda w: w[0])
        full.append(ws or s)
    # columns = x-intervals covered by row words, separated by whitespace no row crosses; words closer than
    # 9 pt stay in one cell ("W1 & W2", "SEE ELEV.")
    lo = int(min(w[0] for s in full for w in s)); hi = int(max(w[2] for s in full for w in s)) + 2
    cov = [0] * (hi - lo + 1)
    for s in full:
        seen = set()
        for w in s:
            seen.update(range(int(w[0]) - lo, int(w[2]) - lo + 1))
        for x in seen: cov[x] += 1
    th = 1
    cols_iv = []
    for x, c in enumerate(cov):
        if c >= th:
            if cols_iv and x + lo - cols_iv[-1][1] <= 9: cols_iv[-1][1] = x + lo
            else: cols_iv.append([x + lo, x + lo])
    cols = [c[0] for c in cols_iv]

    def ci_of(x0w, x1w):
        cx = (x0w + x1w) / 2
        for i, (a, b) in enumerate(cols_iv):
            if a - 2 <= cx <= b + 2: return i
        return min(range(len(cols_iv)), key=lambda i: min(abs(cx - cols_iv[i][0]), abs(cx - cols_iv[i][1])))

    def cells(s):
        out = [''] * len(cols)
        for w in s:
            i = ci_of(w[0], w[2])
            out[i] = (out[i] + ' ' + w[4]).strip()
        return out

    hdr = [''] * len(cols)
    above = sorted([w for w in band if w[0] <= xr + 5], key=lambda w: (round(w[1]), w[0]))
    # header phrases (words on one header line closer than a few points) go to the column they overlap most
    for ln in lines_of([w for w in above if 'schedul' not in w[4].lower()], tol=2.0):
        ph = [[ln[0]]]
        for w in ln[1:]:
            if w[0] - ph[-1][-1][2] < 7: ph[-1].append(w)
            else: ph.append([w])
        for p in ph:
            a, b = p[0][0], p[-1][2]
            ov = [max(0, min(b, cb + 6) - max(a, ca - 6)) for ca, cb in cols_iv]
            i = max(range(len(ov)), key=lambda k: ov[k]) if max(ov) > 0 else ci_of(a, b)
            hdr[i] = (hdr[i] + ' ' + ' '.join(w[4] for w in p)).strip()
    title = ' '.join(w[4] for w in above if w[1] < y0 - 40)[:80]
    # title: nearest line containing 'schedule' above the table
    tl = [s for s in segs if any('schedul' in w[4].lower() for w in s) and s[0][1] < y0 and y0 - s[0][1] < 260 and x0 - 60 < s[0][0] < x1]
    if tl:
        title = ' '.join(w[4] for w in max(tl, key=lambda s: s[0][1]))
    cf = lambda s: re.match(r'^\d{1,4}$', s[0][4]) and len(s) > 1 and s[1][4] != 'SF' and re.match(r'^[A-Z]{1,2}\d{1,3}(-[A-Z]{1,2})?$|^[A-Z]{2}$', s[1][4])
    return dict(title=title, cols=cols, headers=hdr, bbox=[x0, y0, max(x1, xr), y1],
                rows=[dict(count=(int(s[0][4]) if cf(s) else None),
                           desc=' '.join(w[4] for w in s[2:]), id=(s[1][4] if cf(s) else s[0][4] + (' SF' if len(s) > 1 and s[1][4] == 'SF' else '')),
                           cells=cells(f), bbox=[min(w[0] for w in f), min(w[1] for w in f), max(w[2] for w in f), max(w[3] for w in f)])
                      for s, f in zip(rows, full)])


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
        if re.search(r'finish|room schedule|ceiling|wall|\bbase\b', ql) and 'finish' in tl: s += 4
        if re.search(r'\barea\b|largest|smallest', ql) and col_for(t, 'area') is not None: s += 4
        if 'door schedule' in ql and 'door' in tl and 'finish' not in tl: s += 3
        if 'window' in ql and 'window' in tl: s += 4
        return s + len(t['rows']) / 1000
    return max(tabs, key=score) if tabs else None


def col_for(t, *keys):
    for k in keys:
        for i, h in enumerate(t['headers']):
            if k in h.lower(): return i
    return None


# question phrase -> header keywords (most specific first)
COLQ = [(r'fire', ('fire',)), (r'frame (?:material|matl)|frames?\b', ('frame material', 'frame matl', 'frame')),
        (r'door (?:material|matl)|material', ('door material', 'door matl', 'matl', 'material')),
        (r'hardware', ('hardware',)), (r'notes?\b', ('notes',)),
        (r'north wall', ('north',)), (r'south wall', ('south',)), (r'east wall', ('east',)), (r'west wall', ('west',)),
        (r'floor finish|floor', ('floor',)), (r'\bbase\b', ('base',)), (r'ceiling', ('ceiling',)),
        (r'door type|\btype\b', ('door type', 'type')), (r'width|wide', ('width',)), (r'height|high', ('height',))]
CODE_RX = r"[A-Z]{1,3}-\d{1,2}|[A-Z]\d{1,2}|U\d{2}|[A-Z]{2}"


def q_cols(t, ql):
    """columns the question names, in the order they are mentioned (the asked attribute comes first)"""
    out = []
    for rx, keys in COLQ:
        m = re.search(rx, ql)
        if m:
            c = col_for(t, *keys)
            if c is not None and c not in [o[1] for o in out]: out.append((m.start(), c))
    return [c for _, c in sorted(out)]


def legend(words, tabs, code):
    """What a code means on this sheet: an inline legend line ('F4 RESILIENT FLOORING (T.B.D.)') or a
    labelled elevation ('DOOR TYPE B3' with the description printed underneath)."""
    inside = lambda w: any(b[0] - 5 <= w[0] <= b[2] + 5 and b[1] - 5 <= w[1] <= b[3] + 5 for b in (tb['bbox'] for tb in tabs))
    for l in lines_of(words):
        for i, w in enumerate(l):
            if w[4] != code or inside(w): continue
            rest = []
            for x in l[i + 1:]:
                if x[0] - (rest[-1][2] if rest else w[2]) > (80 if not rest else 40): break
                rest.append(x)
            txt = ' '.join(x[4] for x in rest).strip(' -:')
            if i == 0 or l[i - 1][4].upper() != 'TYPE':
                if len(rest) >= 1 and re.search(r'[A-Z]{3,}', txt):
                    return txt, w
            else:   # label "TYPE B3": description = the lines right under the label, same column
                lx = l[i - 2][0] if i >= 2 and l[i - 2][4].upper() == 'DOOR' else l[i - 1][0]
                nxt = min([x[0] for x in l[i + 1:] if x[0] > w[2]] or [lx + 160])
                below = [x for x in words if w[3] < x[1] < w[3] + 40 and lx - 6 <= x[0] < nxt - 6]
                if below:
                    return ' '.join(x[4] for ln in lines_of(below) for x in ln), w
    return None, None


# standard US drawing abbreviations for door / frame materials (shown next to the scheduled code)
ABBR = {'HM': 'hollow metal', 'WD': 'wood', 'AL': 'aluminium', 'ALUM': 'aluminium', 'FG': 'fiberglass', 'STL': 'steel',
        'GL': 'glass', 'SCW': 'solid core wood', 'HCW': 'hollow core wood', 'MTL': 'metal', 'VNL': 'vinyl'}


def decode(words, tabs, val):
    codes = re.findall(r'\b(?:' + CODE_RX + r')\b', val or '')
    parts, hits = [], []
    for c in codes:
        d, w = legend(words, tabs, c)
        if d:
            parts.append(d); hits.append((c, d, w))
    if not parts:
        return val, []
    return f"{val} - {'; '.join(parts)}", hits


def answer(path, q):
    words, W, H, tabs = sheet(path)
    t = pick_table(tabs, q)
    base = [f"Read {len(words)} vector words from the sheet (rotation applied); found {len(tabs)} schedule tables by their id columns"]
    if t is None:
        return dict(value=None, unit=None, items=[], method='no schedule found', steps=base, view=None)
    ql = q.lower()
    steps = base + [f"Chose “{t['title'] or 'untitled'}”: {len(t['rows'])} rows, columns: " + ' | '.join(h or '·' for h in t['headers'])]
    rows = t['rows']
    hdr = lambda i: t['headers'][i] if i is not None and t['headers'][i] else f'col {i}'
    item = lambda r, i=0: dict(kind='row', label=' · '.join(c for c in r['cells'][:4] if c), bbox=r['bbox'], value=None)
    num = lambda c: float(re.sub(r'[^\d.]', '', c) or 0) if re.search(r'\d', c or '') else None
    toks = lambda c: [p for p in re.split(r'[/\s,&]+', c or '') if p]
    cols = q_cols(t, ql)
    ai = col_for(t, 'area')
    ni = col_for(t, 'room name', 'name')

    # ---- row keys named in the question: door numbers, type marks, room numbers
    door_ids = re.findall(r'\b\d{2,4}\.[A-Z]{1,2}\d?\b', q)
    tm = re.findall(r'\btypes? ((?:' + CODE_RX + r')(?:-[A-Z]{1,2})?)\b', q)
    rooms = re.findall(r'room (\d{2,4})\b', q)
    def rows_for(key):
        k = nz(key)
        hit = [r for r in rows if nz(r['id']) == k]
        if not hit:
            hit = [r for r in rows if any(nz(c) == k for c in r['cells'][:3])]
        return hit

    lookup = re.search(r'\b(what|which)\b', ql) and not re.search(r'how many|combined|total area|sum', ql) \
        and not (ai is not None and re.search(r'\barea\b', ql))
    if lookup and 'largest' not in ql and 'smallest' not in ql:
        keys = door_ids[:1] or rooms[:1] or tm[:1]
        sel = rows_for(keys[0]) if keys else []
        if not sel and not keys and cols:
            # no row named: a value common to every row ("the width of a window unit")
            sel = rows
        if sel:
            want_wh = re.search(r'width', ql) and re.search(r'height', ql)
            if want_wh:
                a, b = col_for(t, 'width'), col_for(t, 'height')
                vals = sorted({f"{r['cells'][a]} wide x {r['cells'][b]} high" for r in sel})
                ci = a
            else:
                ci = cols[0] if cols else None
                vals = sorted({r['cells'][ci] for r in sel}) if ci is not None else [' | '.join(sel[0]['cells'])]
            if len(vals) == 1:
                val = vals[0]
                its = [item(r) for r in sel[:12]]
                st = [f"Row{'s' if len(sel) > 1 else ''} {', '.join(r['id'] for r in sel[:6])}{'…' if len(sel) > 6 else ''}: column “{hdr(ci)}” = {val}"]
                h = hdr(ci).lower()
                if re.search(r'material|matl', h) and val.strip().upper() in ABBR:
                    val = f"{val} ({ABBR[val.strip().upper()]})"
                    st.append(f"Abbreviation {val}")
                elif re.search(r'mean|what kind|stand for', ql) or re.search(r'finish|type|wall|ceiling|base|floor|material|matl', h) and not want_wh:
                    dv, hits = decode(words, tabs, val)
                    if hits:
                        val = dv
                        for c, d, w in hits:
                            st.append(f"Legend on the same sheet: {c} = {d}")
                            its.append(dict(kind='legend', label=f'{c}: {d}', bbox=[w[0] - 2, w[1] - 2, w[2] + 200, w[3] + 2], value=None))
                return dict(value=val, unit='text', items=its, method=f'schedule lookup: {hdr(ci)} of {keys[0] if keys else "every row"}', steps=steps + st)

    # ---- area questions on a finish/room schedule
    if ai is not None and re.search(r'\barea\b|largest|smallest', ql):
        sel, why = rows, 'all rows'
        if rooms:
            sel = [r for r in rows for k in rooms if nz(r['cells'][col_for(t, 'number') or 1]) == k]; why = 'room ' + ', '.join(rooms)
        elif ni is not None:
            qt = {w.upper().rstrip("'S").replace("’S", '') for w in re.findall(r"[A-Za-z’']+", q)}
            qt |= {w.upper() for w in re.findall(r"[A-Za-z]+", q)}
            def named(r):
                nt = [w.rstrip("'S").replace("’S", '') for w in re.findall(r"[A-Z’']+", r['cells'][ni].upper()) if len(w) > 1]
                return nt and all(w in qt for w in nt)
            m = [r for r in rows if named(r)]
            if m and not re.search(r'largest|smallest', ql): sel, why = m, 'room name in the question'
        codes = [c for c in re.findall(r'\b(?:' + CODE_RX + r')\b', q) if c not in ('SF',)]
        if codes and cols:
            sel = [r for r in rows if any(p in codes for p in toks(r['cells'][cols[0]]))]; why = f"{hdr(cols[0])} = {'/'.join(codes)}"
        if re.search(r'largest|smallest', ql):
            f = max if 'largest' in ql else min
            r = f([r for r in sel if num(r['cells'][ai])], key=lambda r: num(r['cells'][ai]))
            val = f"Room {r['cells'][col_for(t, 'number') or 1]} {r['cells'][ni] if ni is not None else ''} ({r['cells'][ai]})"
            return dict(value=val, unit='text', items=[item(r)], method=f'{f.__name__} of Area column', steps=steps + ["Compared the Area column of every row"])
        sel = [r for r in sel if num(r['cells'][ai])]
        tot = sum(num(r['cells'][ai]) for r in sel)
        its = [dict(item(r), value=num(r['cells'][ai])) for r in sel]
        if re.search(r'how many rooms', ql):
            return dict(value=f"{len(sel)} rooms, {tot:g} SF", unit='text', items=its, method='count + sum of Area column', steps=steps + [f"{len(sel)} rows where {why}; summed Area = {tot:g} SF"])
        return dict(value=round(tot, 2), unit='SF', items=its, method='sum of Area column', steps=steps + [f"Selected {len(sel)} rows where {why}; summed the Area column = {tot:g} SF"])

    # ---- counting rows
    if re.search(r'how many', ql):
        codes = re.findall(r"\b(?:[A-Z]{1,3}-\d{1,2}|[A-Z]\d{1,2}|U\d{2})\b", q)
        tm2 = re.search(r"\btypes? ((?:[A-Z]{2}\b(?:,? (?:and |or )?)?)+)", q)
        if tm2: codes += re.findall(r'[A-Z]{2}', tm2.group(1))
        codes = [c for c in codes if c not in ('WI', 'SF')]
        dims = re.findall(r"(\d+'-\d+(?: \d+/\d+)?\")", q)
        note = re.search(r'note ([A-Z])\b', q)
        sel, why = rows, 'all rows'
        if note:
            ci = col_for(t, 'notes')
            if ci is not None:
                sel = [r for r in rows if note.group(1) in toks(r['cells'][ci])]
            else:   # Notes column outside the table body: same-baseline single letters up to 300 pt to the right
                def notes(r):
                    yc = (r['bbox'][1] + r['bbox'][3]) / 2
                    return [w[4].strip(',') for w in words if abs((w[1] + w[3]) / 2 - yc) < 2.5 and r['bbox'][2] < w[0] < r['bbox'][2] + 300
                            and re.match(r'^[A-Z],?$', w[4])]
                sel = [r for r in rows if note.group(1) in notes(r)]
            why = f"the Notes column lists {note.group(1)}"
        elif codes:
            want = set(codes)
            # which columns hold these codes; the question's column words narrow it ("frames", "base", "walls")
            holders = [i for i in range(len(t['headers'])) if any(p in want for r in rows for p in toks(r['cells'][i]))]
            named = [i for i in cols if i in holders]
            if cols and holders and not named:   # stacked headers can sit one column off: the holder nearest the named column
                named = [min(holders, key=lambda i: abs(i - cols[0]))]
            if re.search(r'all (?:four )?walls', ql):
                wc = [i for i in range(len(t['headers'])) if 'wall' in t['headers'][i].lower()]
                sel = [r for r in rows if wc and all(toks(r['cells'][i]) and set(toks(r['cells'][i])) <= want for i in wc)]
                why = f"all {len(wc)} wall columns = {'/'.join(sorted(want))}"
            elif named:
                sel = [r for r in rows if any(p in want for i in named[:1] for p in toks(r['cells'][i]))]
                why = f"{hdr(named[0])} = {' or '.join(sorted(want))}"
            else:
                sel = [r for r in rows if any(p in want for c in r['cells'] for p in toks(c))]
                why = 'a cell equals ' + ' or '.join(sorted(want))
        elif rooms and 'door' in ql:
            sel = [r for r in rows if any(nz(c) == rooms[0] for c in r['cells'][1:4])]
            why = f"room number = {rooms[0]}"
        elif dims:
            ci = col_for(t, 'height') if re.search(r'high|height', ql) else col_for(t, 'width')
            sel = [r for r in rows if ci is not None and nz(r['cells'][ci]) == nz(dims[0])]
            why = f"{hdr(ci)} = {dims[0]}"
        nwide = re.search(r'every n-wide', ql)
        if rows and rows[0].get('count') is not None:   # count-first type schedule ("71 U01 UNIT DOOR")
            if not codes and not dims:
                # product / floor words from the question that appear in row descriptions (e.g. MARVIN, VISTAGRANDE, 3RD FLOOR)
                stop = {'SHEET', 'DRAWINGS', 'CANNERY', 'TRAIL', 'RESIDENCES', 'OXFORD', 'CLAIRE', 'SCHEDULED', 'TOTAL', 'DOORS', 'WINDOWS', 'FLOOR'}
                kws = [w.upper() for w in re.findall(r"[A-Za-z]{5,}", q) if w.upper() not in stop and any(w.upper() in r['desc'] for r in rows)]
                fl = re.search(r'(\d)(?:st|nd|rd|th) floor', ql)
                sw = re.search(r"starts? with '([A-Z]+)'", q)
                sel = rows
                if 'all type marks' in ql:
                    why = 'all type marks'
                elif sw:
                    sel = [r for r in sel if r['desc'].startswith(sw.group(1))]; why = 'description starts with ' + sw.group(1)
                elif kws:
                    sel = [r for r in sel if all(k in r['desc'] for k in kws)]; why = 'description contains ' + ' + '.join(kws)
                else:
                    why = 'all type marks'
                if fl:
                    sel = [r for r in sel if re.search(fl.group(1) + r'(ST|ND|RD|TH) FLOOR', r['desc'])]; why += ', ' + fl.group(0)
            its = [dict(item(r), value=r['count']) for r in sel]
            tot = sum(r['count'] for r in sel)
            return dict(value=tot, unit='count', items=its, method=f'sum of the Count column where {why}',
                        steps=steps + [f"Kept type rows where {why}: {len(sel)}", f"Each row carries its own quantity → summed Count = {tot}"])
        qi = col_for(t, 'count', 'qty', 'quantity')
        if qi is not None and qi > 0:   # aggregated schedule: one row per type, quantity in a Count column
            mult = lambda r: 1
            if nwide:   # "every N-wide assembly consists of N units": weight each row by its N-WIDE
                mult = lambda r: int((re.search(r'(\d+)-WIDE', ' '.join(r['cells'])) or [0, 1])[1])
            its = [dict(item(r), value=(num(r['cells'][qi]) or 0) * mult(r)) for r in sel]
            tot = int(sum((num(r['cells'][qi]) or 0) * mult(r) for r in sel))
            extra = [f"Weighted each row's Count by its N-WIDE (units per assembly)"] if nwide else []
            return dict(value=tot, unit='count', items=its, method=f'sum of Count column where {why}' + (' × N-wide' if nwide else ''),
                        steps=steps + [f"Kept rows where {why}: {len(sel)}"] + extra + [f"Schedule is aggregated → summed its Count column = {tot}"])
        its = [item(r) for r in sel]
        return dict(value=len(sel), unit='count', items=its, method=f'count schedule rows where {why}', steps=steps + [f"Kept rows where {why}: {len(sel)}"])
    return dict(value=None, unit=None, items=[], method='not routed', steps=steps + ['No schedule operation matched'])


def view(path, rel):
    words, W, H, _ = sheet(path)
    return dict(kind='sheet', url=f'/api/sheet?path={quote(rel)}', w=W, h=H)
