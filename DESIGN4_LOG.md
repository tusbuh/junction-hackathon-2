# DESIGN4 log: ?theme=pro (corporate, minimal, light)

Branch `design4`, folder ~/jh2-design4, served on :8766 only. NOT merged into main; the user approves first.

## How to view
- http://localhost:8766/?theme=pro and http://localhost:8766/?static=1&theme=pro
- No theme param = the current look, unchanged (checked with a screenshot: same dark/amber UI, no console errors).

## What changed
- `static/theme.js` (new): reads `?theme=pro` and adds `html.themed.theme-pro`. It loads `static/fonts/fonts.css` and `static/theme-pro.css` and keeps the theme stylesheet last in `<head>`. It also strips pictogram prefixes from button labels (the words stay the same) and swaps the dock and stepper glyphs for clean SVG icons.
- Tools menu: Walk in 3D (W), BoQ (Q), Identify (I), Audit (A), Scores and Cost race (R) move into one "Tools" dropdown. They are the same buttons with the same ids, handlers and shortcuts. Each item has a one-line description and its key. An amber dot on Tools shows when the drawing has audit findings. The header keeps the drawing picker, the Ask field (the one primary action), the cost meter, Tour and Tools.
- `static/theme-pro.css` (new): white surfaces and a neutral grey scale, with one deep-blue accent (#1f4fd6). Spacing is on a 4/8 px scale, borders are 1 px, shadows are calm, transitions take 160 ms and focus rings are visible. Highlights on drawings use the accent; the selected item turns near-black with a blue ring. Restyled surfaces: splash, answer card, receipt, evidence, drawing audit, drawer, scoreboard, cost race, BoQ, walkthrough chrome, identify panels and tour captions. Edges line up at 20 px up to 1679 px wide and 24 px from 1680 px. The receipt column is 360 px wide (400 px from 1680 px).
- `static/app.js` / `static/walk.js`: small `PRO` switches, active only with the theme. Sheets open on white paper. The 3D fog, grid and highlight colours follow the accent. The walkthrough uses a daylight scene with bloom off and accent highlights.
- `static/index.html`: one `<script src="/static/theme.js">` line.
- DEMO_SCRIPT.md is unchanged. No visible label changed; in pro mode the secondary buttons live under Tools.

## Fonts (self-hosted, latin subset, 56 KB total)
- Geist (variable 400–700), `static/fonts/geist-latin.woff2`, SIL Open Font License 1.1, `static/fonts/OFL-Geist.txt`
- Geist Mono (variable 400–600), `static/fonts/geist-mono-latin.woff2`, SIL Open Font License 1.1, `static/fonts/OFL-GeistMono.txt`

## Screenshots (headless Chrome)
- ~/junction-hackathon-2/shots_tmp/design4/splash.png (1440x900, ?static=1&theme=pro)
- ~/junction-hackathon-2/shots_tmp/design4/main.png (1440x900, drawing loaded, answer + receipt)
- ~/junction-hackathon-2/shots_tmp/design4/main_1920.png (1920x1080)
- Also reviewed at 1280x800 and 1920x1080, plus every overlay: Tools menu, scoreboard, drawer, cost race, BoQ, audit showcase, identify, walk, 2D/3D split, CubiCasa scan, US schedule and tour caption. The licence credit shows under every drawing.

## Eval (full run, written to /tmp/design4/eval, not to shared data/eval)
- swiss_dwellings 2358/2358 = 100.0%
- ifc_models 1049/1049 = 100.0%
- opening_design 61/64 = 95.3%
- cubicasa5k 3124/4270 = 73.2%
- /api/eval_all (dev split) and /api/scoreboard on :8766 agree for all four sources.
- Disk: 3.9 GB free at eval start, 6.5 GB at the end. No training, no large files.

## Summary
1. New opt-in light theme `?theme=pro`: white, grey, one deep-blue accent, Geist + Geist Mono.
2. One primary action per view (Ask; on the splash, the guided tour). Secondary features sit in a Tools menu with shortcuts.
3. Big numbers are calm and confident: sans for display figures, mono for data. Highlights on drawings stay clearly visible in blue.
4. Every feature, route, shortcut, number and drawing credit is unchanged and reachable; the default look is untouched.
5. Eval is unchanged on all four sources. Branch pushed, not merged.

## Status
Code head: 40bc0e6 (this log is committed after it). Pushed to origin/design4. NOT merged into main.

DESIGN4_READY
