# STATIC track log: publishable static build of the PINPOINT demo (NOT published)

Nothing was published. No deploy, no Netlify login, no new repo, no push to any new remote. Branch `static` was
pushed to the existing private `origin` only. Not merged to main.

## Disk incident (16:47)

Right after the first export run, `df -h /` showed **3.1 GiB free** (it was 4.9 GiB at the start). That is under the
3.5 GB limit, so I stopped, logged it and committed (b12f23d). This track had written only ~39 MB (site/ 38 MB plus
~1 MB of sheet SVGs in the shared data/cache), so the drop came from another process. A minute later free disk was back at
4.7 GiB, and I resumed. Free disk at the end: 6.4 GiB. Downloads by this track: none (only `npm view` metadata).

## What was built

- `site/` (38 MB, 181 files) is a fully static export: `index.html`, `static/` (front end), `pp-data/` (recorded answers),
  `LICENSES.md` + `LICENSES.html`, `netlify.toml`, `.nojekyll`.
- `~/junction-hackathon-2/shots_tmp/submission/site.zip` (33 MB): the same folder, zipped.
- Screenshots at 1440x900: `shots_tmp/submission/static_splash.png` and `static_main.png` (German WC question,
  4 found = 4 ground truth, credit line visible).
- Rebuild: `.venv/bin/python tools/build_static.py` (about 5 min). `--front` re-copies only the front end and licences.

