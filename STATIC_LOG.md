# STATIC track log

## STOPPED: free disk below 3.5 GB (Sat 2026-11-14 ~16:47)

`df -h /` showed **3.1 GiB free** right after the first export run (it was 4.9 GiB at the start of this track).
The rule says to stop under 3.5 GB, so I stopped here. Nothing was published, deployed or pushed to a new remote.

What used the disk: this track wrote `site/` (38 MB) and about 1 MB of sheet SVGs to the shared `data/cache`
(two Swiss sheets). The other ~1.7 GB came from outside this track (another process; I did not look into other
jh2-* folders, as the rules say).

## State when stopped

- `tools/build_static.py`: records the real app's responses in-process (FastAPI TestClient against `pinpoint.server`)
  for a curated, licence-checked drawing list and writes `site/` (front-end copy with relative paths +
  `pp-data/` recorded responses + `pp-data/manifest.js`). Every number is a recorded app response; none is typed in.
- `tools/offline.js`: browser shim that answers `/api/*` from the recorded files (fetch, `<img src>`, `<a href>`),
  with gzip bundles decoded by `DecompressionStream`.
- First run recorded all data (13 drawings: 4 Swiss, 5 ifc_models, 2 ifc_bench, 2 CubiCasa; 1,262 answers;
  ~14k element cards; meshes) in 5 min, `site/` = 38 MB. It then failed in the last step (`copy_front_end`) on a
  self-check: an absolute `/static/` path was still in index.html. That is a small fix (more `/static/` spellings in
  index.html need rewriting).

Still to do (not started): fix that rewrite, LICENSES.md/LICENSES.html, netlify.toml, the local test with
`python3 -m http.server 8767`, screenshots, site.zip, the deploy notes, commit and push.

To resume: free disk to above 3.5 GB, then `.venv/bin/python tools/build_static.py` (rebuilds `site/` from scratch).
