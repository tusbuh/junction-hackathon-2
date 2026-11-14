# PINPOINT — every answer comes with a receipt

Stoa challenge "Make Blueprints Talk", Junction 2026.

PINPOINT answers plain-language questions about construction drawings and BIM models, in any language. Every answer
shows **where it came from**: the counted doors, toilets, rooms or schedule rows are boxed and numbered on the real
drawing, IFC elements glow in a 3D X-ray view and on the linked 2D plan, and a numbered receipt lists every step, so a
person can check the answer in seconds.

Instead of asking an expensive vision model to "look" at a sheet, PINPOINT reads the geometry that is already in the
file (CAD layers, PDF vector text, IFC elements and quantities) and, for scanned plans, a small fine-tuned detector.
Answers are exact lookups and sums over that geometry. A language model is optional and is only ever allowed to
rewrite the *question* into a template; it never sees the drawing and never produces the answer.

## Results on the preview set (auto-graded against `questions.jsonl`)

| source | what PINPOINT reads | accuracy | median latency | cost / question |
|---|---|---|---|---|
| Swiss floor plans (DXF + PDF, EN/DE/FR/IT) | DXF layers → symbols + room polygons, projected onto the PDF | **99.2 %** (2338/2358) | < 1 ms warm | ≈ €0.00000003 |
| IFC building models (EN/ET/DA/DE) | ifcopenshell: elements, storeys, quantities, 3D footprints | **97.7 %** (1025/1049); **100 %** of questions whose IFC is in the preview | 44 ms | ≈ €0.0000005 |
| US drawing sets (schedule sheets) | rotation-aware vector words → schedule tables, highlighted rows | 70 % (40/57) | ~0.1 s | ≈ €0.000001 |
| IFC-Bench v2 (free text) | deterministic intents over IFC facts, GlobalIds cited | not auto-graded (reference answer shown) | ~0.1 s | ≈ €0.000001 |
| Finnish raster plans (PNG) | leak-free YOLOv8n (trained only on the 213 CubiCasa5K plans not in the Stoa set) + fi/en room-label OCR | 2728 / 4270 = 63.9 % exact (preview dev split) | — | — |

Open the **▦ Scoreboard** in the app for the live numbers. Counts must be exact; areas, lengths and volumes within 2 %.
The 24 IFC misses all refer to FZK-Haus, whose IFC file is not part of the preview.

**Cost.** Measured CPU time × €0.04 per vCPU-hour, plus LLM tokens when the optional router is used (0 calls in all
runs above). The UI's cost meter shows this per answer next to an estimate of what a frontier VLM would cost for the
same sheet (~1.6k image tokens per 1.15 MP at 200 dpi plus prompt/answer at $3/$15 per Mtok): typically 10⁴–10⁵× more.

## How it works

```
file ─► format adapter ─► geometry index ─► question router ─► exact lookup / sum ─► receipt
        DXF  (ezdxf)        symbols, room polygons      rules (EN/DE/FR/IT/FI/ET/DA)       value + steps + evidence
        PDF  (PyMuPDF)      vector words, tables        → multilingual lexicon (~30 langs)  (boxes, polygons, GlobalIds)
        IFC  (ifcopenshell) elements, storeys, Qto      → optional tiny LLM: template only
        PNG  (YOLO)         symbol + room detections
```

Verification is built in, not bolted on:
- **Cross-checks**: the printed area label on a Swiss plan vs the area computed from the room polygon; IFC `Qto`
  areas vs the 3D footprint. Disagreements turn amber.
- **2D ↔ 3D linking**: the plan SVGs rendered from IFC carry each element's GlobalId, so the same doors light up on the
  plan and in the 3D model with no geometric fitting. Storey questions get an architectural section cut 1.2 m above
  that floor.
- **DXF → PDF projection**: an affine fit on room labels printed in both files (max error ≈ 0.2 pt) places CAD geometry
  exactly on the sheet a person reads.
- **Honest misses**: "not available in the model" is answered only after searching every property set; borderline
  detections are listed as such.

Notable accuracy rules found in the data: a washbasin is a bowl with a drain circle, a WC is a bowl without one
(130/130); a shower is a free 4.5 cm floor drain (hob burners are 8 cm); assembled stairs count once.

## Run

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
# dataset: unzip the Stoa preview into data/preview/ (or set PINPOINT_DATA to the folder with questions.jsonl)
.venv/bin/python -m pinpoint.server          # http://127.0.0.1:8737
.venv/bin/python -m pinpoint.evaluate        # per-source accuracy -> data/eval/*.json (feeds the Scoreboard)
.venv/bin/python -m pinpoint.answer questions.jsonl > answers.jsonl   # batch mode with evidence per answer
```

Optional: `ANTHROPIC_API_KEY` enables the template-only LLM router fallback for questions no rule or lexicon entry
matches (its token cost is added to the meter).

App: pick a drawing, ask (or click an example question), hover a receipt row to locate it, click to zoom. "Run all
questions on this drawing" grades every dataset question for that file live.

## Licences and credits

Drawings and questions come from the Stoa Junction 2026 dataset and keep their licences (see each
`data/<source>/LICENSE.md`): Swiss Dwellings CC BY 4.0, CubiCasa5K CC BY-NC-SA 4.0, Kalervo et al. 2019 (detector weights
and derived labels keep CC BY-NC-SA; trained only on the 213 CubiCasa5K plans that are not in the Stoa set, zero overlap asserted), opening_design CC BY-SA 4.0, IFC models per file. three.js (MIT),
ifcopenshell (LGPL), PyMuPDF (AGPL), ezdxf (MIT), ultralytics (AGPL).
