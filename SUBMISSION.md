# DRAFT - NOT SUBMITTED

> Draft for the team to review. Nothing here has been submitted or published. Every number is from `/api/scoreboard`,
> `/api/eval_all`, `/api/race` or a committed file in this repo; re-check them against the live scoreboard before
> submitting.

---

# PINPOINT — every answer comes with a receipt

**Submitted as:** AIRAM · Junction 2026 · Stoa challenge *"Make Blueprints Talk"*

## Pitch

Site engineers lose hours a day hunting through drawing sets for one number, and general AI fails on complex
drawings because it reads a sheet like a photo and guesses. PINPOINT reads the drawing the way an engineer does: from
the geometry already in the file (CAD layers, PDF vector text, IFC elements and quantities) and, for scanned plans,
a small fine-tuned detector. Ask in any language ("Wie viele WCs…?", "Mitu ust…?", "net floor area of apartment A")
and you get an exact answer with a receipt. Every counted item is boxed and numbered on the real drawing, every line
is cited to its DXF entity, IFC GlobalId or schedule row, and the deviation from the reference is shown against Stoa's
2 % tolerance. It turns a quantity takeoff, a door schedule check or a BoQ into seconds of verification. It also
catches mistakes in the drawings themselves: a door schedule that lists 41 doors on plans that tag 39, and RC columns
modelled twice in an IFC, each one an RFI before it becomes a wrong order on site. All of this costs about a hundred
thousand times less than asking a frontier vision model.

## How it works

```
file ─► format adapter ─► geometry index ─► question router ─► exact lookup / sum ─► receipt
        DXF  (ezdxf)        symbols, room polygons      rules (EN/DE/FR/IT/FI/ET/DA)       value + steps + evidence
        PDF  (PyMuPDF)      vector words, tables        → multilingual lexicon (~30 langs)  (boxes, polygons, GlobalIds)
        IFC  (ifcopenshell) elements, storeys, Qto      → optional LLM: template only
        PNG  (YOLOv8n+OCR)  symbol + room-label detections
```

- **Hybrid, vector first.** Where the file has vectors (DXF, IFC, vector PDF), PINPOINT parses them and answers with
  exact lookups and sums. Same-name files in several formats are the same drawing; the vector one wins, and IFC plan
  PDFs are linked to their model, so 2D and 3D light up together by GlobalId.
- **Small models where there are only pixels.** Finnish raster plans use a leak-free YOLOv8n trained only on the 213
  CubiCasa5K plans not in the Stoa set, plus Tesseract fin+eng room-label OCR and fixture priors from those 213 plans.
- **Optional frontier model, never in the scored path.** An LLM may only rewrite a question into a template when no
  rule or lexicon entry matches. It never sees the drawing and never produces the answer. **0 LLM calls** in every
  scored run below.
- **Verification built in.** Each receipt carries the method, a confidence colour with reasons, cross-checks (printed
  m² label vs room polygon; IFC `Qto` vs 3D footprint), itemized citations that light up on the drawing, items
  excluded from the takeoff with the reason, and the drawing's licence credit.
- **Beyond Q&A:** drawing audit (schedule vs plan tags, revision diff, duplicated IFC elements), click-to-identify any
  component (type, size, Psets, exact source; missing values stay missing), 3D walkthrough, one-click bill of
  quantities (CSV/PDF), cost race, and a captioned guided tour.

## Accuracy

Stoa's scoring: counts exact; areas, lengths and volumes within 2 %. Per source, never blended.

**Preview set** (`/api/scoreboard`, `data/eval/*.json`):

| source | exact / graded | accuracy | by type | median latency |
|---|---|---|---|---|
| Swiss floor plans (DXF + PDF) | **2358 / 2358** | **100 %** | count 1614/1614 · area 744/744 | 0.2 ms |
| IFC building models | **1049 / 1049** | **100 %** | area 846/846 · count 153/153 · volume 34/34 · length 16/16 | 38 ms |
| US drawing sets (opening_design) | **61 / 64** | **95.3 %** | count 37/39 · text 15/16 · area 9/9 | 0.2 ms |
| Finnish raster plans (CubiCasa5K) | **3124 / 4270** | **73.2 %** | count 3124/4270 | 0.8 ms |

