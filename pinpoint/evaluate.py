"""Score PINPOINT on the dataset questions.  .venv/bin/python -m pinpoint.evaluate [source ...]
Writes data/eval/<source>.json (per-question results) and prints accuracy per source and question template."""
import sys, os, re, json, time, collections
from . import engine

OUT = os.environ.get('PINPOINT_EVAL_OUT', os.path.join(engine.ROOT, 'data/eval'))
os.makedirs(OUT, exist_ok=True)


def template(q):
    q = re.sub(r"['„«“‘][^'“»”’]*['“»”’]", 'X', q)
    q = re.sub(r'\d+([.,]\d+)?', 'N', q)
    return q[:70]


def run(sources):
    qs = [q for q in engine.questions() if engine.source_of(q['path']) in sources]
    res = []
    t = time.time()
    for i, q in enumerate(qs):
        t0 = time.perf_counter()
        try:
            r = engine.ask(q['path'], q['question'])
            v, ok, method, cost = r['value'], r.get('correct'), r['method'], r['cost']['total_eur']
        except Exception as e:
            v, ok, method, cost = None, False, f'error {type(e).__name__}: {e}', 0
        res.append(dict(path=q['path'], question=q['question'], type=q['type'], truth=q['answer'], value=v,
                        correct=ok, method=method, secs=round(time.perf_counter() - t0, 4), eur=cost))
        if i % 500 == 0:
            print(f'  {i}/{len(qs)} {time.time() - t:.0f}s', file=sys.stderr)
    return res


def report(res):
    by = collections.defaultdict(lambda: [0, 0])
    tp = collections.defaultdict(lambda: [0, 0])
    for r in res:
        if r['correct'] is None: continue
        s = engine.source_of(r['path'])
        by[s][0] += bool(r['correct']); by[s][1] += 1
        tp[(s, template(r['question']))][0] += bool(r['correct']); tp[(s, template(r['question']))][1] += 1
    for s, (a, b) in by.items():
        print(f'{s:18s} {a}/{b} = {100 * a / b:.1f}%')
    print('--- worst templates')
    for (s, k), (a, b) in sorted(tp.items(), key=lambda x: x[1][0] - x[1][1])[:25]:
        if a < b: print(f'{a:4d}/{b:<4d} {s[:10]} {k}')


if __name__ == '__main__':
    srcs = sys.argv[1:] or ['swiss_dwellings', 'ifc_models', 'cubicasa5k', 'opening_design', 'ifc_bench']
    allres = []
    for s in srcs:
        res = run([s])
        json.dump(res, open(os.path.join(OUT, f'{s}.json'), 'w'), ensure_ascii=False)
        allres += res
    report(allres)
