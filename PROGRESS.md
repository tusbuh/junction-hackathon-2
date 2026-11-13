# PROGRESS

Run: `uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt && .venv/bin/python -m pinpoint.server` → http://127.0.0.1:8737
Data: preview set unzipped to `data/preview/junction-dataset-preview` (gitignored). 3D meshes cached in `data/cache`.

## Done
- [x] Preview dataset downloaded + unzipped into data/ (gitignored)
- [x] `pinpoint/` package: swiss (DXF geometry engine), ifcq (IFC engine), mesh (IFC → binary mesh for three.js), engine (dispatcher, DXF→PDF affine fit, cost model, grading), server (FastAPI)
- [x] Web UI (`static/`): drawing picker per source, question box + dataset example chips, answer card with ground-truth badge, 2D vector sheet viewer (PDF → SVG, crisp at any zoom, blueprint/paper toggle, pan/zoom, numbered evidence polygons/boxes, animated), 3D X-ray IFC viewer (three.js, answer elements glow amber with numbered labels, click to inspect GlobalId), receipt (step trace + cross-checks printed label vs computed polygon), cost meter (this answer, latency, LLM calls, session total, frontier-VLM baseline, savings ×)
- [x] End-to-end: Swiss "net area of apartment A" → 80.33 m² (gt 80.34), 9 rooms shaded, 7/7 cross-checks agree

- [x] Accuracy: Swiss 99.2% (drain-circle WC/basin rule 130/130, free-drain shower rule), IFC 100% of answerable (stair assemblies, tolerant room names)
- [x] 2D plan ↔ 3D linking by GlobalId (IFC plan SVGs), storey section cut, blueprint restyle
- [x] Multilingual lexicon router (~30 languages) + optional template-only LLM fallback (ANTHROPIC_API_KEY)
- [x] Batch CLI `python -m pinpoint.answer`, eval harness `python -m pinpoint.evaluate`, Scoreboard modal, run-all audit strip
- [x] IFC-Bench free-text engine (types/extremes/totals/levels/rooms/materials/fire/load-bearing/not-in-model), cites GlobalIds
- [x] US schedules engine (rotation-aware tables, highlighted rows): 21/58 auto-graded
- [x] Raster QA adapter ready; YOLO detector training on CubiCasa5K subset (preview ids excluded) in progress
- [x] README with results and run instructions

## Next
- IFC plan PDFs: project 3D elements onto the 2D plan sheet
- cubicasa5k raster (53% of questions): symbol detector
- opening_design door schedules; ifc_bench text questions
- eval page / scoreboard
