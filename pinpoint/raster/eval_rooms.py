"""python -m pinpoint.raster.eval_rooms preview|val300 -> accuracy of OCR room-label counts per question template
(preview = dev set used to design the rules; val300 = 300 other Stoa CubiCasa plans, held out for validation)."""
import sys, json, os, glob, collections
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from pinpoint.raster import ocr, rooms
from pinpoint import engine
TPL = {'bedrooms': ('How many bedrooms', 'bedroom'), 'kitchens': ('How many kitchens', 'kitchen'), 'bathrooms': ('How many bathrooms', 'bathroom'),
       'wc': ('How many separate WC', 'wc'), 'saunas': ('How many saunas', 'sauna'), 'balconies': ('How many balconies', 'balcony'),
       'floors': ('How many floors', 'floors')}
which = sys.argv[1]
if which == 'preview':
    Q = [json.loads(l) for l in open(os.path.expanduser('~/jh2-acc/data/preview/junction-dataset-preview/questions.jsonl')) if 'cubicasa' in l]
else:
    val = set(json.load(open(os.path.expanduser('~/jh2-acc/data/full/cubicasa_val300.json'))))
    Q = [json.loads(l) for l in open(os.path.expanduser('~/jh2-acc/data/full/questions.jsonl')) if '/cubicasa5k/' in l]
    Q = [q for q in Q if q['path'] in val]
acc = collections.defaultdict(lambda: [0, 0]); conf = collections.defaultdict(collections.Counter)
miss = 0
for q in Q:
    k = next((k for k, (pre, c) in TPL.items() if q['question'].startswith(pre)), None)
    if not k: continue
    p = engine.abspath(q['path'])
    o = ocr.cached(p)
    if o is None: miss += 1; continue
    v, _ = rooms.count(o, TPL[k][1]); v = max(v, rooms.MINIMUM.get(TPL[k][1], 0))
    acc[k][0] += v == q['answer']; acc[k][1] += 1
    conf[k][(q['answer'], v)] += 1
print('missing ocr', miss)
out = os.environ.get('PINPOINT_EVAL_OUT') or os.path.join(os.path.dirname(__file__), '..', '..', 'data/eval_acc')
os.makedirs(out, exist_ok=True)
json.dump(dict(split=which, missing_ocr=miss, by_template={k: dict(correct=a, graded=b) for k, (a, b) in acc.items()}),
          open(os.path.join(out, f'cubicasa_rooms_{which}.json'), 'w'))
for k, (a, b) in acc.items():
    print(f'{k:10s} {a}/{b} = {100*a/b:.0f}%   (truth,pred) top errors:', [x for x in conf[k].most_common(12) if x[0][0] != x[0][1]][:6])
