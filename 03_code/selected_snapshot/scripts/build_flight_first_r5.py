"""Build a new immutable r5 release from the sealed r4 content."""
import sys,json,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geo_bench import baseline_v2 as b
from geo_bench.search.live_retriever import normalise_url
from geo_bench.experiment.run_store import url_hash
from geo_bench.retrieval.chunker import make_passages
from geo_bench.config import CONFIG
from optimisation_v3.flight_first_refinement import refine,ARM

R4=ROOT/'results/v3_final_release_20260920_r4'
OUT=ROOT/'results/v3_final_release_20260920_r5'


def main():
    if OUT.exists() and any(OUT.iterdir()):raise ValueError('Use a new release path; no overwrite')
    m=b.read(R4/'validated_manifest.json')
    assert b.digest({k:v for k,v in m.items() if k!='release_id'})==m['release_id']
    for name,h in m['artifacts'].items():
        assert b.sha(R4/name)==h,name
    for name,h in m['code'].items():
        assert b.sha(ROOT/name)==h,name
    rows=b.read(R4/'v3_final_core.json');outputs={};review=[]
    parent=Path(m['parent_path']);pages=b.read(parent/'pages.json')
    contexts=b.read(parent/'contexts.json')
    fixed={normalise_url(p['file']) for key,pool in contexts.items() if key.endswith('/fixed') for p in pool if p['brand']=='flightcentre'}
    OUT.mkdir(parents=True,exist_ok=True)
    for key,prior in rows.items():
        o=refine(prior);outputs[key]=o
        pairs=o['evidence'][-1]['pairs']
        passages=make_passages(o['clean'],'flightcentre',o['url'],CONFIG)
        available=sum(any((e['question']+' '+e['answer']) in p.text[:CONFIG.passage_prompt_chars] for p in passages) for e in pairs)
        delivered=sum((e['question']+' '+e['answer']) in o['clean'][:CONFIG.page_prompt_chars] for e in pairs)
        if key in fixed and delivered!=len(pairs):raise ValueError('Restored FAQ truncated in fixed context: '+key)
        h=url_hash(o['url']);folder=OUT/'pages'/h;folder.mkdir(parents=True)
        (folder/'final.html').write_text(o['html'],encoding='utf-8')
        (folder/'final.txt').write_text(o['clean'],encoding='utf-8')
        content='<!doctype html><meta charset="utf-8"><title>r5 flight-first comparison</title><style>body{font:16px system-ui;margin:28px}article{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}pre{white-space:pre-wrap;line-height:1.5}</style>'
        content+='<a href="../../index.html">All pages</a><h1>'+html.escape(o['url'])+'</h1><p>Historical content. Baseline, prior r4, and FAQ/flight-first r5. No new factual claims or performance claims.</p><article>'
        for title,text in [('Baseline',pages[key]['text']),('Prior optimised r4',prior['clean']),('Refined r5',o['clean'])]:
            content+='<section><h2>'+title+'</h2><pre>'+html.escape(text)+'</pre></section>'
        (folder/'comparison.html').write_text(content+'</article>',encoding='utf-8')
        review.append({'url':key,'folder':h,'changed':o['clean']!=prior['clean'],'restored_questions':len(pairs),
                       'section_moves':len(o['notes']['r5']['movements']),'selected_in_fixed':key in fixed,
                       'complete_pairs_in_fixed_budget':delivered,'complete_pairs_available_in_passages':available,
                       'pairs_not_complete_in_one_passage':len(pairs)-available,'chars':len(o['clean']),
                       'fixed_budget_exceeded':len(o['clean'])>CONFIG.page_prompt_chars})
        print('VALIDATED',len(review),key,flush=True)
    b.write(OUT/'outputs.json',outputs);b.write(OUT/'review.json',review)
    validation={'status':'PASS','pages':len(review),'changed_pages':sum(r['changed'] for r in review),
                'restored_questions':sum(r['restored_questions'] for r in review),
                'moved_sections':sum(r['section_moves'] for r in review),
                'complete_pairs_available_in_passages':sum(r['complete_pairs_available_in_passages'] for r in review),
                'pairs_not_complete_in_one_passage':sum(r['pairs_not_complete_in_one_passage'] for r in review),
                'fixed_selected_pages_truncate_restored_pairs':0,
                'oversize_pages':[r for r in review if r['fixed_budget_exceeded']],
                'invariants':['original body word multiset plus exact question labels','original answers unchanged',
                              'question-answer adjacency','offer card HTML unchanged','metadata unchanged','source links unchanged'],
                'limitation':'No guarantee of passage retrieval, positive visibility or factual truth of inherited claims.'}
    b.write(OUT/'validation.json',validation)
    (OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Flight-first r5</title><h1>Flight-first r5: 52 page comparisons</h1><p>Baseline versus r4 versus r5; frozen historical content.</p><ul>'+''.join('<li><a href="pages/'+r['folder']+'/comparison.html">'+html.escape(r['url'])+'</a></li>' for r in review)+'</ul>',encoding='utf-8')
    files=list((ROOT/'optimisation_v3').glob('*.py'))+[ROOT/'scripts/build_flight_first_r5.py',ROOT/'FLIGHT_FIRST_R5_PROTOCOL.md']+list((ROOT/'geo_bench').rglob('*.py'))
    manifest={'version':'r5-flight-first','arm':ARM,'prior_release_id':m['release_id'],'prior_release_path':str(R4),
              'parent_path':str(parent),'parent_id':m['parent_id'],'validation':validation,
              'code':{p.relative_to(ROOT).as_posix():b.sha(p) for p in files},
              'artifacts':{p.relative_to(OUT).as_posix():b.sha(p) for p in OUT.rglob('*') if p.is_file()}}
    manifest['release_id']=b.digest(manifest);b.write(OUT/'validated_manifest.json',manifest)
    print(json.dumps(validation,indent=2),flush=True)


if __name__=='__main__':main()
