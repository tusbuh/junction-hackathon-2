# PINPOINT: every answer comes with a receipt
Stoa challenge "Make Blueprints Talk", Junction 2026. Final deadline **Sun 15 Nov 10:00 (Helsinki)**. Preliminary submission **tonight 23:59**.

## 1. What the data really is (preview, 924 files, 7,990 questions)
| source | files | format | questions | languages |
|---|---|---|---|---|
| cubicasa5k | 241 | PNG raster (Finnish real-estate plans) | 4,270 (53%) | EN + FI |
| swiss_dwellings | 65 x3 | vector PDF + DXF (+PNG), same drawing | 2,358 (30%) | EN/DE/FR/IT |
| ifc_models | 4 IFC + 3 plan PDF/SVG | IFC2x3/4 + rendered plans | 1,049 (13%) | EN/ET/DA |
| ifc_bench | 5 IFC | IFC | 249 free-text (IFC-Bench v2) | EN |
| opening_design | 55 PDF, 20 DWG, 1 DXF, 5 IFC | US drawing sets | 64 | EN |
| habs, finna, europeana, wikimedia | 374 JPG, 7 SVG | historic scans | 0 in preview | many |

Question types: count 6,076 · area 1,599 · text 265 · volume 34 · length 16. Scoring: counts exact, area/length/volume within 2%, text free-form.
Full set: about 14k drawings, about 120k questions, about 30 languages. Being downloaded to `/workspace/stoa/full.zip`.

**Key insight:** this is a quantity-takeoff benchmark. Almost every question is "count symbol X" or "sum area of Y". Those are geometry problems, not language problems. Frontier models are bad at counting symbols on dense sheets, and they are expensive. CAD/BIM geometry gives exact answers with exact coordinates for free.

## 2. Concept
**PINPOINT turns every drawing into a "geometry index" once: every door, window, WC, room polygon, label and IFC element, each with its coordinates. Questions are answered by exact lookups and sums over that index, and every answer comes with a receipt: the drawing with each counted item boxed and numbered, plus a "printed label vs computed geometry" cross-check. The language model only routes the question (any language) to a lookup, so a typical answer costs about €0.0000 and takes about 50 ms.**

Why it isn't made obsolete next year: frontier models get better at reading, but they never get exact counting with coordinates for free. PINPOINT can also use a better model as the router or as the raster fallback without changing anything else.

### Architecture (simple)
```
file ─► format adapter ─► GEOMETRY INDEX (sqlite/json): {kind, label, room, unit, storey, polygon/bbox, page, source-entity-id}
          ├─ DXF (ezdxf): layers DOOR/WINDOW/FIXTURE/ROOM_OUTLINE/ROOM_TEXT/UNIT_OUTLINE → symbols, room polygons (shapely)
          ├─ vector PDF (PyMuPDF): words + bboxes, drawings; affine DXF→PDF fit on shared labels (max error 0.23 pt)
          ├─ IFC (ifcopenshell): IfcDoor/Window/Space/Wall… per storey, Qto quantities, 3D geometry when Qto is missing
          ├─ raster PNG/JPG: small fine-tuned detector (YOLO-nano) for doors/windows/WC/sinks/tubs/showers/saunas + OCR for labels
          └─ schedule PDFs: word-row clustering into tables (door schedules)
question ─► router: regex/keyword rules (EN/DE/FR/IT/FI/ET/DA) → {op: count|sum_area|lookup, kind, filter}
             └─ fallback: tiny LLM (Gemini Flash-Lite class) returns the same JSON, never the answer itself
         ─► executor over the index → value + evidence list
         ─► renderer: sheet with numbered boxes/polygons + zoom crop + "how I got this" line + confidence
         ─► (text questions only) LLM phrases the answer from the extracted facts, citing element IDs
```
Confidence and safety: when two independent signals disagree (printed "15.61 m²" label vs computed polygon area, IFC Qto vs geometry, detector vs VLM), we flag the answer amber and show both. That is the verification story.

