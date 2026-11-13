"""Batch mode for the full benchmark:  .venv/bin/python -m pinpoint.answer questions.jsonl > answers.jsonl
Each output row = input row + {"pred", "unit_pred", "method", "router", "evidence" (ids/boxes), "eur", "secs"}.
Set PINPOINT_DATA to the dataset root (folder containing data/ and questions.jsonl)."""
import sys, json, time
from . import engine


def main(path):
    n = ok = graded = 0
    eur = 0.0
    t = time.time()
    for line in open(path):
        q = json.loads(line)
        try:
            r = engine.ask(q['path'], q['question'])
        except Exception as e:
            r = dict(value=None, unit=None, items=[], method=f'error: {e}', cost=dict(total_eur=0, seconds=0))
        ev = [dict(n=i.get('n'), label=i.get('label'), gid=i.get('gid'), bbox=i.get('bbox')) for i in r['items']][:500]
        out = dict(q, pred=r['value'], unit_pred=r.get('unit'), method=r['method'], router=r.get('router'), evidence=ev,
                   eur=r['cost']['total_eur'], secs=r['cost']['seconds'])
        print(json.dumps(out, ensure_ascii=False))
        n += 1; eur += r['cost']['total_eur']
        if r.get('correct') is not None:
            graded += 1; ok += bool(r['correct'])
    print(f'{n} questions, {graded} auto-graded, {ok} correct ({100 * ok / max(graded, 1):.1f}%), '
          f'total €{eur:.6f}, {time.time() - t:.0f}s', file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1])
