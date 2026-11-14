"""Failure breakdown of a CubiCasa eval file, by question type and by room / object template.

    .venv/bin/python -m pinpoint.raster.breakdown [data/eval/cubicasa5k.json] [other.json]

Every number is counted from the per-question eval rows; nothing is estimated. With two files it
prints the per-template delta (e.g. baseline vs a candidate before merging).
"""
import json, sys, collections
from .detector import template_key


def table(path):
    rows = json.load(open(path))
    t = collections.defaultdict(lambda: dict(ok=0, n=0, over=0, under=0, none=0))
    for r in rows:
        for k in (f"type:{r['type']}", template_key(r['question']) or 'other',
                  'lang:' + ('FI' if r['question'].startswith('Kuinka') else 'EN'), 'ALL'):
            c = t[k]; c['n'] += 1
            if r['correct']: c['ok'] += 1
            elif r['value'] is None: c['none'] += 1
            elif isinstance(r['value'], (int, float)) and isinstance(r['truth'], (int, float)):
                c['over' if r['value'] > r['truth'] else 'under'] += 1
    return t


def main():
    files = sys.argv[1:] or ['data/eval/cubicasa5k.json']
    ts = [table(f) for f in files]
    keys = sorted(ts[0], key=lambda k: -(ts[0][k]['n'] - ts[0][k]['ok']) if k != 'ALL' else 1)
    print(f"{'bucket':20s} {'misses':>6s} {'exact':>12s}  over under none" + ('   delta' if len(ts) > 1 else ''))
    for k in keys:
        c = ts[0][k]
        line = f"{k:20s} {c['n'] - c['ok']:6d} {c['ok']:5d}/{c['n']:<5d} {100 * c['ok'] / c['n']:5.1f}%  {c['over']:4d} {c['under']:5d} {c['none']:4d}"
        if len(ts) > 1:
            d = ts[1].get(k, dict(ok=0, n=0))
            line += f"   {d['ok'] - c['ok']:+d}  -> {d['ok']}/{d['n']}"
        print(line)


if __name__ == '__main__':
    main()
