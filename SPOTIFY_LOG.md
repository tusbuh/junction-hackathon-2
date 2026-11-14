# SPOTIFY track log (branch `spotify`, ~/jh2-spotify) — NOT merged to main, waiting for the user's approval of the look

## Notes
- Port 8744 was already taken by another track's server (jh2-wow2, pid 79118, started 07:00). I did not touch it.
  All testing ran on **:8764** instead (`PORT=8764 .venv/bin/python -m pinpoint.server`).
- Screenshots: headless Chrome 1440x900 driven over CDP (script in /tmp only), `?static=1`.
  Main view = `?static=1&q=How many apartments (residential units) are shown on this floor plan?` (Swiss site1000 plan, answer + receipt).
- Disk: 4.9 GB free at start, 4.2 GB at the low point (my Chrome temp profiles, deleted → 4.5 GB). No training, no downloads.
- The eval ran with `PINPOINT_EVAL_OUT=/tmp/spotify_eval` so the shared data/eval files were not overwritten.

## What changed (style only; every route, number and feature unchanged)
- New `static/spotify.css` (loaded last; `static/shell.js` keeps it after the sheets that other scripts inject) and `static/shell.js` (sidebar + player bar wiring; it only clicks existing buttons and reads `window.PP.S`).
- Layout: left sidebar (Ask, Audit, Identify, 3D walkthrough, BoQ, Cost race, Tour, Scores + "Your library" with one row per source),
  pill search/ask bar at the top, and a bottom player bar: current drawing + answer status on the left, ‹ / play-tour / › with an
  item progress bar in the middle, cost meter on the right.
- Colours: #000 frame, #121212 panels, #181818 cards, #282828 hover, one green accent #1DB954 (primary buttons, highlights, evidence),
  white / #B3B3B3 text. Removed: Inter / JetBrains Mono Google fonts, gradient text, glows, glass blur, emoji on buttons.
- Type: system sans (-apple-system, Helvetica Neue, Helvetica, Arial) for words, ui-monospace / SF Mono / Menlo for numbers.
- Drawings now default to the light "paper" canvas inside dark cards (◐ still toggles blueprint); evidence boxes, number pills, 3D
  highlights, BoQ and Identify highlights are green.
- Licence credit under every drawing kept (CC BY 4.0 / CC BY-NC-SA 4.0 / per-file IFC); `?static=1` still shows final numbers.
- DEMO_SCRIPT.md: button labels updated (sidebar / player bar, no emoji).

## Commits
d1d3fb8 shell + theme · df4ffa7 overlays (audit order fix, scoreboard, BoQ, walk/identify) · 27c1c77 DEMO_SCRIPT labels · 967378a tagline wrap

## Eval (full `python -m pinpoint.evaluate`, unchanged)
- ifc_models 1049/1049 · swiss_dwellings 2358/2358 · opening_design 61/64 · cubicasa5k 3124/4270
- `/api/eval_all` dev split = `/api/scoreboard` for all four sources (same numbers as above).

SPOTIFY_READY
- branch head: spotify @ 967378a (code); this log is committed on top of it (see `git log -1 spotify`)
- screenshots:
  - ~/junction-hackathon-2/shots_tmp/spotify/before_splash.png
  - ~/junction-hackathon-2/shots_tmp/spotify/before_main.png
  - ~/junction-hackathon-2/shots_tmp/spotify/after_splash.png
  - ~/junction-hackathon-2/shots_tmp/spotify/after_main.png
- summary:
  1. Whole UI restyled like a dark music-player web app: near-black panels, one green accent, pill buttons, bold system sans, mono numbers.
  2. New left sidebar (8 features + library of sources) and bottom player bar (drawing, answer status, item stepper, tour play button, cost meter).
  3. AI look removed: no web fonts, gradients, glows, blur or emoji buttons; drawings shown on light paper with green highlights.
  4. Every feature, route, number, licence credit and ?static=1 kept; DEMO_SCRIPT labels updated.
  5. Not merged to main: waiting for the user's approval.
- eval: IFC 1049/1049, Swiss 2358/2358, opening_design 61/64, cubicasa5k 3124/4270; /api/eval_all matches /api/scoreboard.
