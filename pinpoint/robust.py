"""Full-dataset robustness + generalisation check.

    python -m pinpoint.robust [plans_per_source]

1. Generalisation: sample drawings whose questions are in the FULL dataset but which are NOT in the preview
   split we developed on; fetch only the files needed (fullset.py), answer every question, grade with the
   official rules (exact counts, 2 % for area/length/volume, free text via engine.grade_text).
2. Robustness: drawings from the sources that carry no questions (historic scans, wikimedia) get generic
   questions in several languages: each must return either an answer with evidence or an explicit reason.
   A crash or a silent None is a failure.
Writes data/eval_acc/robust.json (or $PINPOINT_EVAL_OUT/robust.json) and prints a per-source table.
"""
import os, sys, json, random, time, collections, traceback
from concurrent.futures import ThreadPoolExecutor
from . import engine, fullset

OUT = os.environ.get('PINPOINT_EVAL_OUT') or os.path.join(engine.ROOT, 'data/eval_acc')
GENERIC = ['How many doors are shown on this drawing?', 'Kuinka monta ikkunaa piirustuksessa on?',
           'Wie viele Räume sind auf diesem Plan?', 'What is the total floor area?']


def needed(rel):
    stem, ext = rel.rsplit('.', 1)
    src = engine.source_of(rel)
    if src == 'swiss_dwellings':
        return [stem + '.pdf', stem + '.dxf']
    if src == 'ifc_models' and ext == 'pdf':
        return [rel, stem + '.svg', engine.ifc_for(rel)]
    return [rel]


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    rnd = random.Random(11)
    prev = {json.loads(l)['path'] for l in open(os.path.join(engine.DATA, 'questions.jsonl'))}
    Q = [json.loads(l) for l in open(os.path.join(fullset.FULL, 'questions.jsonl'))]
    by = collections.defaultdict(list)
    for q in Q:
        by[q['path']].append(q)
    idx = fullset.index()
    plans = collections.defaultdict(list)
    for p in sorted(by):
        s = engine.source_of(p)
        if p in prev or s == 'cubicasa5k':       # cubicasa is measured separately (raster track / eval_rooms)
            continue
        if s == 'ifc_bench' and idx[fullset.PREFIX + p][2] > 80e6:
            continue
        plans[s].append(p)
    pick = []
    for s, ps in plans.items():
        rnd.shuffle(ps)
        pick += ps[:k]
    # question-less sources: a few files each
    extra = []
    for s in ('europeana', 'finna', 'habs', 'wikimedia'):
        fs = sorted(n[len(fullset.PREFIX):] for n in idx if n.startswith(f'{fullset.PREFIX}data/{s}/') and not n.endswith('.md'))
        rnd.shuffle(fs)
        extra += fs[:4]
    files = sorted({f for p in pick for f in needed(p)} | set(extra))
    t = time.time()
    with ThreadPoolExecutor(6) as ex:
        got = list(ex.map(fullset.fetch, files))
    print(f'fetched {sum(g is not None for g in got)}/{len(files)} files in {time.time() - t:.0f}s', file=sys.stderr)

    res = []
    def ask(path, q, gt=None):
        t0 = time.perf_counter()
        try:
            r = engine.ask(path, q)
            v, method, crash = r.get('value'), r.get('method'), None
            explained = v is not None or bool(r.get('steps'))
            ok = engine.grade(v, gt) if gt else None
        except Exception as e:
            v, method, crash, explained, ok = None, None, f'{type(e).__name__}: {e}', False, False
            traceback.print_exc()
        res.append(dict(path=path, source=engine.source_of(path), question=q, type=gt['type'] if gt else 'none',
                        truth=gt['answer'] if gt else None, value=v, correct=ok, method=method, crash=crash,
                        explained=explained, secs=round(time.perf_counter() - t0, 3)))
    for p in pick:
        for q in by[p]:
            ask(p, q['question'], q)
    for p in extra:
        for q in GENERIC:
            ask(p, q)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, 'robust.json'), 'w'), ensure_ascii=False, default=str)

    agg = collections.defaultdict(lambda: collections.Counter())
    for r in res:
        a = agg[r['source']]
        a['n'] += 1
        a['crash'] += r['crash'] is not None
        a['silent'] += r['value'] is None and not r['explained']
        a['answered'] += r['value'] is not None
        if r['correct'] is not None:
            a['graded'] += 1; a['correct'] += bool(r['correct'])
    print(f"{'source':16s} {'qs':>5s} {'crash':>5s} {'silent':>6s} {'answered':>8s}  accuracy (graded)")
    for s, a in sorted(agg.items()):
        acc = f"{a['correct']}/{a['graded']} = {100 * a['correct'] / a['graded']:.1f}%" if a['graded'] else 'n/a'
        print(f"{s:16s} {a['n']:5d} {a['crash']:5d} {a['silent']:6d} {a['answered']:8d}  {acc}")


if __name__ == '__main__':
    main()
