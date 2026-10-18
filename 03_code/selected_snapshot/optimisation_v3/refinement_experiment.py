"""Fresh baseline/r4/r5 comparison using the unchanged v2.1 engine.

Standalone orchestration leaves the historical experiment code and seals intact.
"""
import argparse,csv,itertools,json,os,random,shutil
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from geo_bench import baseline_v2 as b
from geo_bench.config import CONFIG
from geo_bench.api.observed import ObservedClient
from geo_bench.search.live_retriever import normalise_url
from . import experiment as engine
from .flight_first_refinement import ARM

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'results/baseline_v2_1_repeat_20260909'
PRIOR=ROOT/'results/v3_final_core_evaluation_20260920_r4_retry1'
RELEASE=ROOT/'results/v3_final_release_20260920_r5'
ARMS=('baseline_repeat','v3_final_core',ARM)
COMPARISONS=(('v3_final_core','baseline_repeat'),(ARM,'baseline_repeat'),(ARM,'v3_final_core'))


def verified_release():
    m=b.read(RELEASE/'validated_manifest.json')
    if b.digest({k:v for k,v in m.items() if k!='release_id'})!=m['release_id']:raise ValueError('Release seal mismatch')
    for n,h in m['artifacts'].items():
        if b.sha(RELEASE/n)!=h:raise ValueError('Release artifact drift: '+n)
    for n,h in m['code'].items():
        if b.sha(ROOT/n)!=h:raise ValueError('Release code drift: '+n)
    return m


def schedule_triplets(original,seed=20260920):
    rng=random.Random(seed);original=list(original);rng.shuffle(original)
    orders=list(itertools.permutations(ARMS));rng.shuffle(orders);jobs=[]
    for i,j in enumerate(original):
        for arm in orders[i%len(orders)]:
            jobs.append({**j,'arm':arm,'pair_key':j['key'],'key':arm+'__'+j['key'],
                         'path':'records/'+arm+'/'+j['key']+'.json'})
    return jobs


