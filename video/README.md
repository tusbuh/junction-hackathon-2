# Demo video pipeline

Records the real PINPOINT app (default `http://localhost:8737`, override with `PP_BASE`) in headless Google Chrome
via playwright-core (`PW_CORE` = path to an existing playwright-core `index.mjs`; no browser download).

1. `./tts.sh` — narration.json → `/tmp/ppvid/audio/<scene>.wav` with macOS `say` (+ durations.txt)
2. `node cards.mjs` — caption bands (1920x120) + title/end cards; end-card numbers fetched live from /api/scoreboard and /api/race
3. `node record.mjs [scene ...]` — each app scene in a 1920x960 viewport (drawn eased cursor, CDP screencast, then a
   30 fps intermediate in /tmp/ppvid/rec; raw frames deleted). Scene length = max(minT, narration + 1.5 s).
4. `./assemble.py [out.mp4]` — app (960 px) + caption band (120 px) + narration → per-scene clips → one H.264/AAC MP4.

scenes.json holds per-scene minimum length and caption timings; record.mjs the cursor choreography.
