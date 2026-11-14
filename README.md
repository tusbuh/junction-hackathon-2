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

### Receipts: every answer can be checked in seconds

The right-hand panel is a receipt for every answer: the value and the method; the official **tolerance** with the
deviation from the dataset's reference answer when there is one (counts must be exact, area/length/volume within ±2 %,
e.g. `80.33 vs 80.34 m², within tolerance (off by 0.01 %)`); a **confidence colour** with its reasons (exact CAD
geometry, model data, PDF text layer, or a detector on pixels; cross-checks agree or disagree); the **cross-checks**;
an **itemized list** where each line cites its source (`file p.1 at (x, y) pt · DXF ROOM_OUTLINE polygon`,
`model.ifc · IfcDoor GlobalId …`, `scan.png at pixel (x, y)`, `sheet p.1 · schedule row`) and lights up on the drawing
when clicked; items excluded from the take-off with the reason (balconies, loggias, shafts); and the source file's
licence and credit.

### Drawing audit: where a drawing disagrees with itself (`⚠ Audit`, key `A`, `/api/audit?path=…`)

Each check reads the same fact twice, independently, and turns amber when the two readings differ:
printed m² room labels vs the ROOM_OUTLINE polygon (Swiss CAD); door marks in the **door schedule** vs **door tags**
on the floor-plan pages; door swings (arc + leaf, recognised from the vector linework) with no door tag near them;
a schedule-only sheet vs the door tags of the project's earlier plan issue (revision check); IFC elements with
identical geometry (double-counted in every quantity take-off), near-complete overlaps, and IfcSpace `Qto` floor
area vs the footprint of the space's own 3D body. Every drawing also gets a short **"what a site engineer should
double-check"** list (raise an RFI, confirm a door mark before ordering the frame, delete a duplicate before the
take-off). `★ Errors we found in the dataset` (`/?audit=showcase`) shows the real ones, each one click from its evidence:

| Drawing | Finding (measured from the files) |
|---|---|
| Sports_Complex `20150720 - XSC - floor plan and door schedule.pdf` | The door schedule (p.3) lists **41** doors, the plan sheets A-101.A/B tag **39**: 118.C and 129.A have no tag. A door leaf is drawn in the Fitness Center (118) south wall next to the Elec. Room with **no door tag**; it is the only one of the 23 recognised swings without a tag (a later A-801 lists 118.C). |
| Sports_Complex `A-801 - Door and Finish Schedules` (current set) | Against the 2015-07-20 plans: 6 doors dropped (114.A, 120.A, 120.B, 121.C, 123.A, 126.A), 5 added (118.C, 119.B, 122.B, 122.C, 124.B): the door supplier's order must follow the current revision. |
| ifc_bench `fantasy_office_building_3_arc.ifc` | 4 round RC columns (STB d=30) on OG1 exist **twice** with identical geometry (same box to 2 cm, same 0.24 m³), so column counts and concrete volumes over-count; 4 RC wall pairs overlap ~93 %. |
| ifc_models `bsc-molio_molio-with-uris.ifc` | Space "Rum nr. 603 Elevortor teknik": Qto floor area 8.70 m², but its 3D body's footprint is 10.08 m². |

Also audited with nothing to flag: all 550 printed room-area labels on the 65 Swiss plans match their outlines
(±2 %); 16,484 IFC elements and 263 spaces in 9 models fingerprinted. IFC findings are precomputed by
`python -m pinpoint.audit` (it meshes every element) into `static/findings.json`; the rest run on request.

Notable accuracy rules found in the data: a washbasin is a bowl with a drain circle, a WC is a bowl without one
(130/130); a shower is a free 4.5 cm floor drain (hob burners are 8 cm); assembled stairs count once.

### Component identification: click any element, get a site-ready card (`⌖ Identify`, key `I`)

Click any element on the 2D sheet, on an IFC plan, in the 3D model or in the walkthrough and an inspector card says
**what it is** (wall, door, window, slab, column, stair, sanitary fixture, room/space…), **its type**, **its size**
(clear opening width, leaf, swing radius, wall thickness and centre-line length, room net area and perimeter; IFC
`OverallWidth/Height` and `Qto` sets), **its properties** (IFC Psets incl. `FireRating`, `IsExternal`, `LoadBearing`,
material layer build-up, storey, host wall via `IfcRelFillsElement`; Swiss DXF: rooms on both sides of a door, the
room a window lights, section hatch, SIA 416 use class from the printed room name) and **the exact source**
(file, DXF layer + entity handle, or IFC GlobalId + STEP line + type object). Values a 2D plan does not contain
(door height, sill height, fire rating) are listed as missing, never filled in. `/api/inspect?path=…&id=…` or `&x=&y=`.

The parts list (`/api/parts?path=…`) answers "what does this drawing contain?": e.g. *36 doors of 9 types · 28
windows of 10 types · 41 walls · 12 sanitary fixtures · 31 rooms*; every row lights its elements up in 2D and 3D.
It also surfaced a data quirk: in 61 of the 65 Swiss plans some doors are **drawn twice** (identical DOOR polylines,
leaf and swing arc stacked on top of each other; 265 pairs among 1,868 door thresholds). The dataset's door counts include
the duplicates, so PINPOINT answers the same, but the card flags each one so a take-off counts the opening once.
Vector PDF sheets identify the printed tag/text under the click; raster scans list detector symbols when the
detector weights are present.

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
