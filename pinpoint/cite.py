"""Citations: turn any engine result into a verifiable receipt.

Every answer gets r['receipt'] = {source, confidence, checks, excluded} and every evidence item gets
it['cite'], a human-readable pointer to exactly where on the drawing / in the model it came from.
Cross-checks compare two independent readings of the same fact (a printed label vs the geometry it labels,
a model quantity vs the 3D shape, a table total vs its rows) and turn amber when they disagree."""
import os, re, functools

LAYER = {'room': 'ROOM_OUTLINE polygon + ROOM_TEXT label', 'apartment': 'UNIT_OUTLINE + Whg./App. label', 'door': 'DOOR leaf',
         'window': 'WINDOW frame', 'basin': 'FIXTURE bowl + drain', 'WC': 'FIXTURE bowl', 'bathtub': 'FIXTURE tub outline',
         'shower': 'FIXTURE floor drain', 'excluded': 'ROOM_OUTLINE polygon'}
KIND = {'swiss_dwellings': 'CAD floor plan (DXF geometry projected on the PDF sheet)', 'ifc_models': 'BIM model (IFC)',
        'ifc_bench': 'BIM model (IFC)', 'cubicasa5k': 'scanned raster floor plan', 'opening_design': 'vector PDF sheet (schedules)'}
# base trust in the reading itself, before any cross-check: exact vector / model data > text tables > a detector on pixels
BASE = {'swiss_dwellings': 0.97, 'ifc_models': 0.95, 'ifc_bench': 0.85, 'opening_design': 0.85, 'cubicasa5k': 0.75}


@functools.lru_cache(maxsize=64)
def licence(data_root, path):
    """Credit line for a dataset file, from the LICENSE.md next to it (per-file table row, else the 'All files' line)."""
    d = os.path.dirname(os.path.join(data_root, path))
    while d.startswith(data_root) and not os.path.exists(os.path.join(d, 'LICENSE.md')):
        d = os.path.dirname(d)
    f = os.path.join(d, 'LICENSE.md')
    if not os.path.exists(f):
        return None
    txt = open(f, encoding='utf-8', errors='replace').read()
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r'_plan-.*$', '', stem)
    for line in txt.splitlines():
        if line.startswith('|') and stem in line:
            cells = [c.strip() for c in line.strip('|').split('|')]
            return ' · '.join(c for c in cells[1:] if c)[:600]
    m = re.search(r'^All files: (.+)$', txt, re.M)
    return m.group(1)[:600] if m else None


def _fmt(v, unit):
    if isinstance(v, float):
        v = f'{v:.2f}'
    return f'{v} {unit}' if unit and unit not in ('count', 'text') else str(v)


def cite_item(it, src, fname, view):
    """Where on the drawing this item is."""
    if it.get('gid'):
        s = f"{fname} · {it.get('cls', 'IfcProduct')} GlobalId {it['gid']}"
        return s + (' · also on the 2D plan' if (view or {}).get('sheet') else '')
    b = it.get('bbox')
    if not b:
        return fname
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    if src == 'swiss_dwellings':
        return f"{fname} p.1 at ({cx:.0f}, {cy:.0f}) pt · DXF {LAYER.get(it.get('kind'), 'entity')}"
    if src == 'cubicasa5k':
        return f"{fname} at pixel ({cx:.0f}, {cy:.0f}), box {b[2] - b[0]:.0f}×{b[3] - b[1]:.0f} px"
    if it.get('kind') == 'row':
        return f"{fname} p.1 · schedule row at y={cy:.0f} pt (x {b[0]:.0f}–{b[2]:.0f})"
    return f"{fname} p.1 at ({cx:.0f}, {cy:.0f})"


def answer_checks(r, src):
    """Answer-level cross-checks built from the item-level ones."""
    out = []
    items = r.get('items') or []
    rc = [i['check'] for i in items if i.get('check') and isinstance(i['check'].get('printed'), (int, float))
          and isinstance(i['check'].get('computed'), (int, float))]
    if rc and r.get('unit') == 'm²' and len(rc) > 1:
        p, c = sum(x['printed'] for x in rc), sum(x['computed'] for x in rc)
        what = 'Σ model quantities vs Σ 3D geometry' if rc[0].get('what') else 'Σ printed m² labels vs Σ computed polygons'
        out.append(dict(what=what, printed=round(p, 2), computed=round(c, 2), unit='m²', ok=abs(p - c) <= max(0.02 * p, 0.1),
                        note=f'{len(rc)} of {len(items)} items carry a second reading'))
    bad = [i for i in items if i.get('check') and not i['check'].get('ok') and i['check'].get('what') != 'low confidence']
    if rc and r.get('unit') != 'm²' or (rc and len(rc) == 1):
        x = rc[0]
        if len(rc) == 1:
            out.append(dict(what=x.get('what') or 'printed m² label vs computed polygon', printed=x['printed'], computed=x['computed'],
                            unit='m²', ok=x['ok'], note=None))
    out += list(r.get('xchecks') or [])     # engine-provided answer-level checks
    if bad and not any(c.get('ok') is False for c in out):
        out.append(dict(what='item cross-checks', printed=None, computed=None, unit=None, ok=False,
                        note=f'{len(bad)} item(s) disagree: ' + ', '.join(str(i.get('label')) for i in bad[:5])))
    return out


