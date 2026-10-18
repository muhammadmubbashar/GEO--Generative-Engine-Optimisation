"""Auditable baseline lifecycle. Historical runs are never overwritten.

python -m geo_bench.baseline_v2 prepare --output results/baseline_v2_1
python -m geo_bench.baseline_v2 run --output results/baseline_v2_1
python -m geo_bench.baseline_v2 report --output results/baseline_v2_1
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import pickle
import platform
import random
import shutil
import sys
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from rank_bm25 import BM25Okapi
from .config import CONFIG
from .api.base import Passage
from .api.offline_client import tokenize
from .api.observed import ObservedClient
from .evaluation.metrics import position_adjusted_word_count
from .generation.generator import shuffle_passages
from .generation.prompts import build_prompt
from .retrieval.chunker import make_passages
from .search.live_retriever import brand_for_url, normalise_url

VERSION = "2.1.0"
ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    if not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def hostname(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def csv_write(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(rows[0])
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def code_files():
    return sorted(list((ROOT/"geo_bench").rglob("*.py")) +
                  list((ROOT/"tests").glob("*.py")) +
                  [ROOT/"BASELINE_V2_PROTOCOL.md", ROOT/"SCORING_RUBRICS.md", ROOT/"pyproject.toml"])


def validate_package(out):
    lock = read(out/"lock.json")
    body = {k:v for k,v in lock.items() if k != "experiment_id"}
    if digest(body) != lock["experiment_id"]:
        raise RuntimeError("Experiment lock identity mismatch")
    for relative, expected in lock["artifacts"].items():
        p = out/relative
        if not p.is_file() or sha(p) != expected:
            raise RuntimeError(f"Missing or changed artifact: {relative}")
    for relative, expected in lock["code"].items():
        if not (ROOT/relative).is_file() or sha(ROOT/relative) != expected:
            raise RuntimeError(f"Code/protocol drift: {relative}; create a new version")
    environment=read(out/"environment.json")
    for name in ("numpy","scipy","rank-bm25","openai","beautifulsoup4"):
        expected=environment["packages"].get(name)
        if expected and importlib.metadata.version(name)!=expected:
            raise RuntimeError(f"Dependency drift: {name}")
    if environment["python"]!=platform.python_version():
        raise RuntimeError("Python version drift")
    expected_records = {x["path"] for x in read(out/"schedule.json")}
    actual = {p.relative_to(out).as_posix() for p in (out/"records").glob("*.json")}
    if actual - expected_records:
        raise RuntimeError("Unscheduled answer files detected")
    return lock


def rank_pool(passages, vectors, bm25, qvector, query, *, depth=50, cap=2, top_k=5):
    """Fixed top-50 per retriever, RRF60, host cap, exact-text context dedup.

    No silent padding beyond the declared candidate pool. Full ranks retained.
    """
    qv = np.asarray(qvector, dtype=np.float32)
    if qv.shape != (vectors.shape[1],) or not np.isfinite(qv).all() or np.linalg.norm(qv) == 0:
        raise RuntimeError("Invalid query embedding")
    qv = qv / np.linalg.norm(qv)
    dense_scores = vectors @ qv
    lex_scores = bm25.get_scores(tokenize(query))
    order = lambda scores: sorted(range(len(passages)), key=lambda i:(-float(scores[i]), passages[i]["id"]))[:depth]
    dense, lexical = order(dense_scores), order(lex_scores)
    fused, ranks = defaultdict(float), defaultdict(dict)
    for name, ids in (("dense", dense), ("bm25", lexical)):
        for r,i in enumerate(ids,1):
            fused[i] += 1/(60+r)
            ranks[i][name] = r
    ranked = sorted(fused, key=lambda i:(-fused[i], passages[i]["id"]))
    selected, counts, texts, trace = [], Counter(), set(), []
    for r,i in enumerate(ranked,1):
        p = passages[i]
        host, text_hash = hostname(p["file"]), digest(p["text"].encode())
        reason = "selected"
        if len(selected) >= top_k: reason = "below_context_cutoff"
        elif counts[host] >= cap: reason = "hostname_cap"
        elif text_hash in texts: reason = "duplicate_context_text"
        else:
            selected.append(p)
            counts[host] += 1
            texts.add(text_hash)
        trace.append({"id":p["id"], "url":p["file"], "rrf_rank":r,
                      "rrf_score":fused[i], **ranks[i], "decision":reason})
    return selected, trace


def prepare(out):
    if (out/"lock.json").exists():
        validate_package(out)
        print("Existing package verified; prepare is idempotent", flush=True)
        return
    if out.exists() and any(out.iterdir()):
        raise RuntimeError("Output is not empty; use a new path (no overwrite)")
    out.mkdir(parents=True, exist_ok=True)
    run_id = CONFIG.active_run_file.read_text().strip()
    source = ROOT/CONFIG.runs_dir/run_id
    from .experiment.run_store import RunStore
    RunStore.open(run_id).verify_frozen_pages()
    manifest = list(csv.DictReader((source/"manifest.csv").open(encoding="utf-8")))
    expected_urls = {r["url"] for r in manifest}
    metas = [read(p) for p in sorted((source/"pages").glob("*/meta.json"))]
    if len(manifest) != len(expected_urls) or {m["url"] for m in metas} != expected_urls:
        raise RuntimeError("Freeze membership mismatch or duplicate URL")
    # Snapshot preserves historical bytes AND current metadata discrepancy;
    # the new manifest does not rewrite historical timestamps.
    print("Archiving frozen pages and retrieval captures ...", flush=True)
    ledger = {}
    with zipfile.ZipFile(out/"source_snapshot.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((source/"pages").rglob("*")) + sorted((source/"retrieval").glob("*.json")) + [source/"manifest.csv"]:
            if p.is_file():
                relative = p.relative_to(source).as_posix()
                ledger[relative] = sha(p)
                z.write(p, relative)
    write(out/"source_files.json", ledger)
    shutil.copy2(CONFIG.queries_file, out/"queries.csv")
    queries = list(csv.DictReader((out/"queries.csv").open(encoding="utf-8")))
    if len({q["id"] for q in queries}) != len(queries):
        raise RuntimeError("Duplicate query ID")
    # Do not inspect, copy or execute heldout queries during development.
    meta_by_url = {m["url"]:m for m in metas}
    pages, exclusions, drift, archive_identity = {}, [], [], []
    for row in manifest:
        url, meta = row["url"], meta_by_url[row["url"]]
        for key in ("sha256", "clean_sha256"):
            if row[key] != meta.get(key): raise RuntimeError(f"Historical byte hash mismatch: {url}")
        if row.get("fetched_at") != meta.get("fetched_at"):
            drift.append({"url":url,"historical":row.get("fetched_at"),"current":meta.get("fetched_at"),"bytes_unchanged":True})
        if row["method"]=="common-crawl":
            from .search.common_crawl import same_archive_url
            matches=same_archive_url(url,meta.get("fallback_cc_url",""))
            archive_identity.append({"url":url,"archive_url":meta.get("fallback_cc_url"),"identity_matches":matches})
            if not matches:
                exclusions.append({"url":url,"reason":"archive_URL_identity_mismatch", "method":row["method"],"words":row["words"]})
                continue
        if row["usable"] != "1":
            exclusions.append({"url":url,"reason":"historical_QC_unusable", "method":row["method"], "words":row["words"]})
            continue
        from .experiment.run_store import url_hash
        text = (source/"pages"/url_hash(url)/"clean.txt").read_bytes().decode("utf-8")
        if not text.strip(): raise RuntimeError("Usable page is empty")
        pages[normalise_url(url)] = {"url":url,"text":text.strip(),"brand":brand_for_url(url),
                                   "method":row["method"],"capture_date":row["fetched_at"]}
    write(out/"pages.json", pages)
    write(out/"exclusions.json", exclusions)
    write(out/"historical_metadata_discrepancies.json", drift)
    write(out/"archive_identity_audit.json",archive_identity)
    # Reuse only exact (URL, text, id) document vectors under matched settings.
    old_path, vec_path = CONFIG.index_path("baseline"), CONFIG.vectors_path("baseline")
    with old_path.open("rb") as f: old = pickle.load(f)
    from .retrieval.index import index_params
    expected = index_params(CONFIG)
    saved = dict(old["params"])
    saved.setdefault("arm_content_sha256", "")
    if saved != expected or old["run_id"] != run_id:
        raise RuntimeError("Cannot prove legacy embedding configuration identity")
    vecs = np.load(vec_path)["vecs"]
    if len(vecs) != len(old["passages"]) or not np.isfinite(vecs).all():
        raise RuntimeError("Invalid legacy vectors")
    lookup = {(p.id,p.file,p.text):i for i,p in enumerate(old["passages"])}
    passages, indices, seen = [], [], set()
    for page in pages.values():
        for p in make_passages(page["text"],page["brand"],page["url"],CONFIG):
            key = (p.file,p.text)
            if key in seen: continue
            seen.add(key)
            index_key = (p.id,p.file,p.text)
            if index_key not in lookup: raise RuntimeError("Passage identity mismatch; no silent re-embedding")
            indices.append(lookup[index_key])
            passages.append(asdict(p))
    vectors = vecs[indices]
    norms = np.linalg.norm(vectors,axis=1)
    if np.any(norms < .99) or np.any(norms > 1.01): raise RuntimeError("Document vectors not normalised")
    write(out/"passages.json",passages)
    np.savez(out/"vectors.npz",vecs=vectors)
    write(out/"embedding_reuse.json",{"source_index_sha256":sha(old_path),"source_vectors_sha256":sha(vec_path),
        "source_params":saved,"selected_indices":indices,"limitation":"Historical API response model metadata was not retained; exact saved vectors frozen here."})
    from .api import get_client
    print(f"Embedding {len(queries)} queries; retaining exact vectors ...",flush=True)
    qvectors = np.asarray(get_client(CONFIG).embed([q["query"] for q in queries]),dtype=np.float32)
    if qvectors.shape != (len(queries),vectors.shape[1]): raise RuntimeError("Query embedding shape mismatch")
    np.savez(out/"query_vectors.npz",vecs=qvectors)
    bm25 = BM25Okapi([tokenize(p["text"]) for p in passages],k1=CONFIG.bm25_k1,b=CONFIG.bm25_b)
    contexts, traces, eligibility = {}, {}, []
    for qi,q in enumerate(queries):
        selected,trace = rank_pool(passages,vectors,bm25,qvectors[qi],q["query"])
        contexts[q["id"]+"/reindexed"] = selected
        traces[q["id"]] = trace
        capture = read(source/"retrieval"/(q["id"]+".json"))
        if capture["query"] != q["query"]: raise RuntimeError("Query text differs from capture")
        fixed, seen_text = [], set()
        for url in capture["analysis_urls"][:10]:
            page = pages.get(normalise_url(url))
            if not page or page["text"] in seen_text: continue
            seen_text.add(page["text"])
            fixed.append({"id":"page:"+digest(url.encode())[:16],"file":url,"brand":page["brand"],"text":page["text"],"words":len(page["text"].split())})
        eligible = any(p["brand"] == CONFIG.our_brand for p in fixed) and len(fixed)>=5
        eligibility.append({"query_id":q["id"],"eligible_fixed":eligible,"usable_fixed_sources":len(fixed),"reason":"eligible" if eligible else "FC_absent_or_fewer_than_five_usable_sources"})
        if eligible: contexts[q["id"]+"/fixed"] = fixed
    write(out/"contexts.json",contexts)
    write(out/"retrieval_trace.json",traces)
    write(out/"eligibility.json",eligibility)
    # Relevance labels are independent judgments, never inferred from brand.
    passage_by_id={p["id"]:p for p in passages}
    relevance_tasks=[]
    for q in queries:
        for t in traces[q["id"]]:
            if min(t.get("dense",999),t.get("bm25",999),t["rrf_rank"])>10:
                continue
            p=passage_by_id[t["id"]]
            relevance_tasks.append({"query_id":q["id"],"query":q["query"],"passage_id":p["id"],
                                    "text":p["text"],"human1_relevance":"","human2_relevance":""})
    random.Random(20260908).shuffle(relevance_tasks)
    write(out/"retrieval_relevance_tasks.json",relevance_tasks)
    # A deterministic extraction-review sample, stratified by brand/method.
    groups=defaultdict(list)
    for p in pages.values(): groups[(p["brand"],p["method"])].append(p)
    extraction=[]
    for group,ps in sorted(groups.items()):
        sample=random.Random(20260908).sample(ps,min(2,len(ps)))
        for p in sample:
            extraction.append({"url":p["url"],"brand":p["brand"],"method":p["method"],"clean_text":p["text"],
                               "raw_archive_member":"pages/"+url_hash(p["url"])+"/raw.html",
                               "human_fact_preservation":"","human_boilerplate_contamination":"","notes":""})
    write(out/"extraction_review_tasks.json",extraction)
    schedule=[]
    for q in queries:
        for variant in ("fixed","reindexed"):
            if q["id"]+"/"+variant not in contexts: continue
            for seed in CONFIG.seeds:
                for run in range(1,CONFIG.runs_per_query+1):
                    key=f"{q['id']}_{variant}_s{seed}_r{run}"
                    schedule.append({"key":key,"query_id":q["id"],"variant":variant,"seed":seed,"run":run,"path":"records/"+key+".json"})
    random.Random(20260908).shuffle(schedule)
    write(out/"schedule.json",schedule)
    environment={"python":platform.python_version(),"platform":platform.platform(),"packages":{d.metadata["Name"]:d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}}
    write(out/"environment.json",environment)
    (out/"requirements-lock.txt").write_text("\n".join(f"{k}=={v}" for k,v in sorted(environment["packages"].items()))+"\n",encoding="utf-8")
    for p in code_files():
        dest=out/"code"/p.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dest)
    from .experiment.run_store import config_snapshot
    lock={"version":VERSION,"created_at":datetime.now(timezone.utc).isoformat(),"source_run":run_id,
          "status":"development_baseline; not heldout confirmation","model":CONFIG.gen_model,
          "sampling":"provider_defaults; no API seed","endpoint":hostname(os.getenv("OPENAI_BASE_URL","https://api.openai.com/v1")),
          "config_snapshot":config_snapshot(CONFIG),
          "policy":{"primary_metric":"citation_inclusion","primary_variant":"reindexed","primary_stratum":"primary",
                    "cap_scope":"hostname_without_www","cap":2,"top_k":5,"candidate_depth":50,"rrf_k":60,
                    "evidence":"historical_QC_usable_only","word_metric":"custom_discounted_attributed_words_v2",
                    "fixed_chars":CONFIG.page_prompt_chars,"reindexed_chars":CONFIG.passage_prompt_chars},
          "expected_records":len(schedule),"code":{p.relative_to(ROOT).as_posix():sha(p) for p in code_files()}}
    lock["artifacts"]={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    lock["experiment_id"]=digest(lock)
    write(out/"lock.json",lock)
    print(f"Prepared {len(pages)} usable pages, {len(passages)} passages, {len(schedule)} scheduled answers. ID={lock['experiment_id']}",flush=True)


def planned_prompt(job,queries,contexts,lock):
    row=queries[job["query_id"]]
    pool=contexts[job["query_id"]+"/"+job["variant"]]
    ordered=shuffle_passages([Passage(**p) for p in pool],job["seed"]*10000+job["run"])
    budget=lock["policy"][job["variant"]+"_chars"]
    prompt=build_prompt(row["query"],ordered,max_chars=budget)
    return row,pool,ordered,budget,prompt


def validate_record(record,job,prompt,lock):
    if record.get("experiment_id")!=lock["experiment_id"] or record.get("key")!=job["key"] or record.get("prompt_sha256")!=digest(prompt.encode()) or record.get("prompt")!=prompt:
        raise RuntimeError("Answer identity/prompt mismatch; refusing resume")
    body={k:v for k,v in record.items() if k!="record_sha256"}
    if record.get("record_sha256")!=digest(body): raise RuntimeError("Answer record hash mismatch")


def run(out,workers=4,limit=None):
    lock=validate_package(out)
    if hostname(os.getenv("OPENAI_BASE_URL","https://api.openai.com/v1"))!=lock["endpoint"]:
        raise RuntimeError("Provider endpoint changed")
    queries={q["id"]:q for q in csv.DictReader((out/"queries.csv").open(encoding="utf-8"))}
    contexts=read(out/"contexts.json")
    jobs=read(out/"schedule.json")
    pending=[]
    for job in jobs:
        *_,prompt=planned_prompt(job,queries,contexts,lock)
        if (out/job["path"]).exists(): validate_record(read(out/job["path"]),job,prompt,lock)
        else: pending.append(job)
    if limit is not None: pending=pending[:limit]
    print(f"Scheduled={len(jobs)} pending={len(pending)} model={lock['model']}",flush=True)
    def execute(job):
        row,pool,ordered,budget,prompt=planned_prompt(job,queries,contexts,lock)
        result=ObservedClient(lock["model"]).generate(prompt)
        record={**job,"experiment_id":lock["experiment_id"],"query":row["query"],"stratum":row.get("stratum",""),
                "group":row.get("group",""),"arm":"baseline","prompt":prompt,"prompt_sha256":digest(prompt.encode()),
                "sources":[{"id":p.id,"url":p.file,"brand":p.brand,"text":p.text[:budget],"original_chars":len(p.text)} for p in ordered],
                "pool_ids":[p["id"] for p in pool],"pool_brands":[p["brand"] for p in pool],**result}
        record["record_sha256"]=digest(record)
        write(out/job["path"],record)
        return job["key"]
    # A process lock prevents duplicate concurrent invocations. No answer mirrors.
    marker=out/"RUNNING"
    with marker.open("x") as f: f.write(str(os.getpid()))
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Bounded batches stop submission after a provider error.
            for offset in range(0,len(pending),workers):
                futures={executor.submit(execute,j):j for j in pending[offset:offset+workers]}
                for future in as_completed(futures):
                    job=futures[future]
                    try:
                        key=future.result()
                        print(f"[{offset+list(futures).index(future)+1}/{len(pending)}] saved {key}",flush=True)
                    except Exception as exc:
                        write(out/"last_failure.json",{"job":job["key"],"error_type":type(exc).__name__,"message":str(exc)[:1000],"at":datetime.now(timezone.utc).isoformat()})
                        raise
    finally:
        marker.unlink()
    report(out)


def record_metrics(r):
    import re
    sources=r["sources"]
    refs=[int(x) for x in re.findall(r"\[(\d+)\]",r["answer"])]
    valid=[i for i in refs if 1<=i<=len(sources)]
    cited=[sources[i-1]["brand"] for i in valid]
    fc=CONFIG.our_brand
    pool=r["pool_brands"]
    rank=pool.index(fc)+1 if fc in pool else None
    return {"key":r["key"],"query_id":r["query_id"],"variant":r["variant"],"stratum":r["stratum"],
            "citation_inclusion":int(fc in cited),"citation_share":cited.count(fc)/len(cited) if cited else 0.0,
            "discounted_attributed_words":position_adjusted_word_count(r["answer"],{i:s["brand"] for i,s in enumerate(sources,1)},fc),
            "retrieval_inclusion":int(rank is not None),"retrieval_reciprocal_rank":1/rank if rank else 0.0,
            "retrieval_rank_conditional":rank,"invalid_citation_count":len(refs)-len(valid),
            "unsupported_grouped_citations":len(re.findall(r"\[\d+(?:\s*[,\-–]\s*\d+)+\]",r["answer"])),
            "no_citations":int(not valid),"n_sources":len(sources),"n_hostnames":len({hostname(s["url"]) for s in sources}),
            "truncated_sources":sum(len(s["text"])<s["original_chars"] for s in sources),
            "finish_reason":r["api"]["finish_reason"],"answer_empty":int(not r["answer"].strip())}


def report(out):
    lock=validate_package(out)
    contexts=read(out/"contexts.json")
    queries={q["id"]:q for q in csv.DictReader((out/"queries.csv").open(encoding="utf-8"))}
    records=[]
    for job in read(out/"schedule.json"):
        path=out/job["path"]
        if not path.exists(): continue
        *_,prompt=planned_prompt(job,queries,contexts,lock)
        rec=read(path)
        validate_record(rec,job,prompt,lock)
        records.append(rec)
    if not records: raise RuntimeError("No generated records")
    rows=[record_metrics(r) for r in records]
    csv_write(out/"scores.csv",rows)
    summaries=[]
    for variant in ("fixed","reindexed"):
        for stratum in ("primary","secondary","all"):
            subset=[r for r in rows if r["variant"]==variant and (stratum=="all" or r["stratum"]==stratum)]
            if not subset: continue
            byq=defaultdict(list)
            for r in subset: byq[r["query_id"]].append(r)
            metrics={}
            for metric in ("citation_inclusion","citation_share","discounted_attributed_words","retrieval_inclusion","retrieval_reciprocal_rank"):
                means=np.array([np.mean([r[metric] for r in rs]) for rs in byq.values()])
                rng=np.random.default_rng(20260908)
                bootstrap=np.mean(rng.choice(means,size=(5000,len(means)),replace=True),axis=1)
                metrics[metric]={"query_mean":float(np.mean(means)),"query_bootstrap_95ci":np.quantile(bootstrap,[.025,.975]).tolist()}
            summaries.append({"variant":variant,"stratum":stratum,"answers":len(subset),"queries":len(byq),"metrics":metrics})
    summary={"experiment_id":lock["experiment_id"],"complete":len(records)==lock["expected_records"],
             "expected":lock["expected_records"],"observed":len(records),"summaries":summaries,
             "score_provenance":{"answers":{r["key"]:r["record_sha256"] for r in records},"scores_sha256":sha(out/"scores.csv")},
             "returned_models":dict(Counter(r["api"]["returned_model"] for r in records)),
             "finish_reasons":dict(Counter(r["api"]["finish_reason"] for r in records)),
             "tokens":sum((r["api"].get("usage") or {}).get("total_tokens",0) for r in records),
             "limitations":["development query set; no confirmatory generalisation", "quality and retrieval relevance await independent human labels", "query bootstrap assumes independent query clusters; related destinations require sensitivity", "citation is not support, endorsement, or product validity"]}
    write(out/"summary.json",summary)
    if summary["complete"]:
        export_annotations(out,records)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("score_provenance","summaries")},indent=2),flush=True)


def export_annotations(out,records):
    """One per query/variant before extra rows; no arm/model/machine score cues."""
    rng=random.Random(20260908)
    byq=defaultdict(list)
    for r in records: byq[(r["query_id"],r["variant"])].append(r)
    sample=[rng.choice(rs) for _,rs in sorted(byq.items())]
    rng.shuffle(sample)
    annotation=out/"human_review"
    annotation.mkdir(exist_ok=True)
    # Never overwrite a human's work during report refresh.
    if (annotation/"labels.csv").exists(): return
    tasks,mapping,labels=[],{},[]
    for i,r in enumerate(sample,1):
        sid=f"A{i:03d}"
        mapping[sid]=r["key"]
        tasks.append({"sample_id":sid,"question":r["query"],"answer":r["answer"],"sources":[{"citation_index":j,"text":s["text"]} for j,s in enumerate(r["sources"],1)]})
        labels.append({"sample_id":sid,**{f"{grader}_{dim}":"" for grader in ("human1","human2") for dim in ("relevance","accuracy","completeness","clarity","attribution")},"notes":""})
    write(annotation/"tasks.json",tasks)
    write(annotation/"ADMIN_mapping_do_not_give_graders.json",mapping)
    csv_write(annotation/"labels.csv",labels)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["prepare","run","report","verify"])
    parser.add_argument("--output",type=Path,default=Path("results/baseline_v2_1"))
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--limit",type=int)
    args=parser.parse_args()
    if not 1<=args.workers<=8: parser.error("workers must be 1..8")
    if args.command=="prepare": prepare(args.output)
    elif args.command=="run": run(args.output,args.workers,args.limit)
    elif args.command=="report": report(args.output)
    else:
        lock=validate_package(args.output)
        print("Package verified",lock["experiment_id"])


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
