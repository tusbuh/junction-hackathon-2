# PINPOINT: plan to win (STOA only)
Deadline Sun 15 Nov 10:00 Helsinki. Judged 25% each on accuracy, verifiable visuals, creativity and low cost.

Rules: no eval data or test plan IDs in training. Credit the licences (CubiCasa CC BY-NC-SA, Swiss Dwellings CC BY). Nothing goes public or gets submitted without the user's OK.

Golden rules: run eval before every commit and never commit an accuracy drop. Commit and push after every block. Keep localhost:8737 working at all times. Keep the Terminal visible and the 5-minute watchdog running all night.

## Phase 1, 01:30-05:00, accuracy
1. The CubiCasa scanned plans are 53% of the questions. Download CubiCasa5K on the Mac. Convert its SVG labels to YOLO (door, window, WC, sink, bathtub, shower, sauna stove), holding out every Stoa plan ID. Train YOLOv8n on MPS. Use Tesseract fi+en OCR for room names and printed areas.
2. While it trains, fix the known misses: the shower rule, shafts/voids in floor totals, Molio stairs, and the room-name typo.
3. Unpack the full dataset and build an eval_all scoreboard per source and per question type, as JSON for the UI.

## Phase 2, 05:00-09:00, stunning receipt UI
- The drawing fills the screen and numbered glowing boxes animate in one by one. Clicking a number zooms to it.
- A receipt panel shows the answer, the method, the itemized list and a confidence colour.
- Cross-check badge: compare the printed label with the computed geometry, turn amber when they disagree, and show both. Find 2-3 real errors in the dataset drawings.
- IFC: a 3D view (three.js/web-ifc) with the counted elements highlighted, synced to the 2D plan.
- Questions in FI/DE/ET/DA get answered in the same language.

## Phase 3, 09:00-15:00, creativity and cost
- Live cost meter.
- A race page: PINPOINT vs a frontier vision model on 200 questions, comparing accuracy, € and seconds. Cap spend at about €5.
- An Export receipt PDF button.
- Send low-confidence raster crops to a small VLM and flag them.

## Phase 4, 15:00-23:00, harden
- Fix the top failure categories and get every answer under 1 s.
- README with numbers, screenshots, architecture and licences.

## Phase 5, Sun 06:00-09:45, ship
- 06:00 feature freeze, plus a 60-90 s demo script (Finnish question, boxes light up, 3D view, error caught, race, cost).
- 07:00 record a 2-min video.
- 08:00 draft the submission text for the user to review.
- The user submits by 09:45. Never submit for them.

## Night orders (Sat 14 Nov 01:14)
Three parallel Claudes, each in its own git worktree and branch:
- UI (~/jh2-ui, branch ui): dramatic redesign: 2D drawing view with counted items and numbered glowing boxes that animate in, click to zoom, clean layout, 3D model view (three.js/web-ifc) synced to plan.
- ACCURACY (~/jh2-acc, branch accuracy): CubiCasa YOLOv8n on MPS, Tesseract fi+en OCR, fix known misses, eval_all scoreboard.
- CITATIONS (~/jh2-cite, branch citations): every answer cites where on the drawing it came from: receipt panel + cross-check badges (amber on disagreement).
main stays at localhost:8737 (tracks test on 8738-8740). A track merges to main only after eval passes with no accuracy drop: rebase on main, eval, merge, push. Tracks resolve their own conflicts. From Sun 06:00 feature freeze: bug fixes and polish only.
