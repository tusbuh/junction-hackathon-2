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
