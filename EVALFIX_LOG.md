# EVALFIX log (2026-11-14)

Disk: 4.3 GB free at start (above the 4 GB stop line); no training, no downloads, only small temp files in /tmp/evalfix_*.

Port note: :8742 was already held by the **jh2-ui2** track's uvicorn (pid 71534, started 06:32). It is not mine, so I
did not kill it. My test server ran on **:8752** (`.venv/bin/python -m uvicorn pinpoint.server:app --port 8752`,
running from ~/jh2-evalfix). :8737 was never touched.

## Task 1: /api/eval_all showed CubiCasa 2728/4270, /api/scoreboard 3124/4270

**Cause: a stale cached result file.** `/api/scoreboard` reads `data/eval/*.json` live on every request. `/api/eval_all`
served `data/eval_all.json`, a derived file written by `python -m pinpoint.eval_all` at 06:32. The raster track later
re-ran `pinpoint.evaluate` (data/eval/*.json mtime 11:21, CubiCasa 3124) but never re-ran `pinpoint.eval_all`, so the
cache kept the 06:32 CubiCasa 2728. It was the same model, the same pipeline and the same scoring code: the file was just out of date.

**Fix (commit ddf03db, merged to main as a fast-forward):**
- `pinpoint/eval_all.py`: `main()` split into `build()` (which returns the dict) and `main()` (which writes the file). `generated` is now the
  mtime of the newest `data/eval/*.json`, not the wall-clock time.
- `pinpoint/server.py` `/api/eval_all`: calls `eval_all.build()` on every request, so its dev split is computed from
  the same `data/eval/*.json` as `/api/scoreboard` and the two can no longer drift apart. Scoring logic is unchanged.
- I re-ran `python -m pinpoint.eval_all`, so the cached `data/eval_all.json` is current too. The running :8737 server
  (old code, which reads that file) now also reports 3124/4270, with no restart. (It will go stale again if evals are re-run
  before :8737 is restarted on the new code.)
- README / DEMO_SCRIPT: removed the "eval_all still shows the earlier 2728 snapshot" caveat.

**Eval before the merge** (full `pinpoint.evaluate` on all four sources, written to /tmp/evalfix_eval so the shared
data/eval was not overwritten):

| source | fresh run | data/eval (scoreboard) | /api/eval_all (:8752) |
|---|---|---|---|
| ifc_models | 1049/1049 | 1049/1049 | 1049/1049 |
| swiss_dwellings | 2358/2358 | 2358/2358 | 2358/2358 |
| opening_design | 61/64 | 61/64 | 61/64 |
| cubicasa5k | 3124/4270 | 3124/4270 | 3124/4270 (73.16 %) |

There was no accuracy drop. eval_all and scoreboard agree. origin/main had not moved, so the rebase was a no-op and the merge was a fast-forward to ddf03db.

## Task 2: DEMO_SCRIPT walk-through against merged main (:8752), read-only

Method: puppeteer-core with headless Chrome over every screen (splash `/?static=1` and animated, Scores, cost race, WC
receipt in German, apartment A area receipt, audit, identify, BoQ, walk-in-3D, and 8 tour frames; screenshots are in
/tmp/evalfix_shots). I also called every `/api` endpoint the script relies on and recounted the backup facts.

Verified OK (each matches /api/scoreboard or a committed file):
- Splash (both static and animated after the count-up): 2,358/2,358 · 1,049/1,049 · 61/64 · 3,124/4,270 (73.2 %), €0.0024,
  frontier est. €170, ~72,135×.
- Scores modal: same four rows, by-type splits, €0.0024 vs €170.48, 7,741 questions, 0 LLM calls.
- Cost race / `/api/race`: 6,592/7,741, €0.0024, 213.6 s, €170.48, 72,135×; per-source rows match the scoreboard.
- WC receipt (DE): 4 = ground truth 4. Area receipt: 80.33 vs 80.34 m², within 0.01 %, 7/7 cross-checks, 74.89 = 74.89 m².
- site1088 apartment C: 82.09 m² exact; the receipt contains Loggia and Balkon as excluded.
- Estonian 4.korrus door question: 42 = 42.
- Audit showcase: 118.C and 129.A untagged; untagged leaf (nearest tags 118.B1/B2/119.A, consistent with README's
  "Fitness Center (118)"); A-801 has 6 dropped and 5 added; fantasy_office 4 duplicated RC columns and 4 walls with 93 % overlap; molio 603
  8.70 vs 10.08 m².
- Identify: drawn-twice doors recounted via `/api/parts` on all 65 Swiss plans = **265 pairs on 61 of 65**, which matches.
- findings.json: 550 Swiss room labels, 16,484 elements, 263 spaces, 9 models, which matches the script.
- `/api/eval_all` unseen: IFC 858/858, Swiss 892/898, IFC-Bench 467/467 answered, 0 crashes, 0 silent. Room-label
  OCR: kitchens 70/75, bathrooms 55/60, saunas 48/77, which matches.
- BoQ / walk / identify agree with each other (36 doors, 28 windows, 31 rooms, 12 sanitary, 25/25 label checks).
- Tour: all 7 steps run; the captions and meter values are computed live.
- The frontend has no hard-coded headline numbers; every figure comes from /api/scoreboard, /api/race or /api/ask.

### RESULT: NOT CLEAN. All screens and /api endpoints are clean. The stale numbers are only in committed docs:

1. **SUBMISSION.md:62**: Accuracy table, CubiCasa row `3042 / 4270`, `71.2 %`, `count 3042/4270`, `0.6 ms`.
   Live (scoreboard): 3124 / 4270, 73.2 %, count 3124/4270, median 0.8 ms.
2. **SUBMISSION.md:80**: Cost table, `€0.0013 (120 s CPU)`. Live (/api/race, cost race screen): €0.0024, 213.6 s.
3. **SUBMISSION.md:81**: `per question ≈ €0.00000017`. Live: €0.0024 / 7,741 ≈ €0.00000031.
4. **SUBMISSION.md:84**: `Ratio ≈ 10⁵×`. Live: 72,135× (shown on the splash and in the cost race).
5. **README.md:80**: Cost table, `€0.0013 (120 s CPU)`. Live: €0.0024, 213.6 s.
6. **README.md:81**: `per question ≈ €0.00000017`. Live ≈ €0.00000031.
7. **README.md:85**: "a frontier VLM would cost roughly 10⁵× more". Live: 72,135×.
8. **README.md:38**: IFC row, "measured cost, whole source" `€0.00039`. Live (scoreboard/race): €0.00090.
9. **README.md:40**: CubiCasa row `p95 322 ms`. Live: 320.8 ms (minor).
10. **README.md:82** / README.md:37: Swiss `€0.000052`. Live: €0.000053 (5.30e-5; rounding, minor).

Cosmetic, not stale: the receipt shows "within 0.01 %" and the BoQ shows "Δ 0.012 %" for the same 80.33 vs 80.34 (0.0124 %,
rounded differently). README.md:58 "3042 → 3124 (71.2 % → 73.2 %)" is a historical delta and is correct as written.
DIRECTIVES.md:25-26 (40.9 %, EUR 0.00006) are the user's original directives, not claims.
