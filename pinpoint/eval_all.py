"""One honest scoreboard: per source and per question type, dev split vs unseen drawings.

    python -m pinpoint.eval_all          -> data/eval_all.json   (served at /api/eval_all)

Inputs (produced by the eval scripts; nothing here re-answers questions):
  data/eval/<source>.json                 dev split = the preview set the rules were developed on (pinpoint.evaluate)
  <eval_acc>/robust.json                  unseen drawings from the FULL dataset (pinpoint.robust)
  <eval_acc>/cubicasa_rooms_<split>.json  CubiCasa room-label OCR (pinpoint.raster.eval_rooms): preview = dev,
                                          val300 = 300 other Stoa plans never looked at while writing the rules
Scoring is the official one: counts exact, area/length/volume within 2 %, short free text by engine.grade_text;
long narrative answers (ifc_bench) are reported as answered, not graded.
"""
import os, json, glob, collections, statistics, time
from . import engine

ACC = os.environ.get('PINPOINT_EVAL_OUT') or os.path.join(engine.ROOT, 'data/eval_acc')
OUT = os.path.join(engine.ROOT, 'data/eval_all.json')


def summarise(rows, src_key):
    by = collections.defaultdict(lambda: collections.defaultdict(lambda: dict(correct=0, graded=0, answered=0, total=0)))
    secs = collections.defaultdict(list)
    for r in rows:
        s = src_key(r)
        t = by[s][r.get('type') or 'none']
        t['total'] += 1
        t['answered'] += r.get('value') is not None
        if r.get('correct') is not None:
            t['graded'] += 1; t['correct'] += bool(r['correct'])
        if r.get('secs') is not None:
            secs[s].append(r['secs'])
    out = {}
    for s, types in by.items():
        tot = {k: sum(t[k] for t in types.values()) for k in ('correct', 'graded', 'answered', 'total')}
        tot['accuracy'] = round(100 * tot['correct'] / tot['graded'], 2) if tot['graded'] else None
        for t in types.values():
            t['accuracy'] = round(100 * t['correct'] / t['graded'], 2) if t['graded'] else None
        out[s] = dict(tot, by_type=dict(types), median_ms=round(1000 * statistics.median(secs[s]), 1) if secs[s] else None)
    return out


def main():
    dev = []
    for f in sorted(glob.glob(os.path.join(engine.ROOT, 'data/eval/*.json'))):
        dev += json.load(open(f))
    res = dict(generated=time.strftime('%Y-%m-%d %H:%M'), scoring='counts exact; area/length/volume within 2%; short text graded, narrative text answered-only',
               dev=dict(note='preview split (rules were developed on it)', sources=summarise(dev, lambda r: engine.source_of(r['path']))))
    rb = os.path.join(ACC, 'robust.json')
    if os.path.exists(rb):
        R = json.load(open(rb))
        res['unseen'] = dict(note='drawings from the full dataset that are not in the preview split (never used for development)',
                             crashes=sum(r.get('crash') is not None for r in R),
                             silent=sum(r.get('value') is None and not r.get('explained') for r in R),
                             sources=summarise(R, lambda r: r['source']))
    cc = {}
    for split in ('preview', 'val300'):
        f = os.path.join(ACC, f'cubicasa_rooms_{split}.json')
        if os.path.exists(f):
            d = json.load(open(f))
            for v in d['by_template'].values():
                v['accuracy'] = round(100 * v['correct'] / v['graded'], 1) if v['graded'] else None
            cc[split] = d
    if cc:
        res['cubicasa_room_labels'] = dict(note='Tesseract fin+eng room-label OCR (bedrooms, kitchens, bathrooms, WC, saunas, balconies, storeys); '
                                                'preview = dev, val300 = held-out Stoa plans', **cc)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    for part in ('dev', 'unseen'):
        if part in res:
            print(part, {s: f"{v['correct']}/{v['graded']}" for s, v in res[part]['sources'].items()})
    print('wrote', OUT)


if __name__ == '__main__':
    main()
