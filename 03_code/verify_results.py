"""Offline audit. Python 3.10+, standard library only. No network or model calls.
Run from any directory: python path/to/03_code/verify_results.py
"""
from pathlib import Path
import collections, hashlib, json, random, re

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / '04_evidence'
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def check_record(r):
    assert r['record_sha256'] == digest({k:v for k,v in r.items() if k!='record_sha256'}), 'Record fingerprint mismatch'
    assert r['prompt_sha256'] == hashlib.sha256(r['prompt'].encode()).hexdigest(), 'Prompt fingerprint mismatch'
def inclusion(r):
    ids={int(x) for x in re.findall(r'\[(\d+)\]',r['answer'])}
    return int(any(0<i<=len(r['sources']) and r['sources'][i-1]['brand']=='flightcentre' for i in ids))
def compare_pairs(baseline_dir, treatment_dir, position=False):
    rows=collections.defaultdict(lambda:[0,0,0]);matched=0
    for p in sorted(treatment_dir.glob('*.json')):
        b,o=read(baseline_dir/p.name),read(p)
        check_record(b);check_record(o)
        assert b['query']==o['query'] and b.get('pair_key',b['key'])==o.get('pair_key',o['key'])
        bc=[(s['url'],s['text']) for s in b['sources'] if s['brand']!='flightcentre']
        oc=[(s['url'],s['text']) for s in o['sources'] if s['brand']!='flightcentre']
        assert bc==oc, 'Competitor texts or relative order differ'
        if position:
            assert sorted((s['url'],s['text']) for s in b['sources'])==sorted((s['url'],s['text']) for s in o['sources'])
            assert o['sources'][0]['brand']=='flightcentre'
        else:
            assert [s['url'] for s in b['sources']]==[s['url'] for s in o['sources']]
        x=rows[b['query_id']];x[0]+=inclusion(b);x[1]+=inclusion(o);x[2]+=1;matched+=1
    assert matched==290 and len(rows)==29 and all(x[2]==10 for x in rows.values())
    return rows
def main():
    q=compare_pairs(E/'selected/baseline',E/'selected/optimised')
    b=sum(x[0] for x in q.values());o=sum(x[1] for x in q.values());n=sum(x[2] for x in q.values())
    assert (b,o,n)==(116,152,290)
    diffs=[(v[1]-v[0])/v[2] for _,v in sorted(q.items())]
    rng=random.Random(20261017);samples=sorted(sum(rng.choices(diffs,k=len(diffs)))/len(diffs)*100 for _ in range(20000))
    # This independently recomputed percentile interval may differ slightly from the saved run's bootstrap.
    interval=[samples[500],samples[19499]]
    methods=[]
    for m in read(E/'individual_methods.json'):
        rows=compare_pairs(E/'individual/common_baseline',E/'individual'/m['folder']/'records','position_corrected' in m['folder'])
        bb=sum(x[0] for x in rows.values());oo=sum(x[1] for x in rows.values())
        assert bb==m['verified_counts']['baseline'] and oo==m['verified_counts']['optimised']
        methods.append({'method':m['method'],'baseline':bb,'optimised':oo,'n':290})
    outputs=read(E/'pages/outputs.json');assert len(outputs)==52
    for v in outputs.values():
        assert hashlib.sha256(v['html'].encode()).hexdigest()==v['raw_sha256']
        assert hashlib.sha256(v['clean'].encode()).hexdigest()==v['clean_sha256']
    normalise=lambda u:u.replace('://www.','://').rstrip('/')
    by_url={normalise(u):v['clean'] for u,v in outputs.items()}
    delivered=0
    for p in (E/'selected/optimised').glob('*.json'):
        for source in read(p)['sources']:
            if source['brand']=='flightcentre':
                assert source['text']==by_url[normalise(source['url'])][:24000], 'Supplied FC text differs from selected page output'
                delivered+=1
    assert delivered==330
    result={'status':'PASS','selected':{'baseline':b,'optimised':o,'n_per_condition':n,'questions':29,'difference_pp':(o-b)/n*100,'relative_increase_pct':(o-b)/b*100,'directions':{'improved':sum(d>0 for d in diffs),'declined':sum(d<0 for d in diffs),'unchanged':sum(d==0 for d in diffs)},'independent_bootstrap95_pp':interval,'bootstrap_seed':20261017,'bootstrap_samples':20000},'source_matching':'290 headline pairs: same URLs/order and unchanged competitor texts','corrected_position':'290 pairs: all source text and competitor relative order preserved','individual_methods':methods,'page_fingerprints_checked':52,'limits':'Checks record integrity, scoring and matching; not truth, citation entailment or causal identification.'}
    result['selected_FC_source_occurrences_matching_page_output']=delivered
    out=ROOT/'02_documentation/Offline_Verification.json';out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__': main()
