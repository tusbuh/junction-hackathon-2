"""DRAWING AUDIT: read the same fact twice, independently, and flag where the drawing disagrees with itself.

    GET /api/audit?path=...        -> findings + 'what a site engineer should double-check' for one drawing
    GET /api/audit/showcase        -> the real discrepancies we found in the preview dataset, each with its evidence

Checks (every number below is measured from the files at request time, nothing is typed in by hand):
- Swiss CAD plans: printed m² room label vs the area of the ROOM_OUTLINE polygon it labels.
- US sheets (door schedule vs plan): door marks listed in the door schedule vs door tags drawn on the floor-plan pages;
  door swings (arc + leaf) drawn on the plan with no door tag near them; for a schedule-only sheet, the same marks
  against the door tags on the project's other issued sheets (revision check).
- IFC models: elements with identical geometry (double-counted in any quantity take-off), near-complete overlaps,
  IfcSpace floor quantity (Qto) vs the footprint of the space's own 3D body. Pre-computed by pinpoint.audit
  (static/findings.json) because it meshes every element.
"""
import os, re, math, json, glob, functools, collections
import numpy as np
import pymupdf
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from . import engine
from .engine import DATA, ROOT, abspath, source_of

router = APIRouter()
MARK = re.compile(r'^\d{3}\.[A-Z]\d?$')          # door mark convention used on these sheets: <room>.<letter>[n], e.g. 118.C, 100.A1
FINDINGS = os.path.join(ROOT, 'static', 'findings.json')


def _url(rel, page=0):
    from urllib.parse import quote
    return f'/api/sheet?path={quote(rel)}' + (f'&page={page}' if page else '')


# ------------------------------------------------------------------------------------------ PDF door schedules vs plans
def _swings(p):
    """Door swings on a vector plan: a ~90° arc (drawn as a chain of short segments) centred on a hinge point, with the
    door leaf (a straight line about one radius long) starting at that hinge."""
    M = p.rotation_matrix
    segs, leaves = [], []
    for g in p.get_drawings():
        its = g['items']
        for it in its:
            if it[0] == 'l':
                a, b = it[1] * M, it[2] * M
                L = math.dist(a, b)
                leaves.append((a, b, L))
                if 0.3 < L < 6 and all(x[0] == 'l' for x in its):
                    segs.append(((round(a.x, 1), round(a.y, 1)), (round(b.x, 1), round(b.y, 1))))
            elif it[0] == 're':
                r_ = it[1] * M; r_.normalize()
                if min(r_.width, r_.height) < 4:
                    leaves.append((pymupdf.Point(r_.x0, r_.y0), pymupdf.Point(r_.x1, r_.y1), max(r_.width, r_.height)))
    par = {}

    def f(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a, b in segs:
        par[f(a)] = f(b)
    comp = collections.defaultdict(list)
    for a, b in segs:
        comp[f(a)].append((a, b))
    out = []
    for c in comp.values():
        if not 6 <= len(c) <= 60:
            continue
        P = np.array([q for s in c for q in s])
        sol, *_ = np.linalg.lstsq(np.c_[2 * P, np.ones(len(P))], (P ** 2).sum(1), rcond=None)
        cx, cy = sol[:2]
        r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0))
        if not 15 < r < 50 or np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r).max() > 0.6:
            continue
        ang = np.sort(np.degrees(np.arctan2(P[:, 1] - cy, P[:, 0] - cx)))
        sweep = 360 - np.diff(np.r_[ang, ang[0] + 360]).max()
        if not 75 < sweep < 105 or min(np.ptp(P[:, 0]), np.ptp(P[:, 1])) < 0.6 * r:
            continue
        if any(abs(L - r) < 0.25 * r and min(math.dist(a, (cx, cy)), math.dist(b, (cx, cy))) < 3 for a, b, L in leaves):
            out.append(dict(r=r, bbox=[float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())]))
    return out


@functools.lru_cache(maxsize=64)
def _pdf_pages(full):
    """Per page: door tags (mark -> bbox in displayed coords), whether the page is a door schedule, its sheet title."""
    doc = pymupdf.open(full)
    pages = []
    for i, p in enumerate(doc):
        M = p.rotation_matrix
        words = [(pymupdf.Rect(w[:4]) * M, w[4]) for w in p.get_text('words')]
        tags = [(t, r) for r, t in words if MARK.match(t)]
        # a schedule lists its marks in one column (same x) or one row (same y); a plan scatters them
        col = max(collections.Counter(round((r.x0 + r.x1) / 4) for _, r in tags).values(), default=0)
        row = max(collections.Counter(round((r.y0 + r.y1) / 4) for _, r in tags).values(), default=0)
        is_sched = len(tags) >= 8 and max(col, row) >= 0.6 * len(tags) and any(re.search(r'door', t, re.I) for _, t in words)
        # sheet number = the biggest 'A-101'-style text on the page (title block), not the section callouts
        big = [(sp['size'], sp['text'].strip()) for b in p.get_text('dict')['blocks'] for l in b.get('lines', []) for sp in l['spans']
               if re.match(r'^[A-Z]{1,2}-?\d{3}(\.[A-Z])?$', sp['text'].strip())]
        sheet = max(big)[1] if big else None
        pages.append(dict(page=i, w=p.rect.width, h=p.rect.height, sched=is_sched, sheet=sheet,
                          tags={t: [r.x0, r.y0, r.x1, r.y1] for t, r in tags}))
    return pages


