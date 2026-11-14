# HUMAN log (2026-11-14)

Goal: make the demo read as a product a Stoa engineer would ship, not an AI-made template. Look and copy only.
Every feature, route and number is unchanged. **Not merged into main** (waiting for the user's approval of the look).

## Process notes
- Test server: **port 8745, not 8743.** :8743 was already held by the old jh2-cite2 server (PID 73524, started 06:36).
  I did not kill it (rule: never kill other processes). My own server ran from ~/jh2-human on :8745.
- Screenshots: headless Chrome over CDP at 1440×900 (script in /tmp only). BEFORE shots were taken from this
  worktree at main 182a1e6, before any change.
- Disk: free space dipped to 3.4 GB after the eval and screenshot runs (other tracks write to the same disk). I deleted
  only my own temp files (headless Chrome profiles, ~334 MB, and the draft PNGs), which brought it back to 3.7 GB. No
  training, downloads or new image sets.

## What changed (static/ only, plus two small server-side strings and one precaution)
- **Palette and type.** Paper white, light grey and near-black ink (#17191c), with ONE accent: drafting orange #c2410c,
  used for evidence on the drawing, selection and the cost ratio. Status colours are muted: green #2e6b45, red #b3261e,
  amber #9a5b00. Text uses the system sans (-apple-system); every number uses ui-monospace / SF Mono / Menlo. The
  Google Fonts link (Inter, JetBrains Mono) is gone, so no fonts are downloaded.
- **Removed:** all gradients (buttons, headline text, panels, bars), glows (drop-shadow, text-shadow, box-shadow
  halos), backdrop blur and glassmorphism, the spinning glowing logo, the bloom pass in the 3D walk-through
  (`V.bloom.enabled = false`), additive "neon" highlight blending, pulsing emissive 3D highlights, bouncy pop-in
  animations, and all emoji / pictogram icons (🚶 🚪 🪟 🚽 🚿 🛁 ⚠ ★ ▶ ▦ ▤ ⌖ ⬇ ⧉ ↻).
  Identify now uses drawing abbreviations: DR, WN, WL, SAN, WC, WB, SH, BT, SP, COL, BM, ST, RL, RF.
- **Linework.** 1 px ink rules, 2 px or square corners, ruled lists instead of rounded cards. The answer card and the
  receipt read like a title block or a checked calculation sheet. Numbered evidence tags are small boxed tags like
  drawing callouts, not glowing pills. Sheets open on **paper** (white drawing, black ink) instead of the inverted
  blueprint; the ◐ dock toggle still switches to blueprint. The 3D view and the walk-through use a light grey scene.
- **Badges.** The answer card keeps only badges with information in them: the **2 % tolerance / exact** badge, the
  ground-truth ✓/✗ fallback, cross-checks and low-confidence counts. The "● confidence" badge (already at the top of the
  receipt) and the "N cited · 0 LLM" badge (count is in the evidence header, LLM calls in the meter) are dropped.
- **Copy.** Splash headline was "Ask a blueprint anything. Check the answer in seconds." It is now "Counts, areas and
  schedule rows, read from the drawing file and marked on the sheet.", with a plain lead naming DXF / PDF / IFC, the door
  schedule and the receipt. The splash is laid out as a cover sheet (header strip, four per-source columns, cost strip).
  Buttons: "Guided tour", "Cost race", "Open the drawing". Header buttons: Walk in 3D, BoQ, Audit, Identify, Tour,
  Scores. Meter labels: cost / time / LLM calls / VLM est. / cheaper (compare). "INSTANT BILL OF QUANTITIES" is now
  "BILL OF QUANTITIES". The receipt's "Check the amber items" is now "Check the flagged items" (receipt.js +
  cite.py text).
- **Credits are kept** under every drawing: 2D, 3D, BoQ and walk-through, with the licence tag first (CubiCasa5K
  CC BY-NC-SA 4.0, Swiss Dwellings CC BY 4.0, IFC per file). `?static=1` still shows final numbers instantly; checked
  on the splash.
- **DEMO_SCRIPT.md:** only the visible labels changed. Header button names no longer have emoji prefixes; "★ Errors we
  found" is now "Errors we found"; "Try it yourself" is now "Open the drawing"; "green cost strip / tolerance badge /
  amber" wording is now neutral; "counted elements glow" is now "are highlighted".
- **Precaution (separate commit 58d3a06, safe to drop):** pinpoint/swiss.py parses one ezdxf entity query at import.
  Once, after a cold restart of my :8745 server, every Swiss ask returned
  `TypeError: <lambda>() missing 1 required positional argument: 't'` from ezdxf's query parser (pyparsing 3.3.3). The
  venv had not changed since last night, and three cold-start trials with concurrent ask / parts / audit / walk / boq
  calls did not reproduce it. My unconfirmed guess is a pyparsing arity-detection race between request threads. The
  warm-up changes no result. Note that the main :8737 server could hit the same thing on a cold start.

Views checked after the change (1440×900): splash, main 2D answer + receipt, IFC 2D+3D split, cost race, BoQ, 3D walk,
audit showcase, identify parts list, scoreboard, drawing picker, CubiCasa raster with a low-confidence item, tour caption.

One side observation, not changed: the live per-answer cost meter varies run to run because it is measured CPU time
(e.g. Zimmer count €0.00000012 / 307,192× before, €0.0000000094 / 3,911× after a fresh restart). The splash, race and
scoreboard totals come from data/eval and are unchanged.

## Eval
`PINPOINT_EVAL_OUT=/tmp/human_eval python -m pinpoint.evaluate` (full preview set, written to /tmp, so the shared
data/eval was not touched):

| source | result |
|---|---|
| ifc_models | 1049 / 1049 |
| swiss_dwellings | 2358 / 2358 |
| opening_design | 61 / 64 |
| cubicasa5k | 3124 / 4270 |

On :8745, `/api/eval_all` dev split = `/api/scoreboard`: cubicasa5k 3124/4270, ifc_models 1049/1049,
opening_design 61/64, swiss_dwellings 2358/2358. Every number is unchanged.

HUMAN_READY
- branch `human`, code head **58d3a06** (58d3a06fa31263dc7296c41a12e208c72c00c122). The only commit after it adds this
  log. Pushed to origin/human. NOT merged into main.
- screenshots:
  - ~/junction-hackathon-2/shots_tmp/human/before_splash.png
  - ~/junction-hackathon-2/shots_tmp/human/before_main.png
  - ~/junction-hackathon-2/shots_tmp/human/after_splash.png
  - ~/junction-hackathon-2/shots_tmp/human/after_main.png
- summary:
  1. Dark neon theme replaced by paper / light grey / ink with one orange accent; system sans for text, monospace for every number; no web fonts.
  2. Gradients, glows, blur, glassmorphism, 3D bloom, pulsing highlights and every emoji or pictogram icon removed; square corners and 1 px rules throughout.
  3. Answer card, receipt, BoQ, audit and scoreboard restyled as ruled title blocks and schedules; evidence numbers are boxed callout tags; sheets open on white paper.
  4. Badge clutter cut to the badges that carry information (2 % tolerance / exact, checks); licence credits kept under every drawing; ?static=1 still works.
  5. Copy rewritten in plain site-engineer terms (splash headline and lead, buttons, meter, BoQ title); DEMO_SCRIPT labels updated to match.
- eval: IFC 1049/1049, Swiss 2358/2358, opening_design 61/64, cubicasa5k 3124/4270; /api/eval_all = /api/scoreboard.
