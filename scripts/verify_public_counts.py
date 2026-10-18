from pathlib import Path
import json,random
root=Path(__file__).resolve().parents[1]
d=json.loads((root/'results/Independent_Repeat_Analysis.json').read_text(encoding='utf-8'))
rows=[v for k,v in sorted(d['question_counts'].items())]
assert len(rows)==29 and all(v[3]==10 for v in rows)
totals=[sum(v[i] for v in rows) for i in range(4)]
assert totals==[116,143,152,290]
for i,j,key in [(1,0,'initial_minus_baseline_95_pp'),(2,0,'repeat_minus_baseline_95_pp'),(2,1,'repeat_minus_initial_95_pp')]:
 ds=[(v[i]-v[j])/v[3]*100 for v in rows];rng=random.Random(20261018)
 draws=sorted(sum(rng.choices(ds,k=29))/29 for _ in range(20000))
 ci=[draws[500],draws[19499]]
 assert all(abs(a-b)<1e-10 for a,b in zip(ci,d[key]))
 print(key,ci)
print('PASS: question-level totals 116 / 143 / 152 out of 290. Raw-answer verification requires the assessment package.')
