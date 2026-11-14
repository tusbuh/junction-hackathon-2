# VIDEO_LOG (track VIDEO, branch video, 2026-11-14)

Output: ~/junction-hackathon-2/shots_tmp/submission/video.mp4 (not uploaded anywhere)
- Duration: 165.0 s (2:45) · size: 19292781 bytes (~18 MB) · 1920x1080 · 30 fps · H.264 (crf 20) + AAC 160k, loudnorm −16 LUFS
- Voice: macOS **Samantha** (`say -v Samantha -r 182`). `say -v '?'` lists no Premium/Enhanced English voice on this machine; no xAI key.
- Also saved: video_frame1..4.png (WC count receipt, door-schedule audit, Estonian 2D⇆3D, cost race) and video_script.md.
- Source: the live app at :8737 (not restarted), recorded headless (installed Google Chrome via an existing playwright-core, no download). The user's screen was never recorded.
- Numbers: only from the app (/api/scoreboard, /api/race, answers on screen). End card fetched live: IFC 1,049/1,049 · Swiss 2,358/2,358 · CubiCasa5K 3,124/4,270 · €0.0024 measured vs €170.48 frontier VLM (est.) · ~72,135× cheaper.

## Scenes
| # | time | scene | what is shown |
|---|------|-------|---------------|
| 0 | 0:00 | title card | "PINPOINT: blueprints that show" |
| 1 | 0:04.5 | the pain / splash | per-source cards, cost strip, cursor tours the numbers |
| 2 | 0:23.5 | ask (German) | types "Wie viele WCs …", 4 WCs boxed, exact badge, steps WC 1–2, receipt rows |
| 3 | 0:43 | area takeoff | apartment A 80.33 vs 80.34 m², within 0.01 %, 9 rooms shaded, cross-check, per-room labels |
| 4 | 1:00 | drawing audit | Audit → Errors we found → Schedule ≠ plan: 118.C boxed on the schedule, 41 ≠ 39 doors |
| 5 | 1:20 | 2D ⇆ 3D (Estonian) | split view, 42 doors exact, door 3 synced in sheet and IFC model by GlobalId |
| 6 | 1:34.5 | walkthrough | Walk in 3D: glowing WCs in orbit, then "Walk inside" swoop into 2.05 Wohnen/Essen |
| 7 | 1:48 | bill of quantities | BoQ overlay, ground-truth badges, CSV/PDF buttons |
| 8 | 2:02 | cost race | animated race, €170.48 vs €0.0024, 72,135×, per-source table, scrolls to the estimate footnote |
| 9 | 2:23 | scoreboard | per-source bars, never blended |
| 10 | 2:37 | end card | real numbers from /api/scoreboard + /api/race, data licences |

Captions: 1–3 per scene in a 120 px band under the app (1920x960 viewport), 42 px bold white/amber, so captions never cover a drawing or the licence credit line under it.

## Glitch check
Every scene was checked from contact sheets (frame every 2.2–2.5 s) and full-res frames. Fixed during review: suggestion dropdown covering the plan while typing (s02/s05), walk scene ending on empty space after an orbit drag (mouse-look in walk mode; drag removed), item zoom too tight for the 2.2x raster sheet (wider fitBox), end-card label wrap, Estonian caption giving the answer before it was asked, late screencast frames after stop.

## Known flaws
- Samantha is a standard (non-neural) macOS voice: clear but somewhat synthetic.
- Zooming into a WC on the Swiss sheet shows the raster sheet's 2.2x resolution (slightly soft).
- Walk scene: the swoop into first person passes ~0.3 s through the roof slabs before landing in the room.
- Cost race: at 960 px the estimate footnote sits at the bottom edge; the scene scrolls down to show it, which pushes the race title off the top for the last ~3 s.
- In the audit scene the "41 ≠ 39" caption appears ~1 s before the receipt card with those numbers finishes loading.
- US drawing sets (61/64) are on the splash and scoreboard scenes but not on the end card (the brief asked for IFC, Swiss, CubiCasa, cost).
- The cursor occasionally rests on a badge it is pointing at.

Scripts committed in video/ (lib.mjs, record.mjs, cards.mjs, tts.sh, raw2mp4.sh, assemble.py, narration.json, scenes.json). Temp frames in /tmp/ppvid removed.

VIDEO_READY
