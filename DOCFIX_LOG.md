# DOCFIX log (2026-11-14)

Docs-only. No code was changed. Every number below comes from the live :8737 `/api/scoreboard` and `/api/race` (read-only curl).

| doc | was | now | live source |
|---|---|---|---|
| SUBMISSION.md CubiCasa row | 3042 / 4270, 71.2 %, 0.6 ms | 3124 / 4270, 73.2 %, 0.8 ms | scoreboard correct=3124, median_ms=0.8 |
| README + SUBMISSION total cost | €0.0013 (120 s CPU) | €0.0024 (213.6 s CPU) | race total eur=0.0023633, secs=213.5993 |
| README + SUBMISSION per question | ≈ €0.00000017 | ≈ €0.00000031 | 0.0023633 / 7741 = 3.05e-7 |
| README + SUBMISSION ratio | 10⁵× | 72,135× | 170.47701 / 0.0023633 = 72,135.2 |
| README IFC cost | €0.00039 | €0.00090 | scoreboard eur=0.00089973 |
| README CubiCasa p95 | 322 ms | 321 ms | scoreboard p95_ms=320.8 |
| README Swiss cost (2 places) | €0.000052 | €0.000053 | scoreboard eur=5.2975e-5 |

All log values matched the live API. Two minor items from EVALFIX_LOG (p95, Swiss cost) were fixed as well.
README.md:58 "3042 → 3124 (71.2 % → 73.2 %)" was kept: it is a clearly labelled historical delta.
SUBMISSION.md still starts with "# DRAFT - NOT SUBMITTED". Nothing was submitted or published.
Eval: /api/scoreboard is unchanged (cubicasa5k 3124/4270, ifc_models 1049/1049, opening_design 61/64, swiss_dwellings 2358/2358).