def _plan_swings(full, page):
    return _swings(pymupdf.open(full)[page])


def _project_root(rel):
    parts = rel.split('/')
    return '/'.join(parts[:3]) if len(parts) > 3 else os.path.dirname(rel)


def audit_pdf(rel):
    full = abspath(rel)
    fname = os.path.basename(rel)
    pages = _pdf_pages(full)
    sched = [p for p in pages if p['sched']]
    plans = [p for p in pages if not p['sched'] and len(p['tags']) >= 3]
    findings, checks, dbl = [], [], []
    if sched and plans:
        listed = {}
        for p in sched:
            for t, b in p['tags'].items():
                listed.setdefault(t, (p['page'], b))
        drawn = {}
        for p in plans:
            for t, b in p['tags'].items():
                drawn.setdefault(t, (p['page'], b))
        miss = sorted(set(listed) - set(drawn))
        extra = sorted(set(drawn) - set(listed))
        ok = not miss and not extra
        checks.append(dict(what='door schedule vs door tags on the plan', printed=len(listed), computed=len(drawn), unit='doors', ok=ok,
                           note=f'{len(listed)} marks in the schedule (p.{sched[0]["page"] + 1}), {len(drawn)} distinct tags on plan pages '
                                + ', '.join(f'p.{p["page"] + 1}' for p in plans)))
        for t in miss:
            pg, b = listed[t]
            findings.append(dict(kind='schedule_vs_plan', severity='amber',
                                 title=f'Door {t} is in the door schedule but has no door tag on any plan page',
                                 detail=f'Schedule row {t} (p.{pg + 1}); searched every plan page of {fname} for the tag.',
                                 items=[dict(kind='row', label=f'schedule row {t}', bbox=b, page=pg,
                                             cite=f'{fname} p.{pg + 1} · door schedule, mark {t}')], page=pg))
            dbl.append(f'Door {t}: scheduled but not tagged on plan. Locate it on site or raise an RFI before the door/hardware order goes out.')
        for t in extra:
            pg, b = drawn[t]
            findings.append(dict(kind='schedule_vs_plan', severity='amber', title=f'Door tag {t} on the plan is missing from the door schedule',
                                 detail='No schedule row: no size, frame, fire rating or hardware set for this door.',
                                 items=[dict(kind='tag', label=f'door tag {t}', bbox=b, page=pg, cite=f'{fname} p.{pg + 1} · door tag {t}')], page=pg))
            dbl.append(f'Door {t}: tagged on plan, not in the schedule. Ask for the schedule row (size, frame, rating, hardware).')
        # door leaves drawn with no tag near them
        for p in plans:
            sw = _plan_swings(full, p['page'])
            tagc = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, t) for t, b in p['tags'].items()]
            lone = []
            for s in sw:
                b = s['bbox']; c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
                d, near = min((math.dist(c, t[:2]), t[2]) for t in tagc)
                if d > 2.2 * s['r']:
                    lone.append((s, d, near))
            checks.append(dict(what=f'door swings with a door tag (p.{p["page"] + 1}{" · " + p["sheet"] if p["sheet"] else ""})',
                               printed=len(sw), computed=len(sw) - len(lone), unit='doors', ok=not lone,
                               note=f'{len(sw)} door swings recognised (arc + leaf); a tag must sit within 2 leaf widths'))
            for s, d, near in lone:
                leaf_ft = s['r'] * 8 / 72      # 1/8" = 1'-0": 1 pt = 8/72 ft
                b = s['bbox']
                findings.append(dict(kind='untagged_door', severity='amber',
                                     title=f'Door leaf drawn on {p["sheet"] or "p." + str(p["page"] + 1)} with no door tag',
                                     detail=f'Swing radius {s["r"]:.1f} pt (≈ {leaf_ft:.1f} ft leaf if the sheet is at 1/8" = 1\'-0"); nearest tag {near} is {d:.0f} pt away.'
                                            + (f' Unplaced schedule marks: {", ".join(miss)}.' if miss else ''),
                                     items=[dict(kind='door', label='untagged door leaf', bbox=b, page=p['page'],
                                                 cite=f'{fname} p.{p["page"] + 1} at ({(b[0] + b[2]) / 2:.0f}, {(b[1] + b[3]) / 2:.0f}) pt · door swing arc + leaf')],
                                     page=p['page']))
                dbl.append(f'Untagged door leaf on {p["sheet"] or "p." + str(p["page"] + 1)} near ({(b[0] + b[2]) / 2:.0f}, {(b[1] + b[3]) / 2:.0f}) pt'
                           + (f': probably {" or ".join(miss)}. Confirm the mark' if miss else ': confirm its mark') + ' before ordering the frame.')
    elif sched and not plans:
        # schedule-only sheet: compare with the door tags on the project's other issued plan sheets (revision check)
        listed = {}
        for p in sched:
            for t, b in p['tags'].items():
                listed.setdefault(t, (p['page'], b))
        for other in sorted(glob.glob(os.path.join(abspath(_project_root(rel)), '**', '*.pdf'), recursive=True)):
            if os.path.samefile(other, full) or os.path.getsize(other) > 40e6:
                continue
            try:
                op = _pdf_pages(other)
            except Exception:
                continue
            oplans = [p for p in op if not p['sched'] and len(p['tags']) >= 3]
            if not oplans:
                continue
            drawn = set().union(*[p['tags'] for p in oplans])
            orel = os.path.relpath(other, DATA)
            gone, new = sorted(drawn - set(listed)), sorted(set(listed) - drawn)
            dm = re.search(r'(20\d{6})', orel)
            when = f'{dm.group(1)[:4]}-{dm.group(1)[4:6]}-{dm.group(1)[6:]}' if dm else 'another'
            checks.append(dict(what=f'this schedule vs door tags on the {when} plan issue', printed=len(listed), computed=len(drawn), unit='doors',
                               ok=not gone and not new, note=os.path.basename(orel)))
            if gone or new:
                findings.append(dict(kind='revision', severity='amber',
                                     title=f'Door schedule changed since the {when} plans: {len(gone)} door(s) dropped, {len(new)} added',
                                     detail=(f'Tagged on the {when} plans but not in this schedule: {", ".join(gone)}. ' if gone else '')
                                            + (f'In this schedule but not on those plans: {", ".join(new)}.' if new else ''),
                                     items=[dict(kind='row', label=f'schedule row {t} (new since {when})', bbox=listed[t][1], page=listed[t][0],
                                                 cite=f'{fname} p.{listed[t][0] + 1} · door schedule, mark {t}') for t in new], page=0, other=orel))
                if gone:
                    dbl.append(f'Doors {", ".join(gone)} were on the {when} plans and are gone from this schedule: make sure the door supplier\'s order follows this revision.')
                if new:
                    dbl.append(f'Doors {", ".join(new)} are new since the {when} plans: check they appear on the current floor plans with frames and openings.')
    return findings, checks, dbl