### Demo moment
A judge types in Finnish or German: *"Wie viele WCs sind auf diesem Grundriss?"* In about 50 ms PINPOINT answers **4** and four yellow numbered boxes light up on the real Swiss sheet, with a cost counter reading **€0.0000**. Then the judge asks for the net area of apartment A. Its 9 rooms fill in one by one, each tagged with its area, summing to 80.33 m² (ground truth 80.34). Last, a live scoreboard runs the full question set: "PINPOINT 98% · €0.00 vs frontier VLM X% · €Y".

### Backups (one line each)
1. **IFC-only "Ask the model"**: answers straight from IFC with a 3D/plan view that highlights the counted elements by GlobalId (99.2% on the answerable preview IFC questions).
2. **Raster counter**: a small detector fine-tuned on public CubiCasa5K labels (test plans held out) counts symbols on scanned Finnish plans and shows a crop gallery, "here are the 13 windows I counted".

## 3. Proof built tonight (box: /workspace/stoa/proof)
- `swiss.py` deterministic DXF engine: **2,314 / 2,358 = 98.1%** of all Swiss preview questions, in 4 languages, 0 LLM calls, about 4 s for all 65 sheets. Doors, windows, WCs, basins, bathtubs, apartments, labelled-room counts, room, apartment and floor areas (computed from room polygons, because some sheets have no printed areas). Misses: showers (rule is too strict, 30/42) and the shaft/void exclusion in floor totals.
- `ifcq.py` IFC engine: **1,017 / 1,025 = 99.2%** of the ifc_models questions whose IFC is in the preview (24 questions belong to FZK-Haus, whose IFC is only in the full set). Misses: Molio stairs (it counts stair parts instead of stairs) and one room name with a typo ("Kontor ([Rum nr. 108)").
- `render.py` evidence images (DXF→PDF affine fit, max error 0.23 pt):
  - `proof/demo_wc.png` and `demo_wc_zoom.png`: "How many toilets?" → 4 (gt 4), 4 numbered boxes.
  - `proof/demo_aptA.png` and `_zoom.png`: apartment A net area → 80.33 m² (gt 80.34), 9 rooms highlighted.
  - `proof/demo_doors.png`: German doors question → 36 (gt 36).
  - `proof/demo_answers.json`: answer, method, evidence bboxes and ground truth.
- `eval_swiss.txt`, `eval_ifc.txt`: per-question-type accuracy tables.
- Probes: vector PDFs have words with coordinates (PyMuPDF). 7 of 55 opening_design PDFs are scans (need OCR). PyMuPDF `find_tables` found no table on the A-801 door schedule (1,885 words, so row clustering is needed). ifcopenshell 0.8 opens 2–74 MB IFCs in 0.3–1.7 s. ezdxf reads all DXF files. DWG is not read directly (convert with ODA File Converter or LibreDWG, or skip, since DWG siblings mostly have PDFs).

## 4. Cost per question (estimate, check current model prices before quoting)
| path | share of questions | compute | cost |
|---|---|---|---|
| vector DXF/PDF + IFC lookup | about 45% | about 10–50 ms CPU | ≈ €0 |
| raster detector (YOLO-nano, CPU) | about 50% | about 50–100 ms CPU | ≈ €0.00001 |
| LLM router fallback (Flash-Lite class, about 600 in / 60 out tokens) | 5–10% | 1 call | about €0.0001 |
| VLM verifier on low-confidence raster crops only | about 10% of raster | 1 small image call | about €0.001 |
| text answers (IFC-bench): LLM phrases extracted facts | about 3% | 1 call, about 2k tokens | about €0.0005 |
| **blended** | | | **≈ €0.0001–0.0003 per question** (vs about €0.01–0.03 for sending a full sheet to a frontier VLM, roughly 100x cheaper) |

## 5. Hour-by-hour plan (Helsinki time)
**Fri 13 Nov**
- 22:30–23:30 · Clean up proof into repo `stoa-pinpoint` (private), README with numbers + demo images. Kick off CubiCasa5K download (running).
- 23:30–23:59 · **Preliminary submission** (text below), user submits it. Nothing public without the user's OK.
- 00:00–02:00 · Raster track: convert CubiCasa5K SVG annotations to YOLO labels (door, window, WC, sink, bathtub, shower, sauna-stove), **exclude the dataset's 241+ plan IDs**, start YOLO-nano training on box CPU/GPU overnight.
- 02:00–07:30 · Sleep (training runs).

