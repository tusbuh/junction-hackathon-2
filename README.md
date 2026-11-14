# PINPOINT — every answer comes with a receipt

Stoa challenge "Make Blueprints Talk", Junction 2026 (team submission name: AIRAM).

PINPOINT answers plain-language questions about construction drawings and BIM models, in any language. Every answer
shows **where it came from**: the counted doors, toilets, rooms or schedule rows are boxed and numbered on the real
drawing, IFC elements glow in a 3D X-ray view and on the linked 2D plan, and a numbered receipt lists every step, so a
person can check the answer in seconds.

Instead of asking an expensive vision model to "look" at a sheet, PINPOINT reads the geometry that is already in the
file (CAD layers, PDF vector text, IFC elements and quantities) and, for scanned plans, a small fine-tuned detector.
Answers are exact lookups and sums over that geometry. A language model is optional and is only ever allowed to
rewrite the *question* into a template; it never sees the drawing and never produces the answer.

## What it does for a site engineer

Site engineers lose hours a day hunting through drawing sets for one number. PINPOINT turns that hunt into a question
with a checkable answer:

| Site task | What you do in PINPOINT | What you get back |
|---|---|---|
| **Quantity takeoff** (counts, net floor areas, lengths, volumes) | Ask "How many WCs on this floor?" or "Net floor area of apartment A, excluding balconies?" in your own language | The value, every counted item boxed and numbered on the sheet, the ±2 % tolerance badge, and the items left out of the takeoff with the reason (balconies, loggias, shafts) |
| **Door schedule** checks | Ask about door types, widths or frame materials on a schedule sheet (e.g. A-801) | The schedule rows that were read, highlighted where they sit on the sheet |
| **Bill of quantities (BoQ)** | `Bill of quantities` (key `Q`) on any floor | Rooms, floor areas, doors, windows and sanitary fixtures for the whole floor, each line cross-checked against the dataset's own questions; CSV and PDF export |
| **Drawing audit before an RFI** | `⚠ Audit` (key `A`) | Places where a drawing disagrees with itself (schedule vs plan tags, printed m² vs room outline, duplicated IFC elements), each with a short "what to double-check" list: raise an RFI, confirm a door mark before ordering the frame, delete a duplicate before the takeoff |
| **As-built / model checks** | Ask about an IFC model, or click any element (`⌖ Identify`, key `I`) | Element type, size, Psets (fire rating, load-bearing, external), storey, host wall, and the exact source (IFC GlobalId + STEP line, or DXF layer + entity handle); values the drawing does not contain are listed as missing, never filled in |
| **Site walk** | `🚶 Walk in 3D` (key `W`) | The 2D plan extruded into a building you can walk through, with the counted elements glowing |

## Results on the preview set (auto-graded against `questions.jsonl`)

Scoring is the challenge's: **counts must be exact; areas, lengths and volumes within 2 %**. Numbers below are from
`/api/scoreboard` (per-question results in `data/eval/*.json`, written by `python -m pinpoint.evaluate`). Per source,
never blended: the sources differ in kind and size.

| source | what PINPOINT reads | exact / graded | accuracy | median latency | measured cost, whole source |
|---|---|---|---|---|---|
| Swiss floor plans (DXF + PDF, EN/DE/FR/IT) | DXF layers → symbols + room polygons, projected onto the PDF | **2358 / 2358** (count 1614/1614, area 744/744) | **100 %** | 0.2 ms | €0.000052 |
| IFC building models (EN/ET/DA/DE) | ifcopenshell: elements, storeys, quantities, 3D footprints | **1049 / 1049** (area 846/846, count 153/153, volume 34/34, length 16/16) | **100 %** | 38 ms | €0.00039 |
| US drawing sets (opening_design schedule sheets) | rotation-aware vector words → schedule tables, highlighted rows | **61 / 64** (count 37/39, text 15/16, area 9/9) | **95.3 %** | 0.2 ms | €0.0000017 |
| Finnish raster plans (CubiCasa5K PNG) | leak-free YOLOv8n + YOLO11s ensemble (both trained only on the 213 CubiCasa5K plans not in the Stoa set) + fi/en room-label OCR + fixture priors from those 213 plans + nested-box de-duplication | **3124 / 4270** (all count questions) | **73.2 %** | 0.8 ms (p95 322 ms) | €0.0014 |
| IFC-Bench v2 (free text) | deterministic intents over IFC facts, GlobalIds cited | not auto-graded (reference answer shown) | — | — | — |

0 LLM calls in every run above. Open the **▦ Scoreboard** in the app for the live numbers.