# ------------------------------------------------------------------------------------------ Swiss CAD
def audit_swiss(rel):
    stem = os.path.splitext(os.path.basename(rel))[0]
    plan = engine.swiss_plan(stem)
    A, *_ = engine.swiss_fit(stem)
    rooms = [r for r in plan.rooms if r.get('printed') is not None and r.get('area')]
    bad = [r for r in rooms if abs(r['printed'] - r['area']) > max(0.02 * r['printed'], 0.06)]
    checks = [dict(what='printed m² room labels vs ROOM_OUTLINE polygon areas', printed=len(rooms), computed=len(rooms) - len(bad), unit='rooms agree',
                   ok=not bad, note=f'tolerance ±2 % (min 0.06 m²) · {len(plan.rooms)} room polygons on the DXF')]
    findings, dbl = [], []
    for r in bad:
        it = engine._map_items([dict(kind='room', label=f"{r['num']} {r['name'] or ''}", bbox=r['bbox'], poly=r.get('poly'))], A)[0]
        it['cite'] = f"{stem}.pdf p.1 · DXF ROOM_OUTLINE + ROOM_TEXT {r['num']}"
        findings.append(dict(kind='label_vs_geometry', severity='amber', title=f"Room {r['num']} {r['name'] or ''}: printed {r['printed']} m², outline {r['area']:.2f} m²",
                             printed=r['printed'], computed=round(r['area'], 2), unit='m²', items=[it], page=0))
        dbl.append(f"Room {r['num']}: re-measure on site; label says {r['printed']} m², the drawn outline is {r['area']:.2f} m².")
    if not bad:
        dbl.append(f'All {len(rooms)} printed room areas match their drawn outlines: no re-measure needed for area-based items (screed, flooring).')
    unl = [r for r in plan.rooms if not r.get('name')]
    if unl:
        dbl.append(f'{len(unl)} room polygon(s) carry no room name: confirm whether they are shafts, loggias or rooms before pricing finishes.')
    return findings, checks, dbl


