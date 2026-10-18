"""Versioned overlay, paired execution and reporting on the unchanged v2.1 engine."""
from __future__ import annotations
import argparse, csv, json, os, random, shutil, zipfile
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
import numpy as np
from rank_bm25 import BM25Okapi
from geo_bench import baseline_v2 as base
from geo_bench.config import CONFIG
from geo_bench.experiment.run_store import url_hash
from geo_bench.retrieval.chunker import make_passages
from geo_bench.api.offline_client import tokenize
from geo_bench.api.observed import ObservedClient
from geo_bench.search.live_retriever import normalise_url
from .arms import Source, rendered, semantic_rendered, quoted, full_stack, autogeo_rewrite, validate_output, ACTIVE, DEFERRED, RETIRED, sha as text_sha
from .remaining import load_external, attribution, oracle_repetition
from .rendered_selective import selective_rendered
from .schema_structured import structured_schema
from .rendered_organisation import organise_rendered
from .faq_refinement import refined_faq
from .structured_refinement import refined_structured, route_structured
from .external_refinement import refined_external
from .schema_representation import schema_identity
from .coherent_refinement import coherent_rendered, useful_external, RENDERED_ARM, EXTERNAL_ARM
from .final_release import RELEASE_ARMS

AVAILABLE_ARMS=tuple(ACTIVE)+RELEASE_ARMS

ROOT=Path(__file__).resolve().parents[1]
ARMS=('baseline_repeat','rendered_content_exposure')
RUN_ARM='rendered_content_exposure'

def new_passages(pages):
    passages=[];seen=set()
    for p in pages.values():
        for chunk in make_passages(p['text'],p['brand'],p['url'],CONFIG):
            key=(chunk.file,chunk.text)
            if key in seen:continue
            seen.add(key);passages.append(asdict(chunk))
    return passages

def reindexed_contexts(passages,vectors,queries,qvecs):
    bm=BM25Okapi([tokenize(p['text']) for p in passages],k1=CONFIG.bm25_k1,b=CONFIG.bm25_b)
    contexts={};traces={}
    for i,q in enumerate(queries):
        selected,trace=base.rank_pool(passages,vectors,bm,qvecs[i],q['query'])
        contexts[q['id']+'/reindexed']=selected;traces[q['id']]=trace
    return contexts,traces

def load_queries(out):
    return list(csv.DictReader((out/'queries.csv').open(encoding='utf-8')))

def validate(out,check_code=True):
    lock=base.read(out/'lock.json')
    if base.digest({k:v for k,v in lock.items() if k!='experiment_id'})!=lock['experiment_id']:
        raise ValueError('Experiment lock mismatch')
    parent=base.validate_package(Path(lock['parent_path']))
    if parent['experiment_id']!=lock['parent_id']:raise ValueError('Parent changed')
    for name,h in lock['artifacts'].items():
        if base.sha(out/name)!=h:raise ValueError('Artifact drift: '+name)
    if check_code:
        for name,h in lock['code'].items():
            if base.sha(ROOT/name)!=h:raise ValueError('Optimisation code drift: '+name)
    paths={j['path'] for j in base.read(out/'schedule.json')}
    actual={p.relative_to(out).as_posix() for p in (out/'records').glob('*/*.json')}
    if actual-paths:raise ValueError('Unscheduled records')
    return lock

