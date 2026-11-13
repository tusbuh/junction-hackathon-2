import json,sys,collections,re,os,time
sys.path.insert(0,'/workspace/stoa/proof')
from ifcq import Model
R='/workspace/stoa/preview/junction-dataset-preview/'
qs=[json.loads(l) for l in open(R+'questions.jsonl') if 'ifc_models' in l]
cache={}; res=collections.defaultdict(lambda:[0,0]); fails=[]
for q in qs:
    p=re.sub(r'_plan-.*$','',q['path'].rsplit('.',1)[0])+'.ifc'
    if not os.path.exists(R+p): res['(model ifc not in preview)'][1]+=1; continue
    if p not in cache: t=time.time(); cache[p]=Model(R+p); print('loaded',p,round(time.time()-t,1),'s')
    try: v,ev,how=cache[p].answer(q['question'])
    except Exception as e: v,how=None,repr(e)
    gt=q['answer']
    ok= v is not None and (v==gt if q['type']=='count' else abs(v-gt)<=0.02*abs(gt)+1e-9)
    key=re.sub(r"['„«“].*?['“»]","X",q['question'])[:55]
    res[key][0]+=ok; res[key][1]+=1
    if not ok: fails.append((p.split('/')[-1][:20],q['question'][:80],gt,v,how))
for k,(a,b) in sorted(res.items(),key=lambda x:-x[1][1]): print(f"{a}/{b}  {k}")
a=sum(x for x,y in res.values() if True); b=sum(y for x,y in res.values())
print('TOTAL',a,b)
for f in fails[:30]: print(f)