**Sat 14 Nov**
- 07:30–09:00 · Evaluate detector on cubicasa preview questions; add "floors (storeys)" = count of plan clusters/titles; sauna = sauna-stove symbol or "SAUNA"/"LH" OCR label.
- 09:00–11:00 · Unified question router (rules + Flash-Lite JSON fallback), one `answer(path, question)` API across sources. Run on the full 120k-question set as soon as full.zip is unpacked; publish an internal accuracy table per source.
- 11:00–13:00 · Web UI (single page: upload/select drawing, ask, sheet viewer with numbered overlays, zoom crop, "how I got this", cost meter). FastAPI + plain HTML/canvas.
- 13:00–15:00 · IFC view: plan render with highlighted elements (and an optional 3D view via web-ifc/xeokit if time), text answers for IFC-bench with cited GlobalIds.
- 15:00–17:00 · Opening_design schedules: row clustering → door-schedule counts with highlighted rows; OCR (Tesseract) for scanned sheets; DWG via LibreDWG/ODA conversion if quick.
- 17:00–19:00 · Cross-check flags (label vs geometry, Qto vs mesh, detector vs VLM) → confidence colours. Fix top failure categories from the eval.
- 19:00–21:00 · Benchmark page: accuracy and €/question vs a frontier-VLM baseline on a 200-question sample (cap spend at about €5).
- 21:00–23:00 · Demo script, 2-min video recording, polish.
- 23:00–07:00 · Buffer/sleep. Full-set eval runs overnight.

**Sun 15 Nov**
- 07:00–08:30 · Final fixes, freeze. README, screenshots, licence credits (CC BY-NC-SA for CubiCasa, CC BY for Swiss Dwellings).
- 08:30–09:30 · Write the final submission and record the video. User reviews.
- **by 09:45** · User submits (deadline 10:00).

## 6. Preliminary submission text (draft, the user submits it)
**Title:** PINPOINT: blueprints that show their work
**Challenge:** Stoa, Make Blueprints Talk
**Short description:** PINPOINT answers natural-language questions about construction drawings and BIM models in any language, and every answer comes with a receipt: the counted doors, toilets or rooms are boxed and numbered on the real drawing, so a site engineer can verify the answer in seconds. Instead of asking an expensive vision model to "look" at a sheet, PINPOINT first turns each drawing into a geometry index (CAD layers, PDF vector text, IFC elements and quantities, and a small fine-tuned symbol detector for scanned plans). It then answers with exact lookups and sums. A small, cheap language model only interprets the question. Early results on Stoa's preview data: 98% exact on 2,358 Swiss floor-plan questions (EN/DE/FR/IT) and 99% on IFC model questions, at a cost of about €0.0001 per question. Disagreements between independent signals (printed area label vs computed room polygon) are flagged for the human.
**Tech:** Python, ezdxf, PyMuPDF, ifcopenshell, shapely, YOLO-nano, FastAPI, Gemini Flash-Lite (router only).

## TOP PRIORITIES FROM THE USER (override anything above if in conflict)
1. Stunning visuals. Render the drawings richly in 2D (crisp, zoomable, nice colours), with each answer's source highlighted on the drawing as numbered boxes or shading, plus a list of the cited items. Add a 3D view of the IFC building model (e.g. web-ifc / three.js) with the answer's elements highlighted, as long as it stays within the challenge rules.
2. Follow the Stoa challenge rules strictly (see BRIEF.md). It answers plain-language questions about construction drawings and 3D building models, and every answer shows where on the drawing it came from, so a person can check it in seconds.
3. Optimize all four equal judging criteria: accuracy, visual verification and clear reasoning, creativity, and low running cost. Show a visible cost-per-question meter.
4. Aim to win. The deadline is Sunday Nov 15 at 10:00 Helsinki. Get a polished end-to-end demo working early, then improve it.
Never make the repo public or submit anything. That needs the user's own OK.
