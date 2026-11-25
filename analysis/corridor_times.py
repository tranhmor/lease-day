import json,heapq,math,sys
d=json.load(open(sys.argv[1]))
nodes={e['id']:e for e in d['elements'] if e['type']=='node'}
rels=[e for e in d['elements'] if e['type']=='relation']
def km(a,b): return math.hypot((a[0]-b[0])*111.2,(a[1]-b[1])*85.3)
AFTER2018={'17','19','3','11','18','12'}
def lines(era):
    out=[]
    for r in rels:
        t=r.get('tags',{}); name=t.get('name',''); ref=t.get('ref') or name
        if '首都机场' in name or '大兴机场' in name: continue
        if era=='before' and (ref in AFTER2018 or '12号线' in name): continue
        seq=[]
        for m in r['members']:
            if m['type']=='node' and m.get('role','').startswith('stop') and m['ref'] in nodes:
                n=nodes[m['ref']]; nm=n.get('tags',{}).get('name')
                if nm and (not seq or seq[-1][0]!=nm): seq.append((nm,(n['lat'],n['lon'])))
        if '昌平线' in name and era=='before':
            names=[s[0] for s in seq]
            if '西二旗' in names:
                i=names.index('西二旗')
                seq=seq[:i+1] if '昌平西山口'==names[0] else seq[i:]
        out.append((ref,seq))
    return out
def graph(era,v,dwell,transfer):
    G={};pos={}
    for ref,seq in lines(era):
        for i in range(len(seq)-1):
            a,b=seq[i],seq[i+1]; t=km(a[1],b[1])*1.12/v*60+dwell
            G.setdefault((a[0],ref),[]).append(((b[0],ref),t,km(a[1],b[1])))
            pos[a[0]]=a[1];pos[b[0]]=b[1]
    st={}
    for k in G: st.setdefault(k[0],set()).add(k[1])
    for k,vs in list(G.items()):
        for (b,t,_) in vs: st.setdefault(b[0],set()).add(b[1])
    for s,rs in st.items():
        for a in rs:
            for b in rs:
                if a!=b: G.setdefault((s,a),[]).append(((s,b),transfer,0))
    return G,st,pos
def best(G,st,src,dst):
    pq=[(0,0,(src,r)) for r in st[src]];seen={}
    while pq:
        t,dist,u=heapq.heappop(pq)
        if u in seen: continue
        seen[u]=t
        if u[0]==dst: return t,dist
        for v,w,dk in G.get(u,[]):
            if v not in seen: heapq.heappush(pq,(t+w,dist+dk,v))
    return None,None
OD=[('昌平','中关村'),('昌平','知春路'),('昌平','西土城'),('昌平','上地'),('沙河','中关村'),('沙河','知春路'),('沙河','西土城'),('生命科学园','中关村'),('回龙观','中关村'),('回龙观','上地'),('回龙观','知春路'),('西二旗','西土城'),('北安河','中关村'),('西北旺','中关村'),('马连洼','中关村')]
for v,dw,tr in [(45,0.6,5),(38,0.6,5),(52,0.6,4)]:
    Gb,sb,pb=graph('before',v,dw,tr);Ga,sa,pa=graph('after',v,dw,tr)
    print(f'\nspeed {v} km/h, dwell {dw} min, transfer {tr} min; door-to-door adds 8+3+6=17 min')
    for o,dd in OD:
        tb,db=best(Gb,sb,o,dd) if o in sb and dd in sb else (None,None)
        ta,da=best(Ga,sa,o,dd) if o in sa and dd in sa else (None,None)
        f=lambda x:'n/a' if x is None else f'{x:5.1f}'
        door=lambda x:'n/a' if x is None else f'{x+17:5.1f}'
        line=(pa.get(o) or pb.get(o)); dstp=(pa.get(dd) or pb.get(dd))
        straight=km(line,dstp) if line and dstp else float('nan')
        print(f'{o:6}->{dd:5} metro {f(tb)} -> {f(ta)} | door {door(tb)} -> {door(ta)} | straight {straight:5.1f} km | authors formula {2.1931*straight*1.25+23.607:5.1f}')
