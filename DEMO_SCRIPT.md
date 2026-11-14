# PINPOINT — 3-minute demo script

Live app: `http://127.0.0.1:8737` (add `?static=1` for screen recordings, so counters show final values instantly).
Every number below comes from `/api/scoreboard`, `/api/eval_all`, `/api/race` or a committed file (README.md,
`static/findings.json`). Where a value is computed live on screen, the script says "read it off the screen" rather than
quoting a number. **Keep the licence credit line under the drawing visible in every shot.**

Audience: Stoa's founding tech team and a construction engineer. Speak like a site engineer: takeoff, door schedule,
BoQ, as-built, RFI.

---

## 0:00 – 0:15 · The pain (splash screen)

**Show:** the splash with the per-source scoreboard.

**Say:**
> "A site engineer loses hours a day hunting through drawing sets for one number: how many WCs on level 3, the net
> area of apartment A, which door type goes in opening 118.C. General AI reads a drawing like a photo and guesses.
> PINPOINT reads the drawing like an engineer does, from the geometry in the file, and gives you a receipt for every
> answer."

**Point at:** Swiss floor plans 2358/2358, IFC models 1049/1049, US drawing sets 61/64, Finnish scans 3042/4270.
"Per source, never blended. Counts exact, quantities within 2 %, which is Stoa's own scoring."

## 0:15 – 0:45 · Ask box, receipt and citations (quantity takeoff)

**Do:** `Try it yourself` → Swiss plan `site1000_bldg2082_floor9385` → ask in German:
`Wie viele WCs sind auf diesem Grundriss eingezeichnet?`

**Say:**
> "Asked in German. Every WC is boxed and numbered on the real sheet. Step through them with the arrow keys. The receipt
> on the right says *how*: a bowl symbol with no drain circle is a WC; a washbasin has one. Each line cites the file,
> the DXF layer and the position on the sheet: click a line, the drawing zooms there."

**Point at:** the itemized receipt rows, the method line, `0 LLM calls` in the cost meter.

## 0:45 – 1:00 · The 2 % tolerance badge (area takeoff)

**Do:** same plan, ask: `What is the net floor area of apartment A in m², summing all its rooms except balconies,
loggias, terraces and other outdoor spaces?`

**Say:**
> "80.33 square metres against the reference 80.34: within 0.01 %, inside the 2 % limit. Every room in the sum is
> shaded and cited, and the balcony is listed as *excluded, with the reason*. That's a takeoff a QS can sign off."

**Point at:** the green tolerance badge, the "excluded" list, the cross-check (printed m² label vs room polygon).

## 1:00 – 1:25 · Drawing audit (catching real errors before the RFI)

**Do:** `⚠ Audit` (key `A`) → `★ Errors we found in the dataset` → Sports Complex door package.

**Say:**
> "Here PINPOINT catches mistakes in the drawings themselves. On this US drawing set the door schedule lists 41 doors, but the
> plans tag only 39: 118.C and 129.A have no tag. There's a door leaf drawn in the Fitness Center wall with no tag at
> all. And the current A-801 schedule drops 6 doors and adds 5 against the earlier plan issue. That's an RFI before
> the door supplier orders frames off the wrong revision."

**Optional second finding:** `fantasy_office_building_3_arc.ifc`: 4 RC columns modelled twice with identical
geometry, so the concrete volume in every takeoff is over-counted.

## 1:25 – 1:45 · Click-to-identify components (as-built check)

**Do:** `⌖ Identify` (key `I`) → click a door on the plan, then a wall in the IFC model.

**Say:**
> "Click any element and you get a site-ready card: what it is, its type, its size (clear opening, leaf, swing,
> wall thickness), its properties (fire rating, load-bearing, external), and the exact source: IFC GlobalId and STEP
> line, or DXF layer and entity handle. If the drawing doesn't contain a value, door height for example, the card
> says *missing*. It never fills one in."

**Point at:** on Swiss plans, the "drawn twice" flag (265 stacked duplicate door pairs across 61 of 65 plans) so a
takeoff counts the opening once.

## 1:45 – 2:05 · 2D ⇆ 3D and the walkthrough

**Do:** IFC plan `bsc-esplanades … 4-korrus` in split view (key `2`), ask in Estonian:
`Mitu ust on näidatud korruse „4.korrus“ plaanil?` → click a numbered door → then `🚶 Walk in 3D` (key `W`) on the
Swiss plan.

**Say:**
> "Estonian office floor, asked in Estonian. Click door 3 and the sheet and the BIM model fly to the same door by its
> GlobalId, with no fitting and no guessing. And any 2D plan becomes a building you can walk through; the counted
> elements glow. That's how you'd brief a crew before they go on site."

## 2:05 – 2:25 · Bill of quantities

**Do:** `Bill of quantities` (key `Q`) on the Swiss plan → hover a line → show CSV/PDF export.

**Say:**
> "One click: the whole floor's BoQ, with rooms, net areas, doors, windows and sanitary fixtures, every line traceable to
> the drawing and cross-checked against the dataset's own questions. Export to CSV or PDF and it goes straight into
> the estimate."

## 2:25 – 2:45 · Cost race against frontier models

**Do:** click the cost meter (key `R`).

**Say:**
> "Same 7,741 graded questions, two ways. A frontier vision model would cost about €170 at list price, and that's an
> estimate we label as one. PINPOINT measured €0.0013 of CPU for all of them, about two minutes on a laptop. That's
> roughly a hundred thousand times cheaper, and it's exact. No LLM is in the scored path. A small fine-tuned detector
> reads the scans, vector parsing reads the CAD, and a frontier model is optional and only ever rephrases the
> question."

## 2:45 – 3:00 · Guided tour + close

**Do:** `▶ Tour` (let it run in the background while closing; it plays count → area → 2D/3D → door schedule → walk →
BoQ → cost race, captions built from the live answers).

**Say:**
> "Every answer is correct *and* checkable in seconds: boxed on the drawing, cited to the entity, graded to Stoa's
> tolerance, and it flags where the drawings themselves are wrong. On unseen drawings from the full set: IFC 858 of
> 858, Swiss 892 of 898, zero crashes, zero silent failures. PINPOINT: every answer comes with a receipt."

---

### Backup facts (only if asked; all from `/api/eval_all` or README)

- Finnish scans: leak-free YOLOv8n trained only on the 213 CubiCasa5K plans not in the Stoa set; room-label OCR
  kitchens 70/75, bathrooms 55/60, saunas 48/77 (the weakest class).
- Swiss audit: all 550 printed room-area labels on the 65 Swiss plans agree with their outlines (±2 %).
- IFC audit: 16,484 elements and 263 spaces in 9 models fingerprinted; molio space 603 Qto 8.70 m² vs body
  footprint 10.08 m².
- Historic/archive scans (europeana, finna, habs, wikimedia): answered honestly with "can't answer, here's why",
  never a silent guess.

### Licence lines to keep on screen

- Swiss plans: *Swiss Dwellings v3.0.0, Archilyse AG, doi:10.5281/zenodo.7788422, CC BY 4.0. Drawing rendered by Stoa
  from the dataset geometry.*
- Finnish scans: *CubiCasa5K, © 2019 CubiCasa, Kalervo et al., SCIA 2019, CC BY-NC-SA 4.0. Non-commercial.*
- US sets: *OpeningDesign, CC BY-SA 4.0.* IFC models: per file (shown automatically under the 3D view).