**Unseen drawings** (`/api/eval_all`; drawings from the full dataset that are *not* in the
preview split and were never used for development): IFC models **858 / 858**, Swiss floor plans **892 / 898
(99.3 %)**, IFC-Bench free text 467 / 467 answered (not auto-graded). The sample also includes 16 historic and archive drawings
(4 each from europeana, finna, habs and wikimedia, 64 generic questions without reference answers): none is answered
with a number, each returns an explained "can't answer, here's why". Across the whole unseen sample: **0 crashes,
0 silent failures**.

**CubiCasa room-label OCR** (`/api/eval_all`, Tesseract fin+eng, preview): kitchens 70/75, bathrooms 55/60, floors
97/108, balconies 28/35, bedrooms 52/72, WC 41/60, saunas 48/77. Weakest classes are where the remaining raster misses are.

(`/api/eval_all` builds its dev split live from the same `data/eval/*.json` files as the scoreboard, so both report
CubiCasa 3124 / 4270.)

**CubiCasa follow-up (RASTER4): 3042 → 3124 / 4270 (71.2 % → 73.2 %).** The three steps below are measured on preview, and
`python -m pinpoint.raster.breakdown old.json new.json` prints the per-template delta:
1. Bedrooms (+16): when OCR reads the bedroom labels, the count is raised to the number of detector bedroom boxes with
   confidence ≥ 0.6, and never lowered. OCR misses labels far more often than it invents them. The 0.6 cut sits in the
   middle of a plateau (0.5–0.8) that holds in both halves of a 2-fold split of the preview plans. **This is dev tuning on
   preview.**
2. Toilets (+4): the count is never below the number of separate WC rooms. This holds on 210 of the 213 leak-free plans.
3. Second detector (+62): a YOLO11s trained on the same 213 leak-free plans (val mAP50 0.71 vs 0.66 for YOLOv8n), with
   its boxes fused with the YOLOv8n boxes. The choices were made on the 25 held-out leak-free plans only, never on preview:
   which classes use the ensemble (all except shower, bathtub and bedroom) and the per-class thresholds. Windows go from
   166 to 176, doors 170 → 176, sinks 306 → 314, toilets 356 → 360, saunas 266 → 278, separate WC 194 → 202, floors
   454 → 470, and balconies 116 → 114.
Tried and dropped because they showed no robust gain on val25 or on preview CV: threshold re-tuning, soft (confidence-sum)
counts, multi-scale inference, splitting long window boxes, other cross-count rules, and a crop re-scoring classifier.

## Cost

Measured CPU time × €0.04 per vCPU-hour, plus LLM tokens when the optional router is used (0 calls in all runs
above). From `/api/race` (same `data/eval/*.json`):

| | PINPOINT (measured) | frontier VLM (list-price estimate) |
|---|---|---|
| all 7,741 graded preview questions | **€0.0013** (120 s CPU) | €170.48 |
| per question | ≈ €0.00000017 | ≈ €0.022 |
| Swiss floor plans, 2,358 questions | €0.000052 | €51.93 |

The VLM column is an estimate, not a measurement: ~1.6k image tokens per 1.15 MP at 200 dpi plus prompt/answer at
$3/$15 per Mtok. On these numbers a frontier VLM would cost roughly 10⁵× more for the same questions. The UI's cost meter
shows both per answer; click it (or press `R`) for the cost race.

## How it works

```
file ─► format adapter ─► geometry index ─► question router ─► exact lookup / sum ─► receipt
        DXF  (ezdxf)        symbols, room polygons      rules (EN/DE/FR/IT/FI/ET/DA)       value + steps + evidence
        PDF  (PyMuPDF)      vector words, tables        → multilingual lexicon (~30 langs)  (boxes, polygons, GlobalIds)
        IFC  (ifcopenshell) elements, storeys, Qto      → optional tiny LLM: template only
        PNG  (YOLO)         symbol + room detections
```

A hybrid: vector parsing where the file has vectors, a small fine-tuned detector (YOLOv8n) plus OCR where it only has
pixels, and an optional frontier model that only rewrites the question. **No LLM is in the scored path.** Same-name
files in several formats are the same drawing: PINPOINT uses the vector one (DXF/IFC over PDF over PNG), and the
`ifc_models` plan PDFs are linked to the IFC they were rendered from.

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
when clicked; items excluded from the takeoff with the reason (balconies, loggias, shafts); and the source file's
licence and credit.

### Drawing audit: where a drawing disagrees with itself (`⚠ Audit`, key `A`, `/api/audit?path=…`)

Each check reads the same fact twice, independently, and turns amber when the two readings differ:
printed m² room labels vs the ROOM_OUTLINE polygon (Swiss CAD); door marks in the **door schedule** vs **door tags**
on the floor-plan pages; door swings (arc + leaf, recognised from the vector linework) with no door tag near them;
a schedule-only sheet vs the door tags of the project's earlier plan issue (revision check); IFC elements with
identical geometry (double-counted in every quantity takeoff), near-complete overlaps, and IfcSpace `Qto` floor
area vs the footprint of the space's own 3D body. Every drawing also gets a short **"what a site engineer should
double-check"** list (raise an RFI, confirm a door mark before ordering the frame, delete a duplicate before the
takeoff). `★ Errors we found in the dataset` (`/?audit=showcase`) shows the real ones, each one click from its evidence:

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
the duplicates, so PINPOINT answers the same, but the card flags each one so a takeoff counts the opening once.
Vector PDF sheets identify the printed tag/text under the click; raster scans list detector symbols when the
detector weights are present.