# ------------------------------------------------------------------------------------------ IFC
def _ifc_findings():
    try:
        return json.load(open(FINDINGS))
    except Exception:
        return dict(findings=[], checked={})


def audit_ifc(rel):
    ifc = rel if rel.endswith('.ifc') else re.sub(r'_plan-.*$', '', rel[:-4]) + '.ifc'
    F = _ifc_findings()
    mine = [f for f in F['findings'] if f.get('path') == ifc]
    findings, dbl = [], []
    for f in mine:
        f = dict(f)
        f['items'] = [dict(gid=g, cls=f.get('cls'), label=f"{f.get('cls')} {g}" + (f" · {s}" if s else ''),
                           cite=f"{os.path.basename(ifc)} · {f.get('cls')} GlobalId {g}") for g, s in zip(f.get('gids') or [], f.get('storeys') or [None] * 9)]
        f['model'] = ifc
        if re.search(r'\bSTB\b', f.get('title', '')):    # German model: say what it is in site terms
            f['detail'] = (f.get('detail') or '') + ' STB = Stahlbeton (reinforced concrete): the copy doubles the concrete, formwork and rebar take-off for this element.'
        findings.append(f)
        if f['kind'] == 'duplicate':
            dbl.append(f"{f['title']}: delete or confirm the copy (GlobalIds {', '.join(f['gids'])}); it is counted {len(f['gids'])}× in every quantity take-off.")
        elif f['kind'] == 'overlap':
            dbl.append(f"{f['title']}: check for a left-behind copy before the clash run.")
        elif f['kind'] == 'space_body':
            dbl.append(f"{f['title']}: confirm which figure the cost plan uses.")
    checks = [dict(what='no two elements of the same class occupy the same space', printed=None, computed=None, unit=None,
                   ok=not any(f['kind'] in ('duplicate', 'overlap') for f in mine), note='geometry fingerprint: world bounding box to 2 cm + volume'),
              dict(what='IfcSpace Qto floor area vs the footprint of its 3D body', printed=None, computed=None, unit=None,
                   ok=not any(f['kind'] == 'space_body' for f in mine), note='flagged when they differ by > 10 % and > 0.5 m²')]
    if not mine:
        dbl.append('No duplicate or overlapping elements, and every space quantity matches its 3D body.')
    return findings, checks, dbl, ifc


# ------------------------------------------------------------------------------------------ dispatcher + API
@functools.lru_cache(maxsize=128)
def audit(rel):
    src = source_of(rel)
    fname = os.path.basename(rel)
    out = dict(path=rel, file=fname, source=src, view=None)
    try:
        if src == 'swiss_dwellings':
            f, c, d = audit_swiss(rel)
            out['view'] = dict(kind='sheet', url=_url(rel), w=engine.swiss_fit(os.path.splitext(fname)[0])[3][0], h=engine.swiss_fit(os.path.splitext(fname)[0])[3][1])
        elif src in ('ifc_models', 'ifc_bench') or rel.endswith('.ifc'):
            f, c, d, ifc = audit_ifc(rel)
            out['model'] = ifc
        elif rel.lower().endswith('.pdf'):
            f, c, d = audit_pdf(rel)
            pg = _pdf_pages(abspath(rel))
            out['pages'] = [dict(page=p['page'], w=p['w'], h=p['h'], url=_url(rel, p['page']), sheet=p['sheet'], schedule=p['sched']) for p in pg]
            if not c:
                d.append('No door schedule and door tags found on this sheet to cross-check.')
        else:
            f, c, d = [], [], ['Raster scan: printed labels are read by OCR, so re-measure any area you will price from.']
    except Exception as ex:
        f, c, d = [], [], [f'Audit could not run on this drawing ({type(ex).__name__}); nothing was checked.']
    out.update(findings=f, checks=c, doublecheck=d)
    from .cite import licence
    out['licence'] = licence(DATA, out.get('model') or rel)
    return out


SHOWCASE = [  # files we audited and found real discrepancies in; the findings themselves are recomputed on request
    'data/opening_design/Sports_Complex/Transfer/_Archive/20150720 - Door Schedule to Door Consultant/20150720 - XSC - floor plan and door schedule.pdf',
    'data/opening_design/Sports_Complex/Sheets - Current Set/A-801 - Door and Finish Schedules & Wall Types.pdf',
    'data/ifc_bench/fantasy_office_building_3_arc.ifc',
    'data/ifc_models/bsc-molio_molio-with-uris.ifc',
]


@router.get('/api/audit')
def api_audit(path: str = Query(...)):
    return JSONResponse(audit(path))


@router.get('/api/audit/showcase')
def api_showcase():
    F = _ifc_findings()
    return JSONResponse(dict(audits=[audit(p) for p in SHOWCASE if os.path.exists(abspath(p))], checked=F.get('checked'), ifc_generated=F.get('generated')))
