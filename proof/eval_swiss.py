import json,sys,collections,re
sys.path.insert(0,'/workspace/stoa/proof')
from swiss import Plan
R='/workspace/stoa/preview/junction-dataset-preview/'
qs=[json.loads(l) for l in open(R+'questions.jsonl') if 'swiss_dwellings' in l]
cache={}; res=collections.defaultdict(lambda:[0,0]); fails=[]
for q in qs:
    p=q['path'].replace('.pdf','.dxf')
    if p not in cache: cache[p]=Plan(R+p)
    v,ev,_=cache[p].answer(q['question'])
    gt=q['answer']
    ok = v is not None and (v==gt if q['type']=='count' else abs(v-gt)<=0.02*abs(gt))
    key=re.sub(r"'.*'|\d+\.\d+|apartment [A-Z]","X",q['question'])[:60]
    res[key][0]+=ok; res[key][1]+=1
    if not ok: fails.append((q['path'].split('/')[-1],q['question'][:70],gt,v))
tot=sum(a for a,b in res.values()),sum(b for a,b in res.values())
for k,(a,b) in sorted(res.items(),key=lambda x:-x[1][1]): print(f"{a}/{b}  {k}")
print('TOTAL',tot, round(100*tot[0]/tot[1],1),'%')
for f in fails[:40]: print(f)
