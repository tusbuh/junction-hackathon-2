# DESIGN3 log: two original looks, A and B (branch design3, NOT merged)

Test server: `~/jh2-design3`, port 8765 (`PORT=8765 .venv/bin/python -m pinpoint.server`).
How to view: `http://localhost:8765/?theme=a` or `?theme=b`. Both work with `?static=1` (e.g. `?static=1&theme=a`).
With no `theme` parameter the app looks exactly as before (checked against a screenshot taken before any change).

## What changed (presentation only)
- `static/theme.js` (new, loaded in `<head>`): reads `?theme=a|b`, adds `html.themed.theme-a|b`, loads
  `static/fonts/fonts.css` plus `static/theme-a.css` or `static/theme-b.css`, and keeps the theme stylesheet last
  in `<head>` even when feature scripts add theirs later (wow.css, audit.css, race.css). In themed mode it also drops
  the pictogram prefix from button labels; the words stay the same ("🚶 Walk in 3D" becomes "Walk in 3D").
- `static/app.js`: one line. Vector sheets open on a light canvas when a theme is active
  (`blue: !themed`). The blueprint toggle still works. Without a theme, behaviour is unchanged.
- `static/index.html`: one `<script src="/static/theme.js">` line.
- `DEMO_SCRIPT.md`: a two-line note about the optional looks and the button labels without pictograms.
- No route, endpoint, number, feature or licence credit changed. The credit strip still shows under every drawing
  (Swiss CC BY 4.0, CubiCasa5K CC BY-NC-SA 4.0, IFC per file); I checked it on Swiss, CubiCasa and the BoQ view.

## Fonts (self-hosted, latin subset, 236 KB of woff2 in total, licence next to each file in static/fonts/)
- Archivo (variable weight and width): SIL Open Font Licence 1.1, `Archivo-OFL.txt`
- Bricolage Grotesque (variable): SIL OFL 1.1, `BricolageGrotesque-OFL.txt`
- Instrument Serif (regular + italic): SIL OFL 1.1, `InstrumentSerif-OFL.txt`
- JetBrains Mono (variable): SIL OFL 1.1, `JetBrainsMono-OFL.txt`

## Theme A: "Night Shift" (dark blueprint)
1. Deep ink-navy drafting table with a fine blueprint grid. The drawing sits on it as a white paper sheet, so it stays easy to read.
2. One safety-orange accent for the primary action and the highlights. Red pen marks only the selected item. No gradients, glows or blur.
3. Archivo for words (extra-wide tracked caps for labels and the wordmark), JetBrains Mono ExtraBold for big numbers.
4. Signature details: crop marks on card corners, dimension lines with end ticks under every big number, and an orange marker loop around "72,135×".
5. Buttons: solid orange primary with an inset bevel and a pressed state, white-outline secondary, underlined ghost; flat 6 px corners and an orange focus ring.

## Theme B: "Red Pen" (light editorial)
1. Warm drawing paper, black ink, 2 px rules like a newspaper masthead; the receipt reads like a printed ledger.
2. Huge Instrument Serif headline: the first line upright in ink, the second in red italic. Bricolage Grotesque for the UI, JetBrains Mono for numbers.
3. Highlights are a reviewer's red pen: numbered red circles on the drawing and in the receipt. The selected item gets highlighter yellow.
4. A red hand-drawn underline under the answer, wavy red underlines on the two sources that are not yet at 100%, and a red loop around "72,135×".
5. Buttons feel like keys: a 1.5 px ink border with a solid ink "key" shadow that lifts on hover and presses flat; red primary, paper secondary, underlined ghost.

## Screenshots (headless Chrome, 1440x900)
- ~/junction-hackathon-2/shots_tmp/design3/a_splash.png (`?static=1&theme=a`)
- ~/junction-hackathon-2/shots_tmp/design3/a_main.png (`?static=1&theme=a&q=How many doors are there?`: drawing, answer card, receipt)
- ~/junction-hackathon-2/shots_tmp/design3/b_splash.png
- ~/junction-hackathon-2/shots_tmp/design3/b_main.png
I also checked in both themes: scoreboard, cost race, CubiCasa raster with low-confidence flags, BoQ, 3D walk-through,
Identify, and the blueprint toggle.

## Eval (full run, written to /tmp/design3/eval, not to shared data/eval)
- swiss_dwellings 2358/2358 = 100.0%
- ifc_models 1049/1049 = 100.0%
- opening_design 61/64 = 95.3%
- cubicasa5k 3124/4270 = 73.2%
- /api/eval_all (dev split) and /api/scoreboard on :8765 agree for all four sources.
Disk: 3.6 GB free throughout. No training and no large files.

## Status
Code head: 7d125d4 (this log is committed after it). Pushed to origin/design3. NOT merged into main: the user picks A or B first.
To adopt one later, keep theme.js and make the chosen theme the default, or fold its CSS into style.css.

DESIGN3_READY
