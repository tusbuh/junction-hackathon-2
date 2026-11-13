"""Render evidence: map DXF metre coords onto the PDF sheet (affine fit on shared room-number labels) and draw numbered boxes."""
import sys, json, numpy as np, pymupdf
sys.path.insert(0,'/workspace/stoa/proof')
from swiss import Plan, NUM_RE
R='/workspace/stoa/preview/junction-dataset-preview/'

def fit(plan, page):
    words={w[4]:((w[0]+w[2])/2,(w[1]+w[3])/2) for w in page.get_text('words') if NUM_RE.match(w[4])}
    src=[];dst=[]
    for t,x,y,b in plan.texts:
        if t in words: cx=(b[0]+b[2])/2; cy=(b[1]+b[3])/2; src.append((cx,cy,1)); dst.append(words[t])
    A,_,_,_=np.linalg.lstsq(np.array(src),np.array(dst),rcond=None)
    err=np.abs(np.array(src)@A-np.array(dst)).max()
    return A, err, len(src)

def render(stem, question, out, dpi=110):
    plan=Plan(R+f'data/swiss_dwellings/{stem}.dxf')
    doc=pymupdf.open(R+f'data/swiss_dwellings/{stem}.pdf'); page=doc[0]
    A,err,n=fit(plan,page)
    val,ev,how=plan.answer(question)
    T=lambda x,y: tuple(np.array([x,y,1])@A)
    shape=page.new_shape()
    rects=[]
    for i,(lab,b) in enumerate(ev):
        p1=T(b[0],b[1]); p2=T(b[2],b[3])
        r=pymupdf.Rect(min(p1[0],p2[0])-2,min(p1[1],p2[1])-2,max(p1[0],p2[0])+2,max(p1[1],p2[1])+2)
        rects.append(r)
        shape.draw_rect(r); shape.finish(color=(0.9,0,0.2),fill=(1,0.85,0),fill_opacity=0.35,width=1.2)
    shape.commit()
    for i,r in enumerate(rects):
        page.insert_text((r.x1+1,r.y0+6),str(i+1),fontsize=7,color=(0.9,0,0.2))
    page.insert_text((30,30),f"Q: {question}",fontsize=11,color=(0,0,0.6))
    page.insert_text((30,46),f"A: {val}   ({len(ev)} highlighted; method: {how}; DXF->PDF fit on {n} labels, max err {err:.2f} pt)",fontsize=10,color=(0.8,0,0.2))
    union=rects[0]
    for r in rects[1:]: union|=r
    clip=(union+(-40,-40,40,40))&page.rect
    page.get_pixmap(dpi=dpi).save(out)
    page.get_pixmap(dpi=dpi*2,clip=clip).save(out.replace('.png','_zoom.png'))
    return dict(question=question,answer=val,method=how,evidence=[(l,[round(c,3) for c in b]) for l,b in ev],fit_err_pt=round(float(err),3),image=out)

if __name__=='__main__':
    res=[]
    s='site1000_bldg2082_floor9385'
    res.append(render(s,'How many toilets (WC) are drawn on this floor plan?','/workspace/stoa/proof/demo_wc.png'))
    res.append(render(s,'What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, terraces and other outdoor spaces?','/workspace/stoa/proof/demo_aptA.png'))
    res.append(render(s,'Wie viele Türen (Innentüren und Eingangstüren zusammen) sind auf diesem Grundriss eingezeichnet?','/workspace/stoa/proof/demo_doors.png'))
    gt={json.loads(l)['question']:json.loads(l)['answer'] for l in open(R+'questions.jsonl') if s in l}
    for r in res: r['ground_truth']=gt.get(r['question'])
    json.dump(res,open('/workspace/stoa/proof/demo_answers.json','w'),indent=1,ensure_ascii=False)
    for r in res: print(r['question'][:60],'->',r['answer'],'gt',r['ground_truth'],'err',r['fit_err_pt'])
