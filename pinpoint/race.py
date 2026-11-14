"""Cost race: PINPOINT vs a frontier VLM on the same eval questions.

PINPOINT numbers are read only from the eval files (data/eval/*.json: measured CPU seconds and euros per
question, auto-graded correctness). The VLM side is an *estimate* (engine.vlm_baseline: image + prompt tokens
at list price); we never ran a VLM on these questions, so its accuracy and latency are reported as not measured.
"""
import glob, json, os, statistics, zlib
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from . import engine
from .engine import ROOT

router = APIRouter()

PRICE_SOURCES = [
    dict(what='list price, Sonnet-class frontier VLM: $3 / Mtok input, $15 / Mtok output (≈ €2.80 / €14.00)',
         url='https://www.anthropic.com/pricing'),
    dict(what='image tokens ≈ width × height / 750, i.e. ~1.6k tokens per 1.15 MP tile',
         url='https://docs.anthropic.com/en/docs/build-with-claude/vision'),
]


@router.get('/api/race')
def race():
    vlm_q = engine.vlm_baseline(None)
    img_tok = max(1, 4e6 / 1.15e6) * 1600
    out, sample = [], []
    for f in sorted(glob.glob(os.path.join(ROOT, 'data/eval/*.json'))):
        res = json.load(open(f))
        if not res:
            continue
        secs = [r['secs'] for r in res]
        g = [r for r in res if r['correct'] is not None]
        sample += [r['question'] for r in res[::max(1, len(res) // 40)]]
        out.append(dict(source=os.path.basename(f)[:-5], n=len(res), graded=len(g), correct=sum(bool(r['correct']) for r in g),
                        eur=sum(r['eur'] or 0 for r in res), secs=sum(secs),
                        median_ms=1000 * statistics.median(secs), p95_ms=1000 * sorted(secs)[int(0.95 * (len(secs) - 1))],
                        vlm_eur=vlm_q * len(res)))
    out.sort(key=lambda x: -x['n'])
    tot = {k: sum(x[k] for x in out) for k in ('n', 'graded', 'correct', 'eur', 'secs', 'vlm_eur')}
    sample.sort(key=lambda q: zlib.crc32(q.encode()))   # stable shuffle: mix sources in the ticker
    return JSONResponse(dict(sources=out, total=tot, file='data/eval/*.json', sample=sample,
                             vlm=dict(eur_per_q=vlm_q, img_tokens=round(img_tok), prompt_tokens=300, answer_tokens=400, px=4e6,
                                      eur_in=engine.VLM_EUR_PER_MTOK_IN, eur_out=engine.VLM_EUR_PER_MTOK_OUT,
                                      sources=PRICE_SOURCES, accuracy='not measured', latency='not measured'),
                             cpu_eur_per_h=engine.CPU_EUR_PER_SEC * 3600))
