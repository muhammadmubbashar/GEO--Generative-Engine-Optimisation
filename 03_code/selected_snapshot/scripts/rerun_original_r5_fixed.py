"""Exact original-r5 fixed prompt repeat; reuse historical control, no page edits."""
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geo_bench import baseline_v2 as b
from optimisation_v3 import experiment as engine, refinement_experiment as runner
ARM='v3_final_flight_first_r5'
PRIOR=ROOT/'results/v3_final_flight_first_r5_evaluation_20260921'
OUT=ROOT/'results/r5_original_unchanged_fixed_repeat_20260928'

def prepare():
    if OUT.exists():raise ValueError('Do not overwrite an existing run')
    prior=engine.validate(PRIOR)
    queries={q['id']:q for q in engine.load_queries(PRIOR)}
    oldctx=b.read(PRIOR/'contexts.json')
    jobs=[j for j in b.read(PRIOR/'schedule.json') if j['arm']==ARM and j['variant']=='fixed' and queries[j['query_id']]['stratum']=='primary']
    assert len(jobs)==290 and len({j['query_id'] for j in jobs})==29
    ctx={ARM:{key:val for key,val in oldctx[ARM].items() if key in {j['query_id']+'/fixed' for j in jobs}}}
    oldjobs={j['key']:j for j in b.read(PRIOR/'schedule.json')}
    references=[];controls=[];original=[]
    for j in jobs:
        old=engine.checked_record(PRIOR,j,queries,oldctx,prior)
        prompt=engine.planned(j,queries,ctx,prior)[-1]
        assert prompt==old['prompt']
        controljob=oldjobs['baseline_repeat__'+j['pair_key']]
        control=engine.checked_record(PRIOR,controljob,queries,oldctx,prior)
        controls.append({**b.record_metrics(control),'arm':'baseline_repeat','pair_key':j['pair_key']})
        original.append({**b.record_metrics(old),'arm':ARM,'pair_key':j['pair_key']})
        references.append({'key':j['key'],'prompt_sha256':old['prompt_sha256'],'original_record_sha256':old['record_sha256'],
                           'baseline_path':controljob['path'],'baseline_record_sha256':control['record_sha256']})
    OUT.mkdir(parents=True)
    for name,data in [('contexts.json',ctx),('schedule.json',jobs),('original_prompt_references.json',references),('historical_baseline_metrics.json',controls),('historical_r5_metrics.json',original)]:b.write(OUT/name,data)
    b.csv_write(OUT/'queries.csv',[queries[k] for k in sorted({j['query_id'] for j in jobs})])
    (OUT/'protocol.md').write_text('''# Unchanged original r5, fixed-only repeat

Explicit user request: retain original r5 including SSR prices and all content. All 290 prompts are verified byte-for-byte against the original saved r5 run. Same 29 primary fixed questions, model request, source ordering, competitors and prompt budget. No page changes, no reindexed generation, no baseline generation. Ten matched source-order/generation trials per question; the repetition index participates in shuffling.

Compare the new treatment answers with the prespecified original 116/290 baseline answers (40%). Also retain the original 143/290 r5 result (49.31%) as the repeatability reference. This is an exploratory historical-control comparison, not a fresh simultaneous control or independent holdout. SSR/baseline capture dates differ. Report the outcome whatever its value; no target-rate stopping or cherry-picking. Citation inclusion is not citation entailment.
''',encoding='utf8')
    code={**prior['code'],Path(__file__).relative_to(ROOT).as_posix():b.sha(Path(__file__))}
    for name in code:
        dest=OUT/'code'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    lock={'version':'original_r5_unchanged_repeat','parent_path':prior['parent_path'],'parent_id':prior['parent_id'],
          'prior_id':prior['experiment_id'],'created_at':datetime.now(timezone.utc).isoformat(),
          'model':prior['model'],'endpoint':prior['endpoint'],'policy':{**prior['policy'],'primary_variant':'fixed'},
          'arms':[ARM],'expected_records':290,'control_generation':'original saved baseline reused; zero new baseline calls',
          'analysis_status':'Exploratory exact-prompt r5 repeat with historical control; mixed capture dates',
          'code':code,'artifacts':{p.relative_to(OUT).as_posix():b.sha(p) for p in OUT.rglob('*') if p.is_file()}}
    lock['experiment_id']=b.digest(lock);b.write(OUT/'lock.json',lock);engine.validate(OUT)
    print('VERIFIED: 290 exact original r5 prompts; original SSR prices retained; no baseline generation',flush=True)

def report():
    lock=engine.validate(OUT);ctx=b.read(OUT/'contexts.json');qs={q['id']:q for q in engine.load_queries(OUT)};rows=[]
    for j in b.read(OUT/'schedule.json'):
        if (OUT/j['path']).exists():
            r=engine.checked_record(OUT,j,qs,ctx,lock)
            rows.append({**b.record_metrics(r),'arm':ARM,'pair_key':j['pair_key']})
    summary={'complete':len(rows)==290,'saved':len(rows),'expected':290,'new_baseline_answers':0,
             'citation_count':sum(r['citation_inclusion'] for r in rows),
             'analysis_status':lock['analysis_status'],'comparison':None,'repeatability':None}
    if len(rows)==290:
        summary['comparison']=runner.comparison(rows+b.read(OUT/'historical_baseline_metrics.json'),ARM,'baseline_repeat')
        original=[{**m,'arm':'original_r5'} for m in b.read(OUT/'historical_r5_metrics.json')]
        summary['repeatability']=runner.comparison(rows+original,ARM,'original_r5')
    b.write(OUT/'metrics.json',rows);b.write(OUT/'summary.json',summary)
    print({k:v for k,v in summary.items() if k not in ('comparison','repeatability')},flush=True)

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='report':report()
    elif sys.argv[1]=='run':
        b.write(OUT/'run_state.json',{'stage':'running','at':datetime.now(timezone.utc).isoformat()})
        try:
            runner.run(OUT,4);report()
            b.write(OUT/'run_state.json',{'stage':'complete','at':datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            b.write(OUT/'run_state.json',{'stage':'failed','error':type(exc).__name__,'at':datetime.now(timezone.utc).isoformat()});raise
    else:raise ValueError('Unknown action')