def prepare(out,parent,embedding_cache=None,arm='v3_final_core',fresh_controls=False,allow_legacy=False):
    global ARMS,RUN_ARM
    if arm not in AVAILABLE_ARMS: raise ValueError('Unknown optimisation arm: '+arm)
    if arm in RELEASE_ARMS and not fresh_controls:
        raise ValueError('Final release experiments require --fresh-controls')
    RUN_ARM=arm; ARMS=('baseline_repeat',arm)
    if (out/'lock.json').exists():validate(out);print('Existing package verified',flush=True);return
    if arm not in RELEASE_ARMS and arm!='position_control' and not allow_legacy:
        raise ValueError('Historical/diagnostic builder: use a final-release arm, or explicitly --allow-legacy-preparation for reproduction. Never combine oracle or rewrite with the core.')
    if out.exists() and any(out.iterdir()):raise ValueError('Use an empty output; no overwriting partial preparation')
    plock=base.validate_package(parent)
    release_outputs=None
    if arm in RELEASE_ARMS:
        release=ROOT/'results/v3_final_release_20260920_r4'
        manifest=base.read(release/'validated_manifest.json')
        if base.digest({k:v for k,v in manifest.items() if k!='release_id'})!=manifest['release_id']:
            raise ValueError('Release identity changed')
        if manifest['parent_id']!=plock['experiment_id']:raise ValueError('Release baseline mismatch')
        for name,h in manifest['artifacts'].items():
            if base.sha(release/name)!=h:raise ValueError('Release artifact changed: '+name)
        for name,h in manifest['code'].items():
            if base.sha(ROOT/name)!=h:raise ValueError('Release code changed: '+name)
        release_outputs=base.read(release/(arm+'.json'))
    if base.hostname(os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'))!=plock['endpoint']:
        raise ValueError('Preparation endpoint differs from baseline')
    out.mkdir(parents=True,exist_ok=True)
    if release_outputs is not None:
        shutil.copy2(release/'validated_manifest.json',out/'release_manifest.json')
    pages=base.read(parent/'pages.json');pcontexts=base.read(parent/'contexts.json')
    passages=base.read(parent/'passages.json');vecs=np.load(parent/'vectors.npz')['vecs']
    qvecs=np.load(parent/'query_vectors.npz')['vecs'];queries=load_queries(parent)
    byqid={q['id']:q for q in queries};schedule=base.read(parent/'schedule.json')
    # A mandatory complete identity overlay, including original query/prompt pairing.
    if new_passages(pages)!=passages:raise ValueError('Identity chunk mismatch')
    identity,_=reindexed_contexts(passages,vecs,queries,qvecs)
    for key,pool in identity.items():
        if pool!=pcontexts[key]:raise ValueError('Identity retrieval mismatch: '+key)
    identity.update({k:v for k,v in pcontexts.items() if k.endswith('/fixed')})
    for job in schedule:
        prompt=base.planned_prompt(job,byqid,identity,plock)[-1]
        rec=base.read(parent/job['path']);base.validate_record(rec,job,prompt,plock)
    base.write(out/'identity_check.json',{'chunks':len(passages),'contexts':len(identity),'prompts':len(schedule),'status':'PASS'})
    for name in ('queries.csv','query_vectors.npz','environment.json','requirements-lock.txt'):
        shutil.copy2(parent/name,out/name)
    facts=list(csv.DictReader(CONFIG.facts_file.open(encoding='utf-8')))
    coherent_reviewed=None;coherent_evidence=None
    if arm in (RENDERED_ARM,EXTERNAL_ARM):
        review_dir=ROOT/'results/coherent_refinements_20260914_v2'
        manifest=base.read(review_dir/'manifest.json')
        if manifest['baseline_id']!=plock['experiment_id']:raise ValueError('Refinement baseline mismatch')
        if manifest['code_sha256']!=base.sha(ROOT/'optimisation_v3/coherent_refinement.py'):raise ValueError('Frozen refinement code changed')
        if base.sha(review_dir/(arm+'.json'))!=manifest['outputs'][arm]:raise ValueError('Refinement outputs changed')
        for name,h in manifest['source_artifacts'].items():
            if base.sha(review_dir/name)!=h:raise ValueError('External source changed')
        coherent_reviewed=base.read(review_dir/(arm+'.json'))
        coherent_evidence=base.read(review_dir/'evidence.json')
        shutil.copytree(review_dir,out/'content_review')
    faq_reviewed=None
    if arm in ('page_grounded_faq_refined','structured_product_facts_refined','structured_product_facts_route'):
        reviewed_dir=ROOT/'results'/({'page_grounded_faq_refined':'faq_refinement_v1','structured_product_facts_refined':'structured_refinement_v1','structured_product_facts_route':'structured_route_v1'}[arm])
        manifest=base.read(reviewed_dir/'manifest.json')
        if manifest['baseline_id']!=plock['experiment_id']:raise ValueError('FAQ baseline differs from review')
        for name in ('outputs','facts'):
            if base.sha(reviewed_dir/(name+'.json'))!=manifest[name+'_sha256']:raise ValueError('FAQ reviewed artifact drift')
        faq_reviewed=base.read(reviewed_dir/'outputs.json')
        facts=base.read(reviewed_dir/'facts.json')
    external_obj=load_external(ROOT/'results/remaining_methods_v3/external_source') if arm=='full_stack_exploratory' else None
    reviewed_outputs=None
    if arm=='rendered_content_organised':
        reviewed=ROOT/'results/rendered_organisation_refinement_v1'
        manifest=base.read(reviewed/'manifest.json')
        if base.digest({k:v for k,v in manifest.items() if k!='identity'})!=manifest['identity']:
            raise ValueError('Refinement manifest changed')
        if manifest['baseline_id']!=plock['experiment_id']:
            raise ValueError('Refinement reviewed against a different baseline')
        if base.sha(reviewed/'outputs.json')!=manifest['artifacts']['outputs.json']:
            raise ValueError('Reviewed refinement bytes changed')
        reviewed_outputs=base.read(reviewed/'outputs.json')
    base.write(out/'facts.json',facts)
    autogeo_review=None
    schema_reviewed=None
    if arm=='schema_page_identity':
        review_dir=ROOT/'results/schema_page_identity_review_v2'
        manifest=base.read(review_dir/'manifest.json')
        if manifest['parent_id']!=plock['experiment_id']:raise ValueError('Schema parent mismatch')
        if base.sha(review_dir/'outputs.json')!=manifest['outputs_sha256']:raise ValueError('Schema review changed')
        schema_reviewed=base.read(review_dir/'outputs.json')
        shutil.copy2(review_dir/'manifest.json',out/'schema_review_manifest.json')
        shutil.copy2(ROOT/'SCHEMA_PAGE_IDENTITY_PROTOCOL.md',out/'schema_protocol.md')
    if arm=='autogeo_rewrite_exploratory':
        review_path=ROOT/'results/autogeo_user_review_20260913/review.json'
        autogeo_review=base.read(review_path)
        prior_outputs=ROOT/'results/optimisation_v3_autogeo_ready2/built_arms/autogeo_rewrite_exploratory.json'
        if base.sha(prior_outputs)!=autogeo_review['outputs_sha256']:raise ValueError('User-reviewed rewrite package changed')
        shutil.copy2(review_path,out/'user_review.json')
    external_reviewed=None;external_frozen=None
    if arm=='external_source_attribution_refined':
        review_dir=ROOT/'results/external_refinement_v2'
        manifest=base.read(review_dir/'manifest.json')
        if manifest['baseline_id']!=plock['experiment_id']:raise ValueError('External review baseline mismatch')
        if base.sha(review_dir/'outputs.json')!=manifest['outputs_sha256']:raise ValueError('External reviewed output drift')
        shutil.copytree(review_dir/'source',out/'external_source')
        external_frozen=load_external(out/'external_source');external_reviewed=base.read(review_dir/'outputs.json')
    oracle_reviewed=None;oracle_map=None;oracle_query_text=None
    if arm=='oracle_query_repetition':
        # Frozen research build is the reviewed reference; rebuild must match byte-for-byte.
        research=ROOT/'results/remaining_methods_v3'
        oracle_reviewed=base.read(research/'built_arms/oracle_query_repetition.json')
        oracle_map=base.read(research/'oracle_query_mapping.json')
        oracle_query_text={q['id']:q['query'] for q in load_queries(parent)}
        shutil.copy2(research/'oracle_query_mapping.json',out/'oracle_query_mapping.json')
    source=ROOT/CONFIG.runs_dir/plock['source_run']
    treatments={};arm_outputs={a:{} for a in AVAILABLE_ARMS};delivery=[]
    print('Validating and freezing 52 rendered replacements and retained quoted arms ...',flush=True)
    with zipfile.ZipFile(parent/'source_snapshot.zip') as original, zipfile.ZipFile(out/'render_captures.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for key,p in pages.items():
            if p['brand']!=CONFIG.our_brand:continue
            h=url_hash(p['url']);raw=original.read('pages/'+h+'/raw.html').decode('utf-8')
            s=Source(p['url'],raw,p['text'])
            if release_outputs is not None:
                o=release_outputs[key]
                if o['source_sha256']!=text_sha(s.clean) or o['arm']!=arm:
                    raise ValueError('Release source/arm mismatch')
                if text_sha(o['html'])!=o['raw_sha256'] or text_sha(o['clean'])!=o['clean_sha256']:
                    raise ValueError('Release output hash mismatch')
                arm_outputs[arm][key]=o
            if arm=='schema_page_identity':
                sc=schema_identity(s)
                if sc!=schema_reviewed[key]:raise ValueError('Schema differs from reviewed output')
                arm_outputs[arm][key]=sc
            if arm=='external_source_attribution_refined':
                e=refined_external(s,external_frozen)
                if e!=external_reviewed[key]:raise ValueError('External refinement differs from reviewed output')
                arm_outputs[arm][key]=e
            if arm in ('page_grounded_faq_refined','structured_product_facts_refined','structured_product_facts_route'):
                refined={'page_grounded_faq_refined':refined_faq,'structured_product_facts_refined':refined_structured,'structured_product_facts_route':route_structured}[arm](s,facts)
                if refined!=faq_reviewed[key]:raise ValueError('FAQ differs from reviewed frozen output')
                arm_outputs[arm][key]=refined
            path=source/'arms/ssr_visible/rendered_raw'/h
            capture=(path/'rendered.html').read_bytes();meta=base.read(path/'meta.json')
            for name in ('rendered.html','meta.json'):archive.write(path/name,h+'/'+name)
            r=rendered(s,capture,meta);validate_output(r,rendered(s,capture,meta))
            arm_outputs['rendered_content_exposure'][key]=r
            sr=semantic_rendered(s,capture,meta);arm_outputs['rendered_content_semantic'][key]=sr
            if arm=='rendered_content_selective':
                sel=selective_rendered(s,capture,meta)
                if sel!=selective_rendered(s,capture,meta):raise ValueError('Selective render is not deterministic: '+key)
                arm_outputs[arm][key]=sel
            if arm in (RENDERED_ARM,EXTERNAL_ARM):
                refined=coherent_rendered(s,capture,meta) if arm==RENDERED_ARM else useful_external(s,coherent_evidence)
                if refined!=coherent_reviewed[key]:raise ValueError('Refinement differs from frozen review')
                arm_outputs[arm][key]=refined
            if arm=='rendered_content_organised':
                refined=organise_rendered(s,capture,meta)
                if refined!=reviewed_outputs[key]:
                    raise ValueError('Refinement differs from reviewed content: '+key)
                arm_outputs[arm][key]=refined
            if arm=='oracle_query_repetition':
                qids=oracle_map.get(key,[])
                missing=[q for q in qids if q not in oracle_query_text]
                if missing:raise ValueError('Oracle mapping names unknown queries: '+','.join(missing))
                o=oracle_repetition(s,[oracle_query_text[q] for q in qids])
                if o!=oracle_reviewed[key]:
                    raise ValueError('Oracle repetition differs from frozen research build: '+key)
                arm_outputs[arm][key]=o
            if arm=='schema_structured_markup':
                sc=structured_schema(s,facts)
                if sc!=structured_schema(s,facts):
                    raise ValueError('Structured schema is not deterministic: '+key)
                arm_outputs[arm][key]=sc
            if arm=='full_stack_exploratory':
                fs=full_stack(s,capture,meta,facts,external_obj);validate_output(fs,full_stack(s,capture,meta,facts,external_obj));arm_outputs[arm][key]=fs
            treatments[key]={**p,'text':r['clean']}
            for built_name in ('page_grounded_faq','fare_clarification','structured_product_facts','verified_quantitative_facts'):
                if built_name not in arm_outputs:continue
                o=quoted(s,facts,built_name);validate_output(o,quoted(s,facts,built_name));arm_outputs[built_name][key]=o
            if 'autogeo_rewrite_exploratory' in arm_outputs:
                ap=ROOT/'results/autogeo_exploratory_ready/rewrites'
                matches=[x for x in ap.glob('*.json') if base.read(x).get('page_key')==key]
                if len(matches)>1:raise ValueError('Duplicate automatic rewrite for '+key)
                if matches:
                    ao=base.read(matches[0])
                    validated=autogeo_rewrite(s,ao['html'],{'source_url':ao.get('url'),'rewriter_model':ao.get('notes',{}).get('rewriter_model',''),'rewritten_at':ao.get('notes',{}).get('rewritten_at','')})
                    if any(ao.get(k)!=validated.get(k) for k in ('url','clean','source_sha256','raw_sha256','clean_sha256')):
                        raise ValueError('AutoGEO frozen rewrite failed deterministic validation: '+key)
                    arm_outputs['autogeo_rewrite_exploratory'][key]={**validated,'notes':{**validated['notes'],'page_key':key,'response_id':ao.get('response_id','')}}
                else:
                    arm_outputs['autogeo_rewrite_exploratory'][key]={'arm':'autogeo_rewrite_exploratory','url':p['url'],'html':raw,'clean':p['text'],'source_sha256':text_sha(p['text']),'raw_sha256':text_sha(raw),'clean_sha256':text_sha(p['text']),'evidence':[],'notes':{'explicit_noop':'AutoGEO rewrite rejected; baseline retained'}}
                if autogeo_review and arm_outputs['autogeo_rewrite_exploratory'][key]['clean_sha256']!=autogeo_review['reviewed_content_hashes'][key]:
                    raise ValueError('Automatic rewrite differs from user-reviewed content')
            if 'external_source_attribution' in arm_outputs:
                ep=ROOT/'results/remaining_methods_v3/built_arms/external_source_attribution.json'
                ev=base.read(ep) if ep.exists() else {}
                e=ev.get(key)
                if e is None:
                    e=next((v for v in ev.values() if normalise_url(v.get('url',''))==normalise_url(p['url'])),None)
                if e is not None:
                    ext=load_external(ROOT/'results/remaining_methods_v3/external_source')
                    expected=attribution(s,ext,True)
                    if any(e.get(k)!=expected.get(k) for k in ('url','clean','source_sha256','raw_sha256','clean_sha256','evidence')):
                        raise ValueError('External attribution frozen output failed deterministic validation: '+key)
                    arm_outputs['external_source_attribution'][key]=e
                else: arm_outputs['external_source_attribution'][key]={'arm':'external_source_attribution','url':p['url'],'html':raw,'clean':p['text'],'source_sha256':text_sha(p['text']),'raw_sha256':text_sha(raw),'clean_sha256':text_sha(p['text']),'evidence':[],'notes':{'explicit_noop':'no eligible external source'}}
            if 'external_fact_only' in arm_outputs:
                fp=ROOT/'results/remaining_methods_v3/built_arms/external_fact_only.json'
                fv=base.read(fp) if fp.exists() else {}
                fe=fv.get(key)
                if fe is None:
                    fe=next((v for v in fv.values() if normalise_url(v.get('url',''))==normalise_url(p['url'])),None)
                if fe is not None:
                    ext=load_external(ROOT/'results/remaining_methods_v3/external_source')
                    fexpected=attribution(s,ext,False)
                    if any(fe.get(k)!=fexpected.get(k) for k in ('url','clean','source_sha256','raw_sha256','clean_sha256','evidence')):
                        raise ValueError('External fact-only frozen output failed deterministic validation: '+key)
                    arm_outputs['external_fact_only'][key]=fe
                else: arm_outputs['external_fact_only'][key]={'arm':'external_fact_only','url':p['url'],'html':raw,'clean':p['text'],'source_sha256':text_sha(p['text']),'raw_sha256':text_sha(raw),'clean_sha256':text_sha(p['text']),'evidence':[],'notes':{'explicit_noop':'no eligible external source'}}
            delivery.append({'url':p['url'],'baseline_chars':len(s.clean),'rendered_chars':len(r['clean']),
                             'changed':s.clean!=r['clean'],'captured_at':meta['rendered_at']})
    for built_name,outputs in arm_outputs.items():base.write(out/'built_arms'/(built_name+'.json'),outputs)
    if arm=='position_control':
        treatments={k:p for k,p in pages.items()}
    elif arm!='rendered_content_exposure':
        byurl={normalise_url(v['url']):v for v in arm_outputs[arm].values()}
        treatments={k:({**p,'text':byurl[normalise_url(p['url'])]['clean']} if p['brand']==CONFIG.our_brand else p) for k,p in pages.items()}
    for key,p in pages.items():
        if key not in treatments:treatments[key]=p
    # Preserve original corpus iteration order and exact competitor content.
    treatments={k:treatments[k] for k in pages}
    if any(treatments[k]!=p for k,p in pages.items() if p['brand']!=CONFIG.our_brand):raise ValueError('Competitor changed')
    tpassages=new_passages(treatments)
    lookup={(p['id'],p['file'],p['text']):v for p,v in zip(passages,vecs)}
    cache_record={}
    if embedding_cache is not None:
        cached=base.read(embedding_cache/'lock.json')
        if base.digest({k:v for k,v in cached.items() if k!='experiment_id'})!=cached['experiment_id']:raise ValueError('Cache identity mismatch')
        for name in ('passages.json','vectors.npz','embedding_log.json'):
            if base.sha(embedding_cache/name)!=cached['artifacts'][name]:raise ValueError('Cache bytes changed')
        if cached['parent_id'] not in (plock['experiment_id'],plock.get('repeat_of')):raise ValueError('Cache belongs to different parent')
        if cached['endpoint']!=plock['endpoint']:raise ValueError('Cache endpoint mismatch')
        log=base.read(embedding_cache/'embedding_log.json')
        if any(r['requested_model']!=CONFIG.embed_model or r['returned_model']!=CONFIG.embed_model for r in log):raise ValueError('Cache embedding model mismatch')
        cp=base.read(embedding_cache/'passages.json');cv=np.load(embedding_cache/'vectors.npz')['vecs']
        if cv.shape!=(len(cp),vecs.shape[1]) or not np.isfinite(cv).all():raise ValueError('Cache vectors invalid')
        for p,v in zip(cp,cv):
            key=(p['id'],p['file'],p['text'])
            if key not in lookup:lookup[key]=v
        cache_record={'experiment_id':cached['experiment_id'],'artifacts':{name:cached['artifacts'][name] for name in ('passages.json','vectors.npz','embedding_log.json')}}
    base.write(out/'embedding_cache_reuse.json',cache_record)
    pending=[(i,p) for i,p in enumerate(tpassages) if (p['id'],p['file'],p['text']) not in lookup]
    vectors=np.zeros((len(tpassages),vecs.shape[1]),dtype=np.float32)
    for i,p in enumerate(tpassages):
        key=(p['id'],p['file'],p['text'])
        if key in lookup:vectors[i]=lookup[key]
    # Same embedding model and dimensions as baseline, no silent fallback.
    from openai import OpenAI
    client=OpenAI(max_retries=2,timeout=90.0);embedding_log=[]
    print(f'Embedding {len(pending)} changed chunks; reusing {len(tpassages)-len(pending)} exact vectors',flush=True)
    for start in range(0,len(pending),64):
        batch=pending[start:start+64]
        response=client.embeddings.create(model=CONFIG.embed_model,input=[p['text'] for _,p in batch])
        data=sorted(response.data,key=lambda d:d.index)
        if [d.index for d in data]!=list(range(len(batch))):raise ValueError('Embedding indices missing/duplicated')
        for (i,p),d in zip(batch,data):
            v=np.asarray(d.embedding,dtype=np.float32)
            if v.shape!=(vectors.shape[1],) or not np.isfinite(v).all() or np.linalg.norm(v)<.99 or np.linalg.norm(v)>1.01:raise ValueError('Invalid embedding')
            vectors[i]=v
        embedding_log.append({'requested_model':CONFIG.embed_model,'returned_model':response.model,
                              'usage':response.usage.model_dump(),'request_id':getattr(response,'_request_id',None),
                              'passage_ids':[p['id'] for _,p in batch]})
        base.write(out/'embedding_log.json',embedding_log)
        print(f'Embedded {min(start+64,len(pending))}/{len(pending)}',flush=True)
    tcontexts,traces=reindexed_contexts(tpassages,vectors,queries,qvecs)
    for key,pool in pcontexts.items():
        if not key.endswith('/fixed'):continue
        tcontexts[key]=[{**p,'text':treatments[base.normalise_url(p['file'])]['text'],
                        'words':len(treatments[base.normalise_url(p['file'])]['text'].split())} if p['brand']==CONFIG.our_brand else p for p in pool]
        if len({p['text'] for p in tcontexts[key]})!=len(pool):raise ValueError('Treatment created duplicate fixed texts; explicit policy required')
    base.write(out/'pages.json',treatments);base.write(out/'passages.json',tpassages)
    np.savez(out/'vectors.npz',vecs=vectors)
    if arm=='position_control':
        # Keep baseline pool order. planned() applies the sole position change
        # after the common shuffle, preserving every competitor's relative order.
        base.write(out/'contexts.json',{'baseline_repeat':pcontexts,arm:pcontexts})
    else:
        base.write(out/'contexts.json',{'baseline_repeat':pcontexts,arm:tcontexts})
    base.write(out/'retrieval_trace.json',traces);base.write(out/'delivery.json',delivery)
    jobs=[]
    for j in schedule:
        jobs.append({**j,'arm':arm,'pair_key':j['key'],'key':arm+'__'+j['key'],'path':'records/'+arm+'/'+j['key']+'.json'})
        if fresh_controls:
            jobs.append({**j,'arm':'baseline_repeat','pair_key':j['key'],'key':'baseline_repeat__'+j['key'],'path':'records/baseline_repeat/'+j['key']+'.json'})
    if fresh_controls:
        # Deterministically randomise pair order and within-pair request order.
        # These are scheduling seeds, not model sampling seeds.
        rng=random.Random(20260914)
        paired=[jobs[i:i+2] for i in range(0,len(jobs),2)]
        for pair in paired:rng.shuffle(pair)
        rng.shuffle(paired)
        jobs=[j for pair in paired for j in pair]
    base.write(out/'schedule.json',jobs)
    delivery_context=[]
    for j in schedule:
        old=base.planned_prompt(j,byqid,pcontexts,plock)[-1];new=base.planned_prompt(j,byqid,tcontexts,plock)[-1]
        delivery_context.append({'key':j['key'],'query_id':j['query_id'],'variant':j['variant'],
                                 'prompt_changed':old!=new,'fc_context_sources':sum(p['brand']==CONFIG.our_brand for p in tcontexts[j['query_id']+'/'+j['variant']])})
    base.write(out/'context_delivery.json',delivery_context)
    lock={'version':'3.1.0','parent_path':str(parent.resolve()),'parent_id':plock['experiment_id'],
          'control_generation':'fresh_interleaved' if fresh_controls else 'historical_parent',
          'model':plock['model'],'endpoint':plock['endpoint'],'policy':plock['policy'],
          'active_arms':list(ACTIVE),'deferred':DEFERRED,'retired':list(RETIRED),'expected_records':len(jobs),
          'code':{p.relative_to(ROOT).as_posix():base.sha(p) for p in sorted((ROOT/'optimisation_v3').glob('*.py'))+[ROOT/'OPTIMISATION_V3_PROTOCOL.md']}}
    for name in lock['code']:
        dest=out/'code'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    lock['artifacts']={p.relative_to(out).as_posix():base.sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    lock['experiment_id']=base.digest(lock);base.write(out/'lock.json',lock)
    print(f'PREPARED {len(jobs)} responses, identity={lock["experiment_id"]}',flush=True)

def planned(j,queries,contexts,lock):
    """Build the exact prompt; position control is applied after shuffling."""
    row,pool,ordered,budget,prompt=base.planned_prompt(j,queries,contexts[j['arm']],lock)
    if j['arm']=='position_control':
        target=next((p for p in ordered if p.brand==CONFIG.our_brand),None)
        if target is not None:
            ordered=[target]+[p for p in ordered if p is not target]
            prompt=base.build_prompt(row['query'],ordered,max_chars=budget)
    return row,pool,ordered,budget,prompt

def checked_record(out,j,queries,contexts,lock):
    prompt=planned(j,queries,contexts,lock)[-1]
    r=base.read(out/j['path']);base.validate_record(r,j,prompt,lock)
    row,pool,ordered,budget,_=planned(j,queries,contexts,lock)
    expected=[{'id':p.id,'url':p.file,'brand':p.brand,'text':p.text[:budget],'original_chars':len(p.text)} for p in ordered]
    if r['sources']!=expected or r['arm']!=j['arm'] or r['pair_key']!=j['pair_key']:raise ValueError('Record source/arm identity mismatch')
    return r

def run(out,workers):
    if (out/'GENERATION_DEFERRED.json').exists():raise ValueError('Superseded preparation: generation is deferred for this package')
    lock=validate(out)
    if base.hostname(os.getenv('OPENAI_BASE_URL','https://api.openai.com/v1'))!=lock['endpoint']:raise ValueError('Endpoint drift')
    contexts=base.read(out/'contexts.json');queries={q['id']:q for q in load_queries(out)}
    jobs=base.read(out/'schedule.json');pairs=defaultdict(list)
    for j in jobs:
        if (out/j['path']).exists():checked_record(out,j,queries,contexts,lock)
        else:pairs[j['pair_key']].append(j)
    print(f'Pending {sum(map(len,pairs.values()))}/{len(jobs)} answers; {workers} paired workers',flush=True)
    def execute(pair):
        for j in pair:
            row,pool,ordered,budget,prompt=planned(j,queries,contexts,lock)
            result=ObservedClient(lock['model']).generate(prompt)
            record={**j,'experiment_id':lock['experiment_id'],'parent_id':lock['parent_id'],
                    'query':row['query'],'stratum':row.get('stratum',''),'group':row.get('group',''),
                    'prompt':prompt,'prompt_sha256':base.digest(prompt.encode()),
                    'sources':[{'id':p.id,'url':p.file,'brand':p.brand,'text':p.text[:budget],'original_chars':len(p.text)} for p in ordered],
                    'pool_ids':[p['id'] for p in pool],'pool_brands':[p['brand'] for p in pool],**result}
            record['record_sha256']=base.digest(record);base.write(out/j['path'],record)
            print('SAVED '+j['key'],flush=True)
    marker=out/'RUNNING'
    with marker.open('x') as f:f.write(str(os.getpid()))
    try:
        pending=list(pairs.values())
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for start in range(0,len(pending),workers):
                futures=[executor.submit(execute,p) for p in pending[start:start+workers]]
                for future in as_completed(futures):future.result()
    except Exception as exc:
        base.write(out/'failure.json',{'error':type(exc).__name__,'message':str(exc)[:1000]});raise
    finally:marker.unlink()
    report(out)

def report(out):
    global ARMS
    scheduled_arms=sorted({j['arm'] for j in base.read(out/'schedule.json')})
    ARMS=('baseline_repeat',)+tuple(a for a in scheduled_arms if a!='baseline_repeat')
    lock=validate(out,check_code=False);queries={q['id']:q for q in load_queries(out)};contexts=base.read(out/'contexts.json')
    jobs=base.read(out/'schedule.json');metrics=[];api_records={a:[] for a in ARMS}
    for j in jobs:
        if not (out/j['path']).exists():continue
        r=checked_record(out,j,queries,contexts,lock);m=base.record_metrics(r);api_records[j['arm']].append(r['api'])
        m.update(arm=j['arm'],pair_key=j['pair_key']);metrics.append(m)
    base.write(out/'metrics.json',metrics)
    scheduled_count=len(metrics);complete=scheduled_count==len(jobs)
    treatment_count=sum(m['arm']!='baseline_repeat' for m in metrics)
    parent=Path(lock['parent_path']);parent_lock=base.validate_package(parent)
    for j in ([] if 'baseline_repeat' in scheduled_arms else base.read(parent/'schedule.json')):
        prompt=base.planned_prompt(j,queries,contexts['baseline_repeat'],parent_lock)[-1]
        r=base.read(parent/j['path']);base.validate_record(r,j,prompt,parent_lock);api_records['baseline_repeat'].append(r['api'])
        m=base.record_metrics(r);m.update(arm='baseline_repeat',pair_key=j['key']);metrics.append(m)
    base.write(out/'metrics.json',metrics)
    summary={'experiment_id':lock['experiment_id'],'records':treatment_count,'scheduled_records':scheduled_count,'expected':len(jobs),'control_records':len(metrics)-treatment_count,'complete':complete,
             'control_generation':lock.get('control_generation','historical_parent'),
             'provider_provenance':{a:{'returned_models':dict(Counter(r['returned_model'] for r in rs)),
                                      'fingerprints':dict(Counter(str(r.get('system_fingerprint')) for r in rs)),
                                      'first_request':min((r['attempts'][0]['started_at'] for r in rs),default=None),
                                      'last_request':max((r['attempts'][0]['started_at'] for r in rs),default=None)} for a,rs in api_records.items()},
             'quality_checks':{'empty':sum(m['answer_empty'] for m in metrics),'invalid_citations':sum(m['invalid_citation_count'] for m in metrics),
                               'unsupported_grouped_citations':sum(m['unsupported_grouped_citations'] for m in metrics),
                               'finish_reasons':dict(Counter(m['finish_reason'] for m in metrics))},'comparisons':{}}
    for variant in ('fixed','reindexed'):
        for stratum in ('all','primary'):
            rows=[m for m in metrics if m['variant']==variant and (stratum=='all' or m['stratum']=='primary')]
            group=defaultdict(dict)
            for m in rows:group[m['pair_key']][m['arm']]=m
            if not group or any(set(v)!=set(ARMS) for v in group.values()):continue
            for metric in ('citation_inclusion','citation_share','retrieval_inclusion'):
                byquery=defaultdict(list)
                for v in group.values():
                    c,t=v[ARMS[0]],v[ARMS[1]];byquery[c['query_id']].append((c[metric],t[metric]))
                qrows=[{'query_id':q,'baseline':float(np.mean([x[0] for x in vals])),
                        'rendered':float(np.mean([x[1] for x in vals]))} for q,vals in sorted(byquery.items())]
                d=np.array([q['rendered']-q['baseline'] for q in qrows]);rng=np.random.default_rng(20260908)
                boot=np.mean(rng.choice(d,size=(5000,len(d)),replace=True),axis=1)
                item={'queries':len(qrows),'pairs':len(group),'baseline':float(np.mean([q['baseline'] for q in qrows])),
                      'rendered':float(np.mean([q['rendered'] for q in qrows])),'difference':float(d.mean()),
                      'paired_query_bootstrap_95':np.quantile(boot,[.025,.975]).tolist(),'per_query':qrows}
                if metric=='citation_inclusion' and variant=='reindexed' and stratum=='primary' and complete:
                    null=np.mean(rng.choice([-1,1],size=(100000,len(d)))*d,axis=1)
                    item['two_sided_sign_flip_p']=(1+int(np.sum(np.abs(null)>=abs(d.mean())-1e-12)))/100001
                summary['comparisons'][variant+'/'+stratum+'/'+metric]=item
    base.write(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='comparisons'},indent=2),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','verify','report']);p.add_argument('--output',type=Path,default=Path('results/optimisation_v3_ready'));p.add_argument('--parent',type=Path,default=Path('results/baseline_v2_1_repeat_20260909'));p.add_argument('--embedding-cache',type=Path);p.add_argument('--workers',type=int,default=4);p.add_argument('--arm',default='v3_final_core',choices=list(AVAILABLE_ARMS));p.add_argument('--allow-generation',action='store_true');p.add_argument('--fresh-controls',action='store_true');p.add_argument('--allow-legacy-preparation',action='store_true');a=p.parse_args()
    if not 1<=a.workers<=8:p.error('workers must be 1..8')
    if a.action=='prepare':prepare(a.output,a.parent,a.embedding_cache,a.arm,a.fresh_controls,a.allow_legacy_preparation)
    elif a.action=='run':
        if not a.allow_generation:p.error('Generation is intentionally deferred. Use --allow-generation only for a separately authorised run.')
        run(a.output,a.workers)
    elif a.action=='report':report(a.output)
    else:print(validate(a.output)['experiment_id'])

if __name__=='__main__':main()