How it works: `tools/build_static.py` calls the real app in-process (FastAPI TestClient on `pinpoint.server`) and stores
every response it needs. `tools/offline.js` (copied to `site/static/offline.js`) answers the app's `/api/*` calls from
those files: `fetch`, `<img src>` and `<a href>` (BoQ CSV/PDF downloads keep the app's file name). Large JSON and the 3D
meshes are gzip files, decoded in the browser with `DecompressionStream`. All paths are relative, so the site also works
under a sub-path (GitHub Pages). The site always opens in the `?static=1` mode (final numbers, no count-ups); `?anim=1`
brings the animations back. **No number is typed in. Every value is a recorded response of the app**: scoreboard and
race come from `data/eval/*.json` through `/api/scoreboard` and `/api/race`, e.g. 2,358/2,358 Swiss, 1,049/1,049 IFC,
61/64 US, 3,124/4,270 CubiCasa, €0.0024 vs €170.48, 72,135×.

Recorded: 1,262 answers (every dataset question on the 13 drawings), about 14k element cards (component identification),
BoQ + verify + CSV + PDF, walkthrough geometry plus the highlighted answer for each Swiss question, IFC meshes (main view
and walkthrough), per-drawing audits, the audit showcase, scoreboard and cost race.

## Included drawings and licences (each checked in data/<source>/LICENSE.md)

| drawing | licence |
|---|---|
| swiss_dwellings site1000_bldg2082_floor9385, site1088_bldg2216_floor10132, site1102_bldg2242_floor10281, site421_bldg1097_floor4796 | CC BY 4.0 (Swiss Dwellings v3.0.0, Archilyse AG) |
| ifc_models bsc-esplanades_1807-ep-ar-v18 (.ifc + 4.korrus plan) | CC BY 4.0 (Esplan via buildingSMART) |
| ifc_models bsc-molio_molio-with-uris (.ifc + kælder plan) | CC BY 4.0 (Molio Demo-hus via buildingSMART) |
| ifc_models kit-fzk-haus_ac20-fzk-haus_plan-02-dachgeschoss (plan only) | KIT "for unrestricted use" (IAI/KIT) |
| ifc_bench fantasy_office_building_3_arc.ifc | MIT (c) 2025 TUM Students, BIM Fundamentals SS2025 (MIT text in LICENSES.md) |
| ifc_bench ac20_arc.ifc | KIT "for unrestricted use" (IAI/KIT) |
| cubicasa5k colorful-11397.png, colorful-11400.png (2 examples) | CC BY-NC-SA 4.0 (non-commercial, attribution, same licence; derived overlays and answers are under the same licence) |

Excluded: opening_design US drawing sets (CC BY-SA 4.0/MIT, but outside the "Swiss + IFC" scope you set; can be added
if you approve), the CC BY-ND IFC models (duplex, clinic), GPL hitos, digital_hub (size), all other CubiCasa plans,
HABS/Finna/Europeana/Wikimedia, anything from data/full, all eval files. Checked: no excluded file name or image is in
pp-data. The only "opening_design" strings are the per-source aggregate rows of the scoreboard and the race. The race
question ticker is filtered to questions about the included drawings. The credit line is shown under every drawing (2D
and 3D) from the recorded `/api/credit`, and site/LICENSES.md lists every drawing with source, licence and credit.

## What works offline (tested in headless Chrome against `python3 -m http.server 8767`, no backend)

- Splash with per-source cards and cost strip; ask box with every dataset question for each drawing (suggestion chips);
  receipts, boxes, stepper, tolerance badge (82.09 vs 82.09 m² apartment C, with loggia/balcony listed under Excluded).
- 2D ⇆ 3D split on the Esplanades plan (42 doors, GlobalId sync), Molio (119 doors), AC20 and Fantasy Office 3D.
- Audit (A): per-drawing audit and the "Errors we found" showcase (Fantasy Office duplicate columns in 3D, Molio Qto vs
  body). Identify (I): clicking a door on a Swiss sheet gives its card; IFC elements by GlobalId; the parts list.
- Walk in 3D (W) with the WC tour, BoQ (Q) with CSV/PDF download, cost race (R), scoreboard, "grade every question"
  (34/34 on site1000), and the guided tour (6 of 7 scenes play).

Doesn't work / limits:
- Only precomputed questions. A free-typed question returns an honest "not in the static demo" receipt.
- Tour scene 4 (A-801 door schedule) and the DEMO_SCRIPT audit beat on the Sports Complex door package are
  skipped, because opening_design is not included. The audit beat can use the IFC duplicate-column finding instead.
- Identify: printed-text lookup on IFC plan PDFs and free 3D points without an element need the live server. Swiss
  sheet clicks use a client-side point-in-polygon pick, not the server's DXF-metre hit test, so a click on a boundary
  can pick a different neighbour than the live app would.
- The FZK-Haus plan has no 3D model (its .ifc is not in the preview split), so it opens 2D only.
- Inter/JetBrains Mono load from Google Fonts. Without internet the browser falls back to system fonts; everything else is local.

## Deploy steps (not done; your approval and login are needed)

npx works with no global install: node v26.0.0 meets netlify-cli 27.19.0's `engines.node >=22.13.0`, and the package
has `netlify`/`ntl` bins. I checked only the npm metadata. I did not run it, because the first `npx` run downloads the
CLI's whole dependency tree into ~/.npm/_npx (my estimate: well over 100 MB, which risks the 300 MB cap). No `NETLIFY_AUTH_TOKEN` is set
and there is no ~/.netlify.

Netlify (CLI):
1. Log in, one of:
   - `npx -y netlify-cli login` opens a browser for OAuth and stores the token locally; or
   - create a personal access token at app.netlify.com → User settings → Applications → Personal access tokens and
     `export NETLIFY_AUTH_TOKEN=...` (no browser).
2. `cd ~/jh2-static/site && npx -y netlify-cli deploy --dir . --prod`. On the first run it asks to link or create a site
   (interactive). Non-interactively: `npx -y netlify-cli sites:create --name <name>`, then
   `npx -y netlify-cli deploy --dir . --prod --site <site-id>`.
   No build step is needed: `netlify.toml` publishes the folder as-is.
Netlify (no CLI): log in at app.netlify.com and drag `site/` (or unzip site.zip and drag the folder) onto
app.netlify.com/drop.

GitHub Pages alternative (needs a public repo, because Pages on a private repo needs a paid plan): create a new public repo
that contains only the contents of `site/` (never this repo, which has data/eval and the dataset paths), push it,
then Settings → Pages → Deploy from branch `main` / root. `.nojekyll` is included so every file is served as-is.
Relative paths make it work under `https://<user>.github.io/<repo>/`. The URL would be public. CubiCasa (NC-SA) and
attribution terms still apply.

STATIC_READY


## DESIGN4 static rebuild (Sunday 15 Nov 2026, about 03:00 Helsinki / UTC+2)

Nothing was published. No deploy, no Netlify, no visibility change. `site/` and `shots_tmp/submission/site.zip` were left untouched.

- Merged main `456b6ab` into branch `static` in `~/jh2-static` (pro theme is the default; `?theme=classic` keeps the old look).
- Rebuilt only the front end into a new folder `~/jh2-static/site_design4/` with `tools/build_static.py --front --out site_design4`, after copying `site/` so the recorded `pp-data/` stayed the same (`diff -q` reported the two `pp-data` folders identical). The drawing and licence filter is unchanged (13 drawings). Credit under every drawing, `LICENSES.md` / `LICENSES.html`, `netlify.toml` and `.nojekyll` are included. Geist and Geist Mono are self-hosted from `static/fonts/` (OFL 1.1 texts included); `fonts.css` paths were rewritten so they work offline.
- Served with `python3 -m http.server 8769 --bind 127.0.0.1` from `site_design4/`. Headless Chrome at 1440×900 confirmed the pro look (`html.theme-pro`), the splash scoreboard (2,358 / 2,358 Swiss, 1,049 / 1,049 IFC, 61 / 64 US, 3,124 / 4,270 CubiCasa, €0.0024 vs an estimated €170, about 72,135× cheaper), and the German WC question on `site1000_bldg2082_floor9385` (4 found = 4 ground truth) with the Swiss Dwellings CC-BY-4.0 credit line visible. Then only the :8769 server was stopped. The demo on :8737 was not touched.
- Zip: `~/junction-hackathon-2/shots_tmp/submission/site_design4.zip` (33,298,113 bytes; 188 files, contents at the zip root). Screenshots: `shots_tmp/submission/static4_splash.png` and `static4_main.png`. Copies also at `/workspace/stoa/submission/` on the box. Old `site.zip` left as it was (33,226,514 bytes, 14 Nov 16:54).
- Folder on disk: `site_design4/` is 38 MB, 188 files (the previous `site/` had 181 files; the 7 added files are the Geist fonts, their OFL texts, `fonts.css`, `theme.js` and `theme-pro.css`).

Limits are the same as the first static build (precomputed questions only; Inter/JetBrains Mono still load from Google Fonts if someone switches to `?theme=classic` without internet; Geist is local). The header cost meter on the main screenshot showed a very small per-question figure that did not match the splash totals; the splash totals match the recorded scoreboard / race values. This rebuild did not change any recorded answers.

Free disk at the end of this rebuild: 6.7 GiB.