### 3D walkthrough, bill of quantities, cost race, guided tour

- **`🚶 Walk in 3D`** (key `W`): any Swiss plan or IFC model as a walkable building; the elements in the current
  answer glow, and clicking one opens its Identify card.
- **`Bill of quantities`** (key `Q`): the whole floor's BoQ, every line cross-checked against the dataset's own
  questions, CSV and PDF export (`/api/boq`, `/api/boq.csv`, `/api/boq.pdf`).
- **Cost race** (click the cost meter, key `R`, or `?race=1`): measured PINPOINT cost vs the frontier-VLM list-price
  estimate, per source, from `data/eval/*.json`.
- **`▶ Tour`**: a 7-scene captioned tour (exact count, area within 2 %, 2D ⇆ 3D, door schedule, walkthrough, BoQ,
  cost race). Captions are built from the live answers; no number is typed into the tour.
- `?static=1` (or prefers-reduced-motion) shows final numbers without count-up animation, for screenshots.

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

## LICENSES

The Stoa Junction 2026 dataset is for **non-commercial use in the Junction challenge**. Every drawing keeps its own
licence, listed with its credit in `data/<source>/LICENSE.md`; PINPOINT shows that credit **under every drawing it
displays** (2D sheet and 3D view) and in every answer's receipt. Questions inherit the licence of the drawing they
ask about.

**CubiCasa5K — CC BY-NC-SA 4.0** (https://creativecommons.org/licenses/by-nc-sa/4.0/). Floor plan images from
CubiCasa5K, © 2019 CubiCasa. Credit: Ahti Kalervo, Juha Ylioinas, Markus Häikiö, Antti Karhu, Juho Kannala,
"CubiCasa5K: A Dataset and an Improved Multi-Task Model for Floorplan Image Analysis", SCIA 2019,
https://zenodo.org/records/2613548. Non-commercial use only. **ShareAlike:** the detector weights, derived labels and
anything else adapted from CubiCasa5K are shared under the same CC BY-NC-SA 4.0 licence. Both detectors (YOLOv8n and
YOLO11s, Ultralytics AGPL-3.0) were trained only on the 213 CubiCasa5K plans that are not in the Stoa set (zero overlap asserted).

**Swiss Dwellings — CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/). Swiss Dwellings v3.0.0 by Matthias
Standfest, Michael Franzen, Yvonne Schröder, Luis Gonzalez Medina, Yarilo Villanueva Hernandez, Jan Hendrik Buck,
Yen-Ling Tan, Milena Niedzwiecka, Rachele Colmegna (Archilyse AG), doi:10.5281/zenodo.7788422. The drawings were
rendered by Stoa from the published geometry (labels, language and numbering added); Archilyse AG does not endorse them.

**opening_design — CC BY-SA 4.0 and MIT**: OpeningDesign, Madison, Wisconsin (https://github.com/OpeningDesign) and the
project team named in each title block; MIT for 104_Janesville and Schultz_Residence (© 2014 Ryan Schultz).
ShareAlike: adaptations of CC BY-SA files are shared under CC BY-SA 4.0.

**ifc_models / ifc_bench — per file** (see each `LICENSE.md`): KIT models (IAI / Karlsruhe Institute of Technology),
MIT models (DigitalHub, RWTH Aachen; Chesapeake Bay Bridge-Tunnel, buildingSMART Community; ResBIM, Xing Liang),
GPL-3.0 models (BIMserver.org). IFC-Bench v2 questions © 2025 Sylvain Hellin, CC BY 4.0 (Hellin, Nousias & Borrmann).

**NoDerivatives (ND) files stay unchanged.** Duplex and Medical-Dental Clinic (buildingSMART) are handled under the
stricter CC BY-ND 3.0: PINPOINT never writes an edited copy of an ND file. It only reads them and draws its evidence
as a separate overlay on top of the unchanged drawing.

**Other sources** (full dataset): finna (Helsinki City Archives, Architecture & Design Museum) CC BY 4.0; habs (HABS/
HAER/HALS, Library of Congress) public domain; europeana and wikimedia per file. Credit each file as given in its
`LICENSE.md`.

**Software**: three.js (MIT), ifcopenshell (LGPL), PyMuPDF (AGPL), ezdxf (MIT), ultralytics (AGPL), Tesseract
(Apache 2.0).