def prepare(out):
    if (out/'lock.json').exists():engine.validate(out);print('Existing package verified',flush=True);return
    release=verified_release();parent=b.validate_package(PARENT);prior=engine.validate(PRIOR)
    if prior['parent_id']!=parent['experiment_id'] or release['parent_id']!=parent['experiment_id']:raise ValueError('Parent mismatch')
    if b.hostname(os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'))!=parent['endpoint']:raise ValueError('Endpoint drift')
    identity={'parent_id':parent['experiment_id'],'prior_id':prior['experiment_id'],
              'release_id':release['release_id'],'embedding_model':CONFIG.embed_model,'code':release['code']}
    if out.exists() and any(out.iterdir()):
        if not (out/'preparation_identity.json').exists() or b.read(out/'preparation_identity.json')!=identity:
            raise ValueError('Unknown or changed partial preparation')
    out.mkdir(parents=True,exist_ok=True);b.write(out/'preparation_identity.json',identity)
    pages=b.read(PARENT/'pages.json');basepass=b.read(PARENT/'passages.json')
    basevec=np.load(PARENT/'vectors.npz')['vecs'];qvec=np.load(PARENT/'query_vectors.npz')['vecs']
    queries=list(csv.DictReader((PARENT/'queries.csv').open(encoding='utf-8')))
    original=b.read(PARENT/'schedule.json');oldcontexts=b.read(PRIOR/'contexts.json')
    if engine.new_passages(pages)!=basepass:raise ValueError('Baseline chunk identity failed')
    freshbase,_=engine.reindexed_contexts(basepass,basevec,queries,qvec)
    if any(v!=oldcontexts['baseline_repeat'][k] for k,v in freshbase.items()):raise ValueError('Baseline retrieval identity failed')
    priorpass=b.read(PRIOR/'passages.json');priorvec=np.load(PRIOR/'vectors.npz')['vecs']
    if engine.new_passages(b.read(PRIOR/'pages.json'))!=priorpass:raise ValueError('r4 chunk identity failed')
    freshr4,_=engine.reindexed_contexts(priorpass,priorvec,queries,qvec)
    if any(v!=oldcontexts['v3_final_core'][k] for k,v in freshr4.items()):raise ValueError('r4 retrieval identity failed')
    byquery={q['id']:q for q in queries}
    for j in original:
        baseline_prompt=b.planned_prompt(j,byquery,oldcontexts['baseline_repeat'],parent)[-1]
        historic=b.read(PARENT/j['path']);b.validate_record(historic,j,baseline_prompt,parent)
    print('Baseline and r4 chunk/context identity verified; all 800 parent prompts reproduced',flush=True)
    b.write(out/'identity_check.json',{'status':'PASS','parent_prompts':len(original),'baseline_chunks':len(basepass),
                                      'r4_chunks':len(priorpass),'baseline_retrieval_contexts':len(freshbase),'r4_retrieval_contexts':len(freshr4)})
    outputs=b.read(RELEASE/'outputs.json')
    if set(outputs)!={k for k,p in pages.items() if p['brand']==CONFIG.our_brand}:raise ValueError('Treatment URL coverage mismatch')
    treatments={}
    from .arms import sha as text_sha
    for k,p in pages.items():
        if p['brand']==CONFIG.our_brand:
            o=outputs[k]
            if o['arm']!=ARM or o['source_sha256']!=text_sha(p['text']):raise ValueError('Treatment baseline/arm mismatch')
            treatments[k]={**p,'text':o['clean']}
        else:treatments[k]=p
    if any(treatments[k]!=p for k,p in pages.items() if p['brand']!=CONFIG.our_brand):raise ValueError('Competitor changed')
    passages=engine.new_passages(treatments);lookup={}
    embedding_logs=b.read(PRIOR/'embedding_log.json')
    if any(x['requested_model']!=CONFIG.embed_model or x['returned_model']!=CONFIG.embed_model for x in embedding_logs):raise ValueError('r4 embedding model mismatch')
    for ps,vs in ((basepass,basevec),(priorpass,priorvec)):
        if len(ps)!=len(vs) or vs.shape[1]!=basevec.shape[1] or not np.isfinite(vs).all():raise ValueError('Cached vector shape/values invalid')
        for p,v in zip(ps,vs):lookup[(p['id'],p['file'],p['text'])]=v
    vectors=np.zeros((len(passages),basevec.shape[1]),dtype=np.float32)
    pending=[]
    for i,p in enumerate(passages):
        key=(p['id'],p['file'],p['text'])
        if key in lookup:vectors[i]=lookup[key]
        else:pending.append((i,p))
    print(f'Embedding {len(pending)} changed chunks; reuse {len(passages)-len(pending)} exact vectors',flush=True)
    from openai import OpenAI
    client=OpenAI(max_retries=2,timeout=90.0);log=[]
    for start in range(0,len(pending),64):
        batch=pending[start:start+64];names=[p['id'] for _,p in batch]
        inputs=b.digest([p['text'] for _,p in batch]);folder=out/'embedding_batches';folder.mkdir(exist_ok=True)
        meta_path=folder/f'{start:05d}.json';vec_path=folder/f'{start:05d}.npz'
        if meta_path.exists():
            meta=b.read(meta_path)
            if meta['input_sha256']!=inputs or meta['passage_ids']!=names or meta['vectors_sha256']!=b.sha(vec_path):raise ValueError('Embedding checkpoint changed')
            if meta['requested_model']!=CONFIG.embed_model or meta['returned_model']!=CONFIG.embed_model:raise ValueError('Checkpoint model drift')
            arr=np.load(vec_path)['vectors']
        else:
            response=client.embeddings.create(model=CONFIG.embed_model,input=[p['text'] for _,p in batch])
            ds=sorted(response.data,key=lambda d:d.index)
            if [d.index for d in ds]!=list(range(len(batch))) or response.model!=CONFIG.embed_model:raise ValueError('Embedding provider mismatch')
            arr=np.asarray([d.embedding for d in ds],dtype=np.float32)
            with vec_path.open('wb') as f:np.savez(f,vectors=arr)
            meta={'input_sha256':inputs,'passage_ids':names,'requested_model':CONFIG.embed_model,'returned_model':response.model,
                  'usage':response.usage.model_dump(),'request_id':getattr(response,'_request_id',None),'vectors_sha256':b.sha(vec_path)}
            b.write(meta_path,meta)
        norms=np.linalg.norm(arr,axis=1)
        if arr.shape!=(len(batch),basevec.shape[1]) or not np.isfinite(arr).all() or np.any(norms<.99) or np.any(norms>1.01):raise ValueError('Invalid new vectors')
        for (i,_),v in zip(batch,arr):vectors[i]=v
        log.append(meta);print(f'Embedded/verified {min(start+64,len(pending))}/{len(pending)}',flush=True)
    newcontexts,traces=engine.reindexed_contexts(passages,vectors,queries,qvec)
    for key,pool in oldcontexts['baseline_repeat'].items():
        if key.endswith('/fixed'):
            newcontexts[key]=[{**p,'text':treatments[normalise_url(p['file'])]['text'],
                               'words':len(treatments[normalise_url(p['file'])]['text'].split())} if p['brand']==CONFIG.our_brand else p for p in pool]
            if len({p['text'] for p in newcontexts[key]})!=len(pool):raise ValueError('Duplicate fixed texts')
    contexts={**oldcontexts,ARM:newcontexts}
    if set(contexts)!=set(ARMS):raise ValueError('Unexpected conditions')
    for n in ('queries.csv','query_vectors.npz','environment.json','requirements-lock.txt'):
        shutil.copy2(PARENT/n,out/n)
    for name,data in [('pages.json',treatments),('passages.json',passages),('contexts.json',contexts),('retrieval_trace.json',traces),
                      ('embedding_log.json',log),('schedule.json',schedule_triplets(original)),('release_manifest.json',release)]:b.write(out/name,data)
    np.savez(out/'vectors.npz',vecs=vectors)
    b.write(out/'context_delivery.json',[{'pair_key':j['key'],'query_id':j['query_id'],'variant':j['variant'],
        'r5_prompt_differs_from_r4':b.planned_prompt(j,byquery,contexts[ARM],parent)[-1]!=b.planned_prompt(j,byquery,contexts['v3_final_core'],parent)[-1]} for j in original])
    lock={'version':'r5-three-condition','parent_path':str(PARENT),'parent_id':parent['experiment_id'],'prior_experiment_id':prior['experiment_id'],
          'release_id':release['release_id'],'model':parent['model'],'endpoint':parent['endpoint'],'policy':parent['policy'],
          'control_generation':'fresh_interleaved_triplets','arms':list(ARMS),'expected_records':3*len(original),
          'scheduling_seed':20260920,'within_triplet_orders':'balanced six permutations; original job order shuffled',
          'analysis_status':'exploratory development; fixed incremental focus does not replace locked primary endpoint','code':release['code']}
    for n in lock['code']:
        dst=out/'code'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,dst)
    lock['artifacts']={p.relative_to(out).as_posix():b.sha(p) for p in out.rglob('*') if p.is_file()}
    lock['experiment_id']=b.digest(lock);b.write(out/'lock.json',lock)
    print(f'PREPARED {lock["expected_records"]} fresh answers: {lock["experiment_id"]}',flush=True)


