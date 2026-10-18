"""Recompute unchanged-treatment initial/repeat results; standard library, offline."""
from pathlib import Path
import collections,hashlib,json,random,re
S=Path(__file__).resolve().parents[1];E=S/'04_evidence/selected'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def score(r):return int(any(0<int(i)<=len(r['sources']) and r['sources'][int(i)-1]['brand']=='flightcentre' for i in re.findall(r'\[(\d+)\]',r['answer'])))
def check(r):
 payload=json.dumps({k:v for k,v in r.items() if k!='record_sha256'},sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
 assert hashlib.sha256(payload).hexdigest()==r['record_sha256']
 assert hashlib.sha256(r['prompt'].encode()).hexdigest()==r['prompt_sha256']
rows=collections.defaultdict(lambda:[0,0,0,0]);n=0
for p in sorted((E/'initial').glob('*.json')):
 b,a,o=read(E/'baseline'/p.name),read(p),read(E/'optimised'/p.name)
 for r in [b,a,o]:check(r)
 assert a['prompt']==o['prompt'] and a['sources']==o['sources'] and a['query']==b['query']==o['query']
 v=rows[a['query_id']];v[0]+=score(b);v[1]+=score(a);v[2]+=score(o);v[3]+=1;n+=1
assert n==290 and len(rows)==29 and all(v[3]==10 for v in rows.values())
def interval(i,j):
 ds=[(v[i]-v[j])/v[3]*100 for _,v in sorted(rows.items())];rng=random.Random(20261018)
 draws=sorted(sum(rng.choices(ds,k=29))/29 for _ in range(20000));return [draws[500],draws[19499]]
totals=[sum(v[i] for v in rows.values()) for i in range(4)];assert totals==[116,143,152,290]
out={'question_counts':dict(sorted(rows.items())),'columns':['baseline','initial','repeat','trials'],'totals':totals,'initial_minus_baseline_95_pp':interval(1,0),'repeat_minus_baseline_95_pp':interval(2,0),'repeat_minus_initial_95_pp':interval(2,1),'seed':20261018,'bootstrap_samples':20000,'method':'Percentile resampling of 29 whole questions, preserving their 10 trials','exact_initial_repeat_prompt_and_source_matches':n,'selection_interpretation':'Both unchanged-page runs are shown; neither constitutes independent held-out confirmation. No pooled rate is treated as a new experiment.'}
(S/'04_evidence/Independent_Repeat_Analysis.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print('PASS: 116 baseline, 143 initial, 152 repeat; all 290 treatment prompts and source packs match.')
