"""Build the static (backend-free) PINPOINT demo in site/.

    .venv/bin/python tools/build_static.py

Every number in site/ is a recorded response of the real app (pinpoint.server, called in-process with
FastAPI's TestClient): nothing is computed or typed in here. The front end is a copy of static/ with
absolute /static/ paths made relative, plus static/offline.js, which answers the app's /api/* requests
from the recorded files (manifest in pp-data/manifest.js).

Only drawings whose licence allows public redistribution are included (see INCLUDE and site/LICENSES.md).
"""
import gzip, hashlib, json, os, re, shutil, struct, sys, warnings
from urllib.parse import urlsplit, parse_qsl, urlencode

warnings.filterwarnings('ignore')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from fastapi.testclient import TestClient  # noqa: E402
from pinpoint.server import app  # noqa: E402
from pinpoint import engine  # noqa: E402

SITE = os.path.join(ROOT, 'site')
DATA_DIR = 'pp-data'

# Curated drawings. Licence of each one is checked in data/<source>/LICENSE.md (see LICENSES.md).
INCLUDE = [
    # Swiss Dwellings, CC BY 4.0
    'data/swiss_dwellings/site1000_bldg2082_floor9385.pdf',
    'data/swiss_dwellings/site1088_bldg2216_floor10132.pdf',
    'data/swiss_dwellings/site1102_bldg2242_floor10281.pdf',
    'data/swiss_dwellings/site421_bldg1097_floor4796.pdf',
    # ifc_models, CC BY 4.0 (Esplanades, Molio) and KIT "for unrestricted use" (FZK-Haus plan)
    'data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-04-4-korrus.pdf',
    'data/ifc_models/bsc-esplanades_1807-ep-ar-v18.ifc',
    'data/ifc_models/bsc-molio_molio-with-uris_plan-02-klder.pdf',
    'data/ifc_models/bsc-molio_molio-with-uris.ifc',
    'data/ifc_models/kit-fzk-haus_ac20-fzk-haus_plan-02-dachgeschoss.pdf',
    # ifc_bench: MIT (FantasyOffice3) and KIT "for unrestricted use" (AC20 FZK-Haus)
    'data/ifc_bench/fantasy_office_building_3_arc.ifc',
    'data/ifc_bench/ac20_arc.ifc',
    # CubiCasa5K, CC BY-NC-SA 4.0: two example plans only (non-commercial, attribution, same licence)
    'data/cubicasa5k/colorful-11397.png',
    'data/cubicasa5k/colorful-11400.png',
]

c = TestClient(app)
manifest = dict(get={}, ask={}, inspect={}, walk={})
written = {}


def key_of(url):
    u = urlsplit(url)
    path = u.path[u.path.index('/api/'):]
    pairs = sorted([list(p) for p in parse_qsl(u.query, keep_blank_values=True)])
    return path + '?' + json.dumps(pairs, ensure_ascii=False, separators=(',', ':'))


def ifc_for(p):
    if p.endswith('.ifc'):
        return p
    return re.sub(r'\.[^.]+$', '', re.sub(r'_plan-.*$', '', p)) + '.ifc'


def exists(p):
    try:
        return os.path.exists(engine.abspath(p))
    except Exception:
        return False


IFC = {p: ifc_for(p) for p in INCLUDE if engine.source_of(p) in ('ifc_models', 'ifc_bench')}
IFC = {p: i for p, i in IFC.items() if os.path.exists(os.path.join(engine.DATA, i))}   # preview split only, never data/full
ALLOWED = set(INCLUDE) | set(IFC.values())
STEMS = tuple(sorted({re.sub(r'\.[^.]+$', '', p) for p in ALLOWED}))


def allowed(url):
    q = dict(parse_qsl(urlsplit(url).query))
    p = q.get('path')
    return p is None or p.startswith(STEMS)


def save(blob, ext, gz=False):
    h = hashlib.sha1(blob).hexdigest()[:16]
    name = f'{DATA_DIR}/{h}.{ext}' + ('.gz' if gz else '')
    if name not in written:
        with open(os.path.join(SITE, name), 'wb') as f:
            f.write(gzip.compress(blob, 9, mtime=0) if gz else blob)
        written[name] = len(blob)
    return name