def comparison(rows,treatment,control):
    groups=defaultdict(dict)
    for r in rows:
        if r['arm'] in (treatment,control):groups[r['pair_key']][r['arm']]=r
    if not groups or any(set(g)!={treatment,control} for g in groups.values()):return None
    result={}
    for metric in ('citation_inclusion','citation_share','retrieval_inclusion'):
        byquery=defaultdict(list)
        for g in groups.values():
            c,t=g[control],g[treatment];byquery[c['query_id']].append((c[metric],t[metric]))
        qrows=[{'query_id':q,'control':float(np.mean([v[0] for v in vals])),
                'treatment':float(np.mean([v[1] for v in vals]))} for q,vals in sorted(byquery.items())]
        d=np.array([q['treatment']-q['control'] for q in qrows]);rng=np.random.default_rng(20260908)
        boot=np.mean(rng.choice(d,size=(5000,len(d)),replace=True),axis=1)
        result[metric]={'control_arm':control,'treatment_arm':treatment,'queries':len(qrows),'pairs':len(groups),
                        'control':float(np.mean([q['control'] for q in qrows])),
                        'treatment':float(np.mean([q['treatment'] for q in qrows])),
                        'difference':float(d.mean()),'paired_query_bootstrap_95':np.quantile(boot,[.025,.975]).tolist(),
                        'interval_interpretation':'unadjusted exploratory interval','per_query':qrows}
    return result