**Unseen drawings** (`/api/eval_all`, full-dataset drawings not in the preview, never used for development):

| source | result |
|---|---|
| IFC building models | **858 / 858** (100 %) |
| Swiss floor plans | **892 / 898** (99.3 %) |
| IFC-Bench v2 free text | 467 / 467 answered (not auto-graded) |
| historic/archive scans (europeana, finna, habs, wikimedia; 16 drawings) | explained "can't answer, here's why", no guesses |
| whole unseen sample | **0 crashes, 0 silent failures** |

## Cost

Measured CPU time × €0.04 per vCPU-hour (+ LLM tokens if the optional router is used: 0 calls). From `/api/race`:

| | PINPOINT (measured) | frontier VLM (list-price estimate*) |
|---|---|---|
| all 7,741 graded preview questions | **€0.0024** (213.6 s CPU) | €170.48 |
| per question | ≈ €0.00000031 | ≈ €0.022 |

\* Estimate, not a measurement: ~1.6k image tokens per 1.15 MP at 200 dpi plus prompt/answer at $3/$15 per Mtok.
Ratio ≈ 72,135×.

## Real errors found in the dataset (from the files, `static/findings.json` + `/api/audit`)

- Sports Complex 2015-07-20 door package: door schedule lists **41** doors, plan sheets tag **39** (118.C, 129.A
  untagged); one drawn door leaf in the Fitness Center wall has no tag.
- Sports Complex A-801 (current) vs the 2015-07-20 plans: 6 doors dropped, 5 added.
- `fantasy_office_building_3_arc.ifc`: 4 round RC columns on OG1 modelled twice with identical geometry.
- `bsc-molio_molio-with-uris.ifc`: space 603 `Qto` floor area 8.70 m² vs 10.08 m² footprint of its own 3D body.
- Swiss plans: in 61 of 65 plans some doors are drawn twice (265 stacked pairs); flagged so a takeoff counts the
  opening once.

## Licences and credits

The Stoa Junction 2026 dataset is for non-commercial use in the Junction challenge. Each drawing's credit is shown
under every drawing in the app, in every receipt, and must appear in screenshots and the video. Full details in
README.md → LICENSES and `data/<source>/LICENSE.md`.

- **CubiCasa5K — CC BY-NC-SA 4.0.** © 2019 CubiCasa. Kalervo, Ylioinas, Häikiö, Karhu, Kannala, "CubiCasa5K: A Dataset
  and an Improved Multi-Task Model for Floorplan Image Analysis", SCIA 2019, https://zenodo.org/records/2613548.
  Non-commercial. ShareAlike: our detector weights and derived labels are shared under CC BY-NC-SA 4.0.
- **Swiss Dwellings — CC BY 4.0.** Swiss Dwellings v3.0.0, Standfest, Franzen, Schröder, Gonzalez Medina, Villanueva
  Hernandez, Buck, Tan, Niedzwiecka, Colmegna (Archilyse AG), doi:10.5281/zenodo.7788422. Drawings rendered by Stoa
  from the published geometry; Archilyse AG does not endorse them.
- **opening_design — CC BY-SA 4.0 / MIT.** OpeningDesign, Madison, WI, and the project teams in each title block.
  ShareAlike applies to adaptations.
- **IFC models and IFC-Bench — per file.** KIT (IAI / Karlsruhe Institute of Technology), MIT models (DigitalHub RWTH
  Aachen, buildingSMART Community, ResBIM), GPL-3.0 (BIMserver.org). IFC-Bench v2 questions © 2025 Sylvain Hellin,
  CC BY 4.0.
- **NoDerivatives:** Duplex and Medical-Dental Clinic are treated as CC BY-ND 3.0. They are kept unchanged and shown as-is
  with overlays only. No edited copies are made.
- Questions inherit the licence of their drawing.
- Software: three.js (MIT), ifcopenshell (LGPL), PyMuPDF (AGPL), ezdxf (MIT), ultralytics (AGPL), Tesseract (Apache 2.0).
