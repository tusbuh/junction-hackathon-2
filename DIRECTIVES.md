# THE BAR (user, Sat 01:56): AMAZING, not just good enough to win
- Accuracy: as close to 100% as possible on EVERY source, Finnish scans included.
- Visuals: something judges remember.
- Creativity: something no other team has (e.g. catching real errors in drawings).
- Cost: show the gap with frontier models vividly.

# CHALLENGE RULES (user, Sat 01:55; from the dataset README and challenge page)
1. Strict scoring: counts must be EXACT; area/length/volume must be within 2%; text is free-form. Grade our eval exactly this way, and show the tolerance on the receipt (e.g. "80.33 vs 80.34 m2, within 0.01%").
2. The data is for non-commercial Junction use only. Each file's licence and credit is in data/<source>/LICENSE.md. Show the credit UNDER EVERY DRAWING displayed in the demo, in screenshots and in the video.
3. CubiCasa is CC BY-NC-SA: adaptations keep the same licence. ND files stay unchanged (show them as-is with overlays only, no edited copies). Questions inherit their drawing's licence. Add a LICENSES section to the README.
4. Pitch: Stoa calls this one of the hardest unsolved problems in construction tech. General AI fails on complex drawings, and site engineers lose hours a day hunting for information. Speak to that pain.
5. The judges are Stoa's founding tech team plus a construction engineer, so use real construction terms and a workflow a site engineer finds credible.
6. The full set has ~14k drawings in ~30 languages (PDF/DWG/DXF/IFC/SVG/PNG/JPEG) and ~120k questions. Types: count, area, length, volume, text, other. Handle "other" gracefully.
7. The same name with a different extension is the same drawing in another format: use the best format (vector over raster). ifc_models plan PDFs are rendered from <model>.ifc, so link them.

# DIRECTIVES FROM THE USER (Sat 01:48) - read before every step
Good is not enough: keep getting better all night in visuals, accuracy and overall impressiveness.

Priority order:
1. CUBICASA RASTER (4,270 questions, 53% of preview) is missing from the scoreboard and is the #1 hole. Train and evaluate the detector, add OCR for room labels and areas plus a scale estimate, then put cubicasa on the scoreboard. (Accuracy track.)
2. FULL DATASET robustness: on a sample of the full set (~14k drawings, ~30 languages, historic scans), every file and question must return an answer with evidence, or an honest "can't answer, here's why". Never crash, never guess silently.
3. Hybrid story the brief asks for: show the fine-tuned detector plus a cheap VLM verifier used only on low-confidence raster crops, labelled as such in the receipt.
4. opening_design is 40/57 and text questions are 0/9: fix the schedule/text questions.
5. Merge the accuracy branch's 100% Swiss once eval passes (main shows 2338/2358 Swiss, 1025/1049 IFC).
6. Hero stat: honest per-source numbers from the eval JSON, not a blended 40.9%.
7. Cost race visual: VLM baseline (about EUR 52 for Swiss) vs us (about EUR 0.00006), shown big and clear.
Golden rules: eval before every merge, no accuracy drops, no invented numbers, never publish or submit.

# TRACK OWNERSHIP (Sat 02:00, avoid GPU/disk fights)
- RASTER (~/jh2-raster) ALONE owns CubiCasa detector training and writes to data/cubicasa_train. Only ONE YOLO training may run on the Mac at a time.
- ACCURACY (~/jh2-acc) must NOT train YOLO or write data/cubicasa_train. It does Finnish OCR, area/scale and room-label work for CubiCasa on its own branch, plus Swiss/IFC/opening_design/text, all feeding the same eval_all scoreboard.