def confidence(r, src, checks):
    why = []
    if r.get('value') is None:
        return dict(level='low', colour='red', score=0.0, why=[r.get('method') or 'no answer'])
    s = BASE.get(src, 0.7)
    why.append({'swiss_dwellings': 'exact CAD geometry, no pixels involved', 'ifc_models': 'read straight from the BIM model',
                'ifc_bench': 'assembled from BIM model facts', 'opening_design': 'parsed from the PDF text layer',
                'cubicasa5k': 'symbol detector on a scanned image'}.get(src, 'source read'))
    router = r.get('router', 'rules')
    if router == 'lexicon':
        s *= 0.97; why.append('question mapped by the multilingual lexicon')
    elif router not in ('rules', None):
        s *= 0.9; why.append('question rewritten by a small LLM (it never saw the drawing)')
    ok = [c for c in checks if c.get('ok')]
    bad = [c for c in checks if c.get('ok') is False]
    if bad:
        s = min(s, 0.6); why.append(f'{len(bad)} cross-check(s) disagree: verify the amber items')
    elif ok:
        s = min(1.0, s + 0.02); why.append(f'{len(ok)} independent cross-check(s) agree')
    low = [i for i in r.get('items') or [] if (i.get('check') or {}).get('what') == 'low confidence']
    if low:
        s = min(s, 0.65); why.append(f'{len(low)} detection(s) below 0.5 confidence')
    if any('borderline' in str(x) for x in r.get('steps') or []):
        s = min(s, 0.7); why.append('borderline detections were left out of the count')
    if src == 'cubicasa5k' and r.get('items'):
        confs = [float(m.group(1)) for i in r['items'] for m in [re.search(r'· ([01]\.\d+)$', str(i.get('label')))] if m]
        if confs:
            mean = sum(confs) / len(confs)
            s = min(s, 0.55 + 0.45 * mean); why.append(f'mean detector confidence {mean:.2f}')
    if r.get('unit') == 'text' and src != 'ifc_bench':
        s *= 0.95
    level, colour = ('high', 'green') if s >= 0.85 else (('check', 'amber') if s >= 0.55 else ('low', 'red'))
    return dict(level=level, colour=colour, score=round(s, 2), why=why)


def tolerance(r, gt=None):
    """The official grading rule for this answer type and, when the dataset has a reference answer, how far we are from it."""
    unit, v = r.get('unit'), r.get('value')
    typ = (gt or {}).get('type') or {'count': 'count', 'm²': 'area', 'm³': 'volume', 'm': 'length', 'text': 'text'}.get(unit)
    rule = {'count': 'count: must be exact', 'area': 'area: within ±2 %', 'length': 'length: within ±2 %',
            'volume': 'volume: within ±2 %', 'text': 'free text: key terms and every code/number must match'}.get(typ, 'not auto-graded')
    out = dict(type=typ, rule=rule)
    if gt is None:
        return out
    a = gt.get('answer')
    out['reference'] = a
    out['ok'] = r.get('correct')
    if typ in ('area', 'length', 'volume') and isinstance(v, (int, float)):
        try:
            a = float(a); dev = abs(v - a) / abs(a) * 100 if a else 0.0
            u = unit if unit not in (None, 'count', 'text') else ''
            out.update(deviation_pct=round(dev, 3),
                       text=f"{v:.2f} vs {a:.2f} {u} reference, {'within' if dev <= 2 else 'outside'} tolerance (off by {dev:.2f} %)".replace('  ', ' '))
        except Exception:
            pass
    elif typ == 'count' and v is not None:
        out['text'] = f"{v} vs {a} reference: {'exact match' if v == a else f'off by {v - a:+}' if isinstance(a, (int, float)) and isinstance(v, (int, float)) else 'different'}"
    elif typ == 'text':
        out['text'] = {True: 'matches the reference answer', False: 'does not match the reference answer', None: 'narrative answer: reference shown, not auto-graded'}[r.get('correct')]
    return out


def finalize(r, path, data_root):
    src = path.split('/')[1] if path.startswith('data/') else path.split('/')[0]
    fname = os.path.basename(r.get('model') or path)
    view = r.get('view')
    for it in r.get('items') or []:
        it['cite'] = cite_item(it, src, fname, view)
    for it in r.get('excluded') or []:
        it['cite'] = cite_item(it, src, fname, view)
    checks = answer_checks(r, src)
    r['receipt'] = dict(
        source=dict(file=fname, path=path, kind=KIND.get(src, src), inputs=r.get('inputs'),
                    licence=licence(data_root, r.get('model') or path)),
        confidence=confidence(r, src, checks),
        checks=checks,
        excluded=r.get('excluded') or [],
        tolerance=tolerance(r),
    )
    return r