def report(out):
    lock=engine.validate(out,check_code=False);contexts=b.read(out/'contexts.json')
    queries={q['id']:q for q in engine.load_queries(out)};jobs=b.read(out/'schedule.json');metrics=[];apis=defaultdict(list)
    for j in jobs:
        if not (out/j['path']).exists():continue
        r=engine.checked_record(out,j,queries,contexts,lock)
        m=b.record_metrics(r);m.update(arm=j['arm'],pair_key=j['pair_key']);metrics.append(m);apis[j['arm']].append(r['api'])
    counts=Counter(m['arm'] for m in metrics)
    summary={'experiment_id':lock['experiment_id'],'complete':len(metrics)==len(jobs),'saved':len(metrics),'expected':len(jobs),
             'counts':dict(counts),'control_generation':lock['control_generation'],'analysis_status':lock['analysis_status'],
             'quality_checks':{'empty':sum(m['answer_empty'] for m in metrics),'invalid_citations':sum(m['invalid_citation_count'] for m in metrics),
                               'unsupported_grouped_citations':sum(m['unsupported_grouped_citations'] for m in metrics),
                               'finish_reasons':dict(Counter(m['finish_reason'] for m in metrics))},
             'provider_provenance':{a:{'returned_models':dict(Counter(r['returned_model'] for r in rs)),
                                      'first_request':min(r['attempts'][0]['started_at'] for r in rs),
                                      'last_request':max(r['attempts'][0]['started_at'] for r in rs)} for a,rs in apis.items()},'comparisons':{}}
    for variant in ('fixed','reindexed'):
        for stratum in ('primary','all'):
            rows=[m for m in metrics if m['variant']==variant and (stratum=='all' or m['stratum']=='primary')]
            for t,c in COMPARISONS:
                stats=comparison(rows,t,c)
                if stats is not None:summary['comparisons'][f'{t}_vs_{c}/{variant}/{stratum}']=stats
    b.write(out/'metrics.json',metrics);b.write(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='comparisons'},indent=2),flush=True)


def run(out,workers):
    lock=engine.validate(out)
    if b.hostname(os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'))!=lock['endpoint']:raise ValueError('Endpoint drift')
    contexts=b.read(out/'contexts.json');queries={q['id']:q for q in engine.load_queries(out)}
    jobs=b.read(out/'schedule.json');pending=defaultdict(list)
    for j in jobs:
        if (out/j['path']).exists():engine.checked_record(out,j,queries,contexts,lock)
        else:pending[j['pair_key']].append(j)
    print(f'Pending {sum(map(len,pending.values()))}/{len(jobs)} answers; {workers} triplet workers',flush=True)
    def execute(triplet):
        for j in triplet:
            row,pool,ordered,budget,prompt=engine.planned(j,queries,contexts,lock)
            answer=ObservedClient(lock['model']).generate(prompt)
            record={**j,'experiment_id':lock['experiment_id'],'parent_id':lock['parent_id'],'query':row['query'],
                    'stratum':row.get('stratum',''),'group':row.get('group',''),'prompt':prompt,'prompt_sha256':b.digest(prompt.encode()),
                    'sources':[{'id':p.id,'url':p.file,'brand':p.brand,'text':p.text[:budget],'original_chars':len(p.text)} for p in ordered],
                    'pool_ids':[p['id'] for p in pool],'pool_brands':[p['brand'] for p in pool],**answer}
            record['record_sha256']=b.digest(record);b.write(out/j['path'],record);print('SAVED '+j['key'],flush=True)
    marker=out/'RUNNING'
    with marker.open('x') as f:f.write(str(os.getpid()))
    try:
        groups=list(pending.values())
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for start in range(0,len(groups),workers):
                futures=[executor.submit(execute,g) for g in groups[start:start+workers]]
                for future in as_completed(futures):future.result()
    except Exception as exc:
        b.write(out/'failure.json',{'error':type(exc).__name__,'message':str(exc)[:1000],'at':datetime.now(timezone.utc).isoformat()});raise
    finally:marker.unlink()
    report(out)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','verify','report'])
    p.add_argument('--output',type=Path,default=ROOT/'results/v3_final_flight_first_r5_evaluation_20260920')
    p.add_argument('--workers',type=int,default=4);p.add_argument('--allow-generation',action='store_true');a=p.parse_args()
    if not 1<=a.workers<=8:p.error('workers must be 1..8')
    if a.action=='prepare':prepare(a.output)
    elif a.action=='run':
        if not a.allow_generation:p.error('Explicit generation authorization required')
        run(a.output,a.workers)
    elif a.action=='report':report(a.output)
    else:print(engine.validate(a.output)['experiment_id'])


if __name__=='__main__':main()