EXT = {'application/json': 'json', 'image/svg+xml': 'svg', 'image/png': 'png', 'image/jpeg': 'jpg', 'text/csv': 'csv',
       'application/pdf': 'pdf', 'application/octet-stream': 'bin'}


def entry(blob, ctype, status=200):
    ext = EXT.get(ctype, 'dat')
    gz = ext in ('json', 'bin') and len(blob) > 2048
    return dict(f=save(blob, ext, gz), t=ctype, s=status, **({'z': 1} if gz else {}))


def record(url, transform=None):
    """GET url from the real app, store the response, return parsed JSON (or None)."""
    k = key_of(url)
    if k in manifest['get'] or not allowed(url):
        return None
    r = c.get(url)
    ctype = r.headers.get('content-type', 'application/octet-stream').split(';')[0]
    if r.status_code >= 500:
        print('  !', r.status_code, url)
    body = r.content
    data = None
    if ctype == 'application/json':
        data = r.json()
        if transform:
            data = transform(data)
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
    manifest['get'][k] = entry(body, ctype, r.status_code)
    if data is not None:
        crawl(data)
    return data


def crawl(o):
    """Record every /api/... URL the app embedded in a response (sheet images, meshes, plan SVGs)."""
    if isinstance(o, dict):
        for v in o.values():
            crawl(v)
    elif isinstance(o, list):
        for v in o:
            crawl(v)
    elif isinstance(o, str) and o.startswith('/api/') and '?' in o:
        record(o)


def u(ep, **q):
    return f'{ep}?{urlencode(q)}'


def bundle(kind, path, obj):
    blob = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()
    manifest[kind][path] = entry(blob, 'application/json')


def mesh_gids(ifc):
    import io
    full = os.path.join(engine.CACHE, os.path.splitext(os.path.basename(ifc))[0] + '.mesh.bin')
    with open(full, 'rb') as f:
        n = struct.unpack('<I', f.read(4))[0]
        return [e['gid'] for e in json.loads(f.read(n))['elements']]


def main():
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(os.path.join(SITE, DATA_DIR))

    # ---- global endpoints
    cat = c.get('/api/catalog').json()
    cat = [f for f in cat if f['path'] in INCLUDE]
    cat.sort(key=lambda f: INCLUDE.index(f['path']))
    assert len(cat) == len(INCLUDE), set(INCLUDE) - {f['path'] for f in cat}
    manifest['get'][key_of('/api/catalog')] = entry(json.dumps(cat, ensure_ascii=False, separators=(',', ':')).encode(), 'application/json')
    for f in cat:
        crawl(f)
    qtext = {q['q'] for f in cat for q in f['questions']}
    record('/api/scoreboard')
    # race: totals are the real eval totals; the question ticker keeps only questions about the included drawings
    record('/api/race', lambda d: {**d, 'sample': [s for s in d.get('sample', []) if (s if isinstance(s, str) else s.get('q')) in qtext]})
    record('/api/audit/showcase', lambda d: {**d, 'audits': [a for a in d['audits'] if a['path'] in ALLOWED]})

    # ---- per drawing
    for f in cat:
        p = f['path']
        print(p, f['n'], 'questions')
        paths = [p] + ([IFC[p]] if p in IFC and IFC[p] != p else [])
        for q in paths:
            record(u('/api/credit', path=q))
            record(u('/api/audit', path=q))
            record(u('/api/parts', path=q))
        if not p.endswith('.ifc') and not f.get('plan'):
            record(u('/api/sheet', path=p))
        if p in IFC:
            record(u('/api/mesh', path=IFC[p]))
        # answers to every dataset question on this drawing
        answers = {}
        for q in dict.fromkeys(x['q'] for x in f['questions']):
            r = c.post('/api/ask', json=dict(path=p, question=q))
            answers[q.strip()] = r.json()
            crawl(answers[q.strip()])
        bundle('ask', p, answers)
        # bill of quantities
        b = record(u('/api/boq', path=p))
        if b and b.get('kind') != 'none' and not b.get('detail'):
            record(u('/api/boq_verify', path=p))
            record(u('/api/boq.csv', path=p))
            record(u('/api/boq.pdf', path=p))
        # walkthrough: base geometry once + the highlighted answer for each question
        w = c.get(u('/api/walk', path=p, q=''))
        if w.status_code == 200:
            wb = w.json()
            crawl(wb)
            wa = {}
            if engine.source_of(p) == 'swiss_dwellings':
                for q in answers:
                    a = c.get(u('/api/walk', path=p, q=q)).json().get('answer')
                    if a is not None:
                        wa[q] = a
            bundle('walk', p, dict(base=wb, answers=wa))
        else:
            manifest['get'][key_of(u('/api/walk', path=p, q=''))] = entry(w.content, 'application/json', w.status_code)
        # component identification: one card per element the parts list or the 3D model can show
        parts = c.get(u('/api/parts', path=p)).json()
        ids = set((parts.get('geo') or {}).keys())
        for g in parts.get('groups') or []:
            for t in g.get('types') or []:
                ids.update(t.get('ids') or [])
        if p in IFC:
            ids.update(mesh_gids(IFC[p]))
        cards = {}
        for i in sorted(ids):
            r = c.get(u('/api/inspect', path=p, id=i))
            if r.status_code == 200:
                cards[i] = r.json()
        bundle('inspect', p, cards)
        print('   ', len(answers), 'answers,', len(cards), 'element cards')
    # walk / identify from the 3D view of a plan use the model path: point it at the plan's bundle
    alias = {}
    for p, i in IFC.items():
        if i != p and i not in manifest['inspect']:
            alias[i] = p
    manifest['alias'] = alias
    with open(os.path.join(SITE, DATA_DIR, 'manifest.js'), 'w') as fo:
        fo.write('window.__PP_OFFLINE=' + json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + ';\n')

    copy_front_end(len(cat))
    print('files', len(written), 'raw MB', round(sum(written.values()) / 1e6, 1))


def copy_front_end(ndraw):
    src = os.path.join(ROOT, 'static')
    dst = os.path.join(SITE, 'static')
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('findings.json', '*.map'))
    for dp, _, fs in os.walk(dst):
        for fn in fs:
            if not fn.endswith('.js'):
                continue
            fp = os.path.join(dp, fn)
            t = open(fp, encoding='utf-8').read()
            o = t
            rel = os.path.relpath(dst, dp)
            pre = './' if rel == '.' else rel + '/'
            t = re.sub(r"""(from\s+|import\()(['"])/static/""", lambda m: m.group(1) + m.group(2) + pre, t)
            t = re.sub(r"""(\.href\s*=\s*)(['"])/static/""", r"\1\2static/", t)
            # the static site always shows final values (the ?static=1 mode); ?anim=1 brings the count-ups back
            t = t.replace("new URLSearchParams(location.search).has('static')", "!new URLSearchParams(location.search).has('anim')")
            if t != o:
                open(fp, 'w', encoding='utf-8').write(t)
    shutil.copy(os.path.join(ROOT, 'tools', 'offline.js'), os.path.join(dst, 'offline.js'))
    h = open(os.path.join(src, 'index.html'), encoding='utf-8').read()
    h = h.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    h = h.replace('"three":"/static/vendor/three.module.js"', '"three":"./static/vendor/three.module.js"')
    h = h.replace('<script type="importmap">',
                  f'<script src="{DATA_DIR}/manifest.js"></script>\n<script src="static/offline.js"></script>\n<script type="importmap">', 1)
    badge = (f'<a class="ppStatic" style="position:fixed;left:17px;top:47px;z-index:30;font:600 9.5px/1 Inter,system-ui,sans-serif;'
             f'color:#9fb3c8;background:rgba(10,16,24,.82);border:1px solid rgba(159,179,200,.3);border-radius:4px;padding:2px 6px;text-decoration:none" href="LICENSES.html" title="Static build: answers for {ndraw} drawings were recorded from the real app. '
             f'Data licences and credits">static demo · {ndraw} drawings · data licences</a>\n')
    h = h.replace('</body>', badge + '</body>', 1)
    assert not re.search(r'''["'(]/static/''', h), 'absolute /static/ path left in index.html'
    open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8').write(h)


def table_row(path):
    src = engine.source_of(path)
    lic = os.path.join(engine.DATA, 'data', src, 'LICENSE.md')
    for line in open(lic, encoding='utf-8'):
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells) >= 5 and cells[0] == os.path.basename(path):
            return dict(title=cells[1], source=cells[4])
    return {}


LIC_URL = {'CC-BY-4.0': 'https://creativecommons.org/licenses/by/4.0/', 'CC-BY-NC-SA-4.0': 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
           'MIT': 'https://opensource.org/license/mit', 'LicenseRef-KIT-unrestricted': 'https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples'}
MIT_TEXT = open(os.path.join(engine.DATA, 'data', 'ifc_bench', 'LICENSE.md'), encoding='utf-8').read().split('```')[1].strip()


def write_licenses():
    from pinpoint.wow import credit
    rows, seen = [], set()
    for p in INCLUDE + sorted(set(IFC.values()) - set(INCLUDE)):
        if p in seen:
            continue
        seen.add(p)
        cr, tr = credit(p), table_row(p)
        src = tr.get('source') or {'swiss_dwellings': 'https://doi.org/10.5281/zenodo.7788422',
                                    'cubicasa5k': 'https://zenodo.org/records/2613548'}.get(engine.source_of(p), '')   # from their LICENSE.md
        rows.append((p, cr['licence'], cr['credit'], tr.get('title', ''), src))
    md = ['# Licences and credits of the drawings in this static demo', '',
          'This static build shows only drawings whose licence allows public redistribution with attribution. Each drawing is',
          'shown with its credit line under it. Answers, highlights, 3D meshes, element cards and bills of quantities derived',
          'from a drawing are shared under the same licence as that drawing (for CubiCasa5K: CC BY-NC-SA 4.0, non-commercial).',
          'Questions inherit the licence of the drawing they ask about; the ifc_bench questions are IFC-Bench v2,',
          'Copyright (c) 2025 Sylvain Hellin, CC BY 4.0 (https://huggingface.co/datasets/sylvainhellin/ifc-bench).', '',
          'Not included: CubiCasa5K beyond two example plans, US drawing sets (opening_design), the CC BY-ND and GPL IFC models,',
          'HABS, Finna, Europeana and Wikimedia scans, any per-question evaluation file and any test-split file.', '',
          '| drawing (dataset path) | what | licence | credit | source |', '|---|---|---|---|---|']
    for p, lic, cr, title, src in rows:
        md.append(f'| `{p}` | {title or "-"} | [{lic}]({LIC_URL.get(lic, "")}) | {cr} | {src or "-"} |')
    md += ['', '## Licence texts', '',
           '- CC BY 4.0: https://creativecommons.org/licenses/by/4.0/',
           '- CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/',
           '- KIT IFC examples: "for unrestricted use", source to cite: Institute for Automation and Applied Informatics (IAI) /',
           '  Karlsruhe Institute of Technology (KIT), https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples',
           '- MIT (Fantasy office building 3, Copyright (c) 2025 TUM Students, BIM Fundamentals SS2025):', '', '```', MIT_TEXT, '```', '',
           '## Third-party code', '', '- three.js (static/vendor), Copyright 2010-2024 Three.js Authors, MIT licence.', '']
    txt = '\n'.join(md)
    open(os.path.join(SITE, 'LICENSES.md'), 'w', encoding='utf-8').write(txt)
    import html
    open(os.path.join(SITE, 'LICENSES.html'), 'w', encoding='utf-8').write(
        '<!doctype html><meta charset="utf-8"><title>PINPOINT static demo: licences</title>'
        '<body style="font:14px/1.5 system-ui,sans-serif;max-width:1100px;margin:30px auto;padding:0 16px">'
        '<p><a href="./">&larr; back to the demo</a> &middot; <a href="LICENSES.md">LICENSES.md</a></p>'
        f'<pre style="white-space:pre-wrap">{html.escape(txt)}</pre></body>')
    return rows


NETLIFY = '''# Netlify: publish this folder as-is (no build step)
[build]
  publish = "."
  command = ""

[[headers]]
  for = "/pp-data/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"

[[headers]]
  for = "/*.md"
  [headers.values]
    Content-Type = "text/plain; charset=utf-8"
'''


if __name__ == '__main__':
    if '--front' in sys.argv:   # front end + licences only (keeps the recorded pp-data/)
        shutil.rmtree(os.path.join(SITE, 'static'), ignore_errors=True)
        copy_front_end(len(INCLUDE))
    else:
        main()
    write_licenses()
    open(os.path.join(SITE, 'netlify.toml'), 'w').write(NETLIFY)
    open(os.path.join(SITE, '.nojekyll'), 'w').close()   # GitHub Pages: serve every file as-is
