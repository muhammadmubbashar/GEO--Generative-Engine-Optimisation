"""Select Flight Centre freeze pages, extract facts, freeze arm HTML.

Never writes into the freeze `pages/` directory. Arm output lives under
`runs/<RUN_ID>/arms/<arm>/pages/`.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import CONFIG, Config
from ..experiment.run_store import RunStore, url_hash
from ..retrieval.cleaner import clean_html
from ..search.live_retriever import brand_for_url, normalise_url
from .base import FrozenPage, OptimisedPage
from .facts import (
    Fact, FactTable, extract_candidates, merge_preserving_verified,
)
from .verifier import (
    validate_jsonld, verify_page, write_failure_report,
)

TARGET_FIELDS = (
    "url", "page_type", "queries_served", "fc_best_rank", "eligible_layers",
    "title",
)
COVERAGE_FIELDS = (
    "url", "page_type", "total_words", "numeric_claims_found",
    "named_entities_found", "usable_facts", "queries_served",
)


def classify_page_type(url: str, title: str = "") -> str:
    path = urllib.parse.urlsplit(url).path.lower()
    blob = f"{path} {(title or '').lower()}"
    if "faq" in blob or "frequently-asked" in blob:
        return "faq"
    cabin = (
        "class-of-travel", "business-class", "premium-economy", "first-class",
        "economy-class", "mixed-class", "business class", "premium economy",
        "first class",
    )
    if any(tok in blob for tok in cabin):
        return "cabin"
    parts = [p for p in path.split("/") if p]
    if "flights" not in parts:
        return "generic"
    rest = parts[parts.index("flights") + 1:]
    if not rest or rest[0] in {
            "airlines", "class-of-travel", "multi-city",
            "round-the-world", "last-minute", "deals"}:
        return "generic"
    locish = [
        p for p in rest
        if re.match(r"^[a-z]{2}(-[a-z]{2,3})+-[a-z]", p)
        or (len(p) == 2 and p.isalpha())
    ]
    if locish:
        return "route"
    if len(rest) >= 2:
        return "route"
    return "generic"


def _layers_for(best_rank: Optional[int], analysis_k: int,
                capture_k: int) -> Tuple[str, ...]:
    if best_rank is None:
        return ("reindexed",)
    if best_rank <= analysis_k:
        return ("selection", "reindexed", "fixed")
    if best_rank <= capture_k:
        return ("selection", "reindexed")
    return ("reindexed",)


def collect_targets(store: RunStore, cfg: Config = CONFIG) -> List[Dict]:
    """One row per unique FC URL in the freeze."""
    # url -> {qid: rank}
    ranks: Dict[str, Dict[str, int]] = defaultdict(dict)
    titles: Dict[str, str] = {}
    for qpath in sorted(store.retrieval_dir.glob("*.json")):
        qid = qpath.stem
        data = json.loads(qpath.read_text(encoding="utf-8"))
        for row in data.get("results") or []:
            url = (row.get("url") or "").strip()
            if not url:
                continue
            if (row.get("brand") or brand_for_url(url, cfg)) != cfg.our_brand:
                continue
            pos = int(row.get("position") or row.get("rank_merged") or 0)
            if pos:
                prev = ranks[url].get(qid)
                ranks[url][qid] = pos if prev is None else min(prev, pos)
            if row.get("title") and url not in titles:
                titles[url] = row["title"]

    rows: List[Dict] = []
    seen = set()
    for meta in store.iter_page_metas():
        url = (meta.get("url") or "").strip()
        if not url:
            continue
        brand = meta.get("brand") or brand_for_url(url, cfg)
        if brand != cfg.our_brand:
            continue
        key = normalise_url(url)
        if key in seen:
            continue
        seen.add(key)
        served = ranks.get(url) or {}
        # ranks dict keyed by exact URL; try normalised aliases
        if not served:
            for u, qmap in ranks.items():
                if normalise_url(u) == key:
                    served = qmap
                    break
        best = min(served.values()) if served else None
        qids = ",".join(sorted(served.keys()))
        page_type = classify_page_type(url, titles.get(url, ""))
        layers = _layers_for(
            best, cfg.search_analysis_depth, cfg.search_capture_depth)
        rows.append({
            "url": url,
            "page_type": page_type,
            "queries_served": qids,
            "fc_best_rank": "" if best is None else str(best),
            "eligible_layers": ",".join(layers),
            "title": titles.get(url, ""),
            "words": int(meta.get("words") or 0),
            "usable": int(meta.get("usable") or 0) if "usable" in meta
            else int(int(meta.get("words") or 0)
                     >= cfg.thin_page_word_threshold),
            "sha256": meta.get("sha256") or "",
        })
    rows.sort(key=lambda r: r["url"])
    return rows


def write_targets_csv(rows: List[Dict], cfg: Config = CONFIG) -> Path:
    path = cfg.optimisation_targets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(TARGET_FIELDS), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def load_frozen_page(store: RunStore, row: Dict,
                     cfg: Config = CONFIG) -> FrozenPage:
    page = store.read_page(row["url"])
    if page is None:
        raise RuntimeError(f"missing freeze page for {row['url']}")
    qids = tuple(q for q in (row.get("queries_served") or "").split(",") if q)
    rank = row.get("fc_best_rank") or ""
    layers = tuple(x for x in (row.get("eligible_layers") or "").split(",") if x)
    return FrozenPage(
        url=page["url"],
        html=page.get("html") or "",
        clean=page.get("clean") or "",
        sha256=page.get("sha256") or "",
        clean_sha256=page.get("clean_sha256") or "",
        words=int(page.get("words") or 0),
        brand=page.get("brand") or cfg.our_brand,
        page_type=row.get("page_type") or "generic",
        title=row.get("title") or "",
        queries_served=qids,
        fc_best_rank=int(rank) if str(rank).isdigit() else None,
        eligible_layers=layers,
        usable=bool(int(row.get("usable") or 1)),
        extra={"method": page.get("method") or ""},
    )


def extract_facts(from_run: Optional[str] = None,
                  cfg: Config = CONFIG) -> Dict:
    """Step 2: candidate facts + coverage. No arm generation."""
    store = RunStore.resolve(from_run, cfg)
    store.verify_frozen_pages()
    targets = collect_targets(store, cfg)
    tpath = write_targets_csv(targets, cfg)

    existing = FactTable.load(cfg.facts_file, cfg)
    incoming: List[Fact] = []
    coverage: List[Dict] = []
    n_id = 0
    zero_pages = 0
    zero_fixed_pages = 0
    n_fixed_pages = 0

    for row in targets:
        page = load_frozen_page(store, row, cfg)
        result = extract_candidates(
            page.url, page.html, page.clean, page.page_type, n_id)
        n_id += len(result.facts)
        incoming.extend(result.facts)
        usable = sum(1 for f in result.facts if f.is_usable)
        if usable == 0:
            zero_pages += 1
        layers = row.get("eligible_layers") or ""
        if "fixed" in layers.split(","):
            n_fixed_pages += 1
            if usable == 0:
                zero_fixed_pages += 1
        coverage.append({
            "url": page.url,
            "page_type": page.page_type,
            "total_words": page.words,
            "numeric_claims_found": result.numeric_claims_found,
            "named_entities_found": len(result.named_entities),
            "usable_facts": usable,
            "queries_served": row.get("queries_served") or "",
        })

    table = merge_preserving_verified(existing, incoming)
    fpath = table.save(cfg.facts_file)

    cpath = cfg.fact_coverage_path()
    cpath.parent.mkdir(parents=True, exist_ok=True)
    with cpath.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COVERAGE_FIELDS))
        w.writeheader()
        w.writerows(coverage)

    # Share of the Fixed-eligible 30 queries whose *best* FC URL has 0 facts.
    routing_path = cfg.routing_path()
    n_fixed_q = 0
    n_fixed_q_zero = 0
    if routing_path.exists():
        cov_by_url = {r["url"]: r for r in coverage}
        for r in csv.DictReader(routing_path.open(encoding="utf-8")):
            if int(r.get("eligible_fixed") or 0) != 1:
                continue
            n_fixed_q += 1
            qid = r["query_id"]
            best = _best_fc_url_in_query(store, qid, cfg)
            if best is None:
                n_fixed_q_zero += 1
                continue
            cov = cov_by_url.get(best)
            if cov is None:
                key = next((u for u in cov_by_url
                            if normalise_url(u) == normalise_url(best)), None)
                cov = cov_by_url.get(key or "")
            if int((cov or {}).get("usable_facts") or 0) == 0:
                n_fixed_q_zero += 1

    summary = {
        "run_id": store.run_id,
        "n_fc_pages": len(targets),
        "n_zero_usable_facts": zero_pages,
        "zero_fact_share": (zero_pages / len(targets)) if targets else 0.0,
        "n_fixed_eligible_pages": n_fixed_pages,
        "n_fixed_pages_zero_facts": zero_fixed_pages,
        "n_fixed_eligible_queries": n_fixed_q,
        "n_fixed_queries_best_url_zero_facts": n_fixed_q_zero,
        "n_candidate_facts": sum(1 for f in table.facts
                                 if f.status == "candidate"),
        "n_verified_facts": sum(1 for f in table.facts if f.is_verified),
        "targets_csv": str(tpath),
        "facts_csv": str(fpath),
        "coverage_csv": str(cpath),
    }
    summary_path = cfg.results_dir / "fact_coverage_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _best_fc_url_in_query(store: RunStore, qid: str,
                         cfg: Config = CONFIG) -> Optional[str]:
    """Lowest-position Flight Centre URL in that query's frozen capture."""
    try:
        data = store.read_retrieval(qid)
    except FileNotFoundError:
        return None
    hits = []
    for row in data.get("results") or []:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        if (row.get("brand") or brand_for_url(url, cfg)) != cfg.our_brand:
            continue
        pos = int(row.get("position") or row.get("rank_merged") or 0)
        hits.append((pos or 999, url))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def render_coverage_summary(summary: Dict) -> str:
    n = summary["n_fc_pages"]
    z = summary["n_zero_usable_facts"]
    share = summary["zero_fact_share"]
    fq = summary["n_fixed_eligible_queries"]
    fz = summary["n_fixed_queries_best_url_zero_facts"]
    lines = [
        "FACT COVERAGE (candidate extraction — freeze FC pages only)",
        f"  freeze:            {summary['run_id']}",
        f"  unique FC pages:   {n}",
        f"  pages with 0 usable facts: {z} / {n}  ({share:.0%})",
        f"  pages in a fixed-eligible layer: "
        f"{summary['n_fixed_eligible_pages']}  "
        f"(zero facts: {summary['n_fixed_pages_zero_facts']})",
        f"  Fixed-eligible queries (best FC URL has 0 usable facts): "
        f"{fz} / {fq}" + (f"  ({fz / fq:.0%})" if fq else ""),
        f"  candidate fact rows: {summary['n_candidate_facts']}",
        f"  verified fact rows:  {summary['n_verified_facts']}",
        f"  wrote: {summary['coverage_csv']}",
        f"         {summary['facts_csv']}",
        f"         {summary['targets_csv']}",
        "",
        "status=candidate. A named team member must set status=verified",
        "before FAQ / statistics / cite / padding run. Do not generate",
        "those arms on candidates.",
    ]
    if share >= 0.5:
        lines += [
            "",
            "NOTE: zero-fact share is ≥ 50%. Content arms that need verified",
            "figures will have little to rewrite. This is a crawler-visibility",
            "ceiling (Type A), not evidence that GEO methods fail. Consider",
            "promoting ssr_visible before interpreting a later null result.",
        ]
    return "\n".join(lines)


def arm_pages_dir(store: RunStore, arm: str) -> Path:
    d = store.root / "arms" / arm / "pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


def arm_content_sha256(store: RunStore, arm: str) -> str:
    """Fingerprint the exact evaluated representation for an arm.

    Answers and indexes must never be resumed after an arm is rebuilt under
    the same freeze ID. The fingerprint is over URL + clean-text hashes, so it
    tracks what retrieval and generation actually receive rather than merely
    source-code timestamps.
    """
    root = store.root / "arms" / arm / "pages"
    rows = []
    for meta_path in sorted(root.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        rows.append({"url": meta.get("url", ""),
                     "clean_sha256": meta.get("clean_sha256", "")})
    if not rows:
        raise RuntimeError(f"arm={arm!r} has no built page metadata")
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_optimised_page(store: RunStore, arm: str, page: FrozenPage,
                         html: str, notes: Dict,
                         cfg: Config = CONFIG,
                         clean: Optional[str] = None) -> OptimisedPage:
    from .base import AddedClaim
    if clean is None:
        # Every arm except ssr_visible has clean == bare clean_html(html), so
        # recomputing here was harmless for them. ssr_visible's optimise()
        # runs an extra post-clean_html fix (_rejoin_split_prices) and
        # returns it via OptimisedPage.clean — recomputing from `html` alone
        # silently discarded that fix (found 2026-08-28: prices were
        # reaching the model as "$ 1 5 0" instead of "$150" in every
        # generated answer). Callers that computed a real `clean` value
        # must pass it through instead of relying on this fallback.
        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
    raw_bytes = html.encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    dest = arm_pages_dir(store, arm) / url_hash(page.url)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "raw.html").write_bytes(raw_bytes)
    (dest / "clean.txt").write_bytes(clean.encode("utf-8", errors="replace"))
    meta = {
        "url": page.url,
        "arm": arm,
        "sha256": digest,
        "clean_sha256": hashlib.sha256(
            clean.encode("utf-8", errors="replace")).hexdigest(),
        "baseline_sha256": page.sha256,
        "words": len(clean.split()),
        "baseline_words": page.words,
        "page_type": page.page_type,
        "notes": notes,
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    claims = [
        AddedClaim(span=c["span"], fact_id=c.get("fact_id", ""),
                   source_url=c.get("source_url", ""),
                   kind=c.get("kind", ""))
        for c in notes.get("claims") or []
    ]
    return OptimisedPage(
        url=page.url, arm=arm, html=html, clean=clean,
        content_hash=digest, baseline_sha256=page.sha256,
        baseline_words=page.words, optimised_words=len(clean.split()),
        page_type=page.page_type, claims=claims, notes=notes,
    )


def write_volume_csv(arm: str, pages: List[OptimisedPage],
                     extra_fields: Optional[Dict[str, Dict]] = None,
                     cfg: Config = CONFIG) -> Path:
    path = cfg.arm_results_dir(arm) / "volume.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["url", "baseline_words", "optimised_words", "delta", "pct_change"]
    extra_fields = extra_fields or {}
    extra_keys = []
    for row in extra_fields.values():
        for k in row:
            if k not in extra_keys:
                extra_keys.append(k)
    fields = fields + extra_keys
    deltas = []
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in pages:
            rec = {
                "url": p.url,
                "baseline_words": p.baseline_words,
                "optimised_words": p.optimised_words,
                "delta": p.words_delta,
                "pct_change": f"{p.pct_change:.2f}",
            }
            rec.update(extra_fields.get(p.url, {}))
            w.writerow(rec)
            if p.baseline_words:
                deltas.append(p.pct_change)
    mean = sum(deltas) / len(deltas) if deltas else 0.0
    flag = abs(mean) > cfg.length_flag_pct * 100
    sidecar = {
        "arm": arm,
        "n": len(pages),
        "mean_pct_change": mean,
        "volume_confound_flag": flag,
        "flag_threshold_pct": cfg.length_flag_pct * 100,
        "fail_threshold_pct": cfg.length_fail_pct * 100,
    }
    (path.parent / "volume_summary.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8")
    if flag:
        print(f"  FLAG: {arm} mean word-count delta {mean:+.1f}% exceeds "
              f"±{cfg.length_flag_pct:.0%}; read against padding_control.")
    return path


def load_arm_page(store: RunStore, arm: str, url: str) -> Optional[OptimisedPage]:
    dest = store.root / "arms" / arm / "pages" / url_hash(url)
    meta_path = dest / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    html = (dest / "raw.html").read_text(encoding="utf-8", errors="replace")
    clean = (dest / "clean.txt").read_text(encoding="utf-8", errors="replace")
    return OptimisedPage(
        url=url, arm=arm, html=html, clean=clean,
        content_hash=meta.get("sha256") or "",
        baseline_sha256=meta.get("baseline_sha256") or "",
        baseline_words=int(meta.get("baseline_words") or 0),
        optimised_words=int(meta.get("words") or 0),
        page_type=meta.get("page_type") or "generic",
        notes=meta.get("notes") or {},
    )


def load_arm_clean_map(store: RunStore, arm: str) -> Dict[str, str]:
    """URL -> cleaned arm text. Competitors never appear here."""
    root = store.root / "arms" / arm / "pages"
    if not root.exists():
        raise RuntimeError(
            f"no optimised pages at {root}. "
            f"Run: python -m geo_bench optimise {arm} --from-run {store.run_id}"
        )
    out: Dict[str, str] = {}
    for meta_path in sorted(root.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        url = (meta.get("url") or "").strip()
        if not url:
            continue
        clean_path = meta_path.parent / "clean.txt"
        if not clean_path.exists():
            continue
        clean = clean_path.read_text(encoding="utf-8", errors="replace").strip()
        if clean:
            out[url] = clean
            out[normalise_url(url)] = clean
    if not out:
        raise RuntimeError(f"arm={arm!r} has no readable clean.txt pages under {root}")
    return out


def optimise_arm(arm_name: str, from_run: Optional[str] = None,
                 cfg: Config = CONFIG) -> Path:
    from .arms import ARM_REGISTRY

    if arm_name not in cfg.optimisation_arms:
        raise RuntimeError(
            f"unknown optimisation arm {arm_name!r}; "
            f"allowed={cfg.optimisation_arms}"
        )
    if arm_name not in ARM_REGISTRY:
        raise RuntimeError(f"arm {arm_name!r} is not registered")
    store = RunStore.resolve(from_run, cfg)
    store.verify_frozen_pages()
    tpath = cfg.optimisation_targets_path()
    if not tpath.exists():
        raise RuntimeError(
            "results/optimisation_targets.csv missing. "
            "Run `geo extract-facts` first."
        )
    targets = list(csv.DictReader(tpath.open(encoding="utf-8")))
    facts = FactTable.load(cfg.facts_file, cfg)
    arm = ARM_REGISTRY[arm_name]
    if arm.needs_verified_facts and not facts.verified():
        raise RuntimeError(
            f"arm {arm_name!r} requires verified facts. "
            "A named team member must set status=verified in "
            f"{cfg.facts_file} first. Candidates are not usable."
        )
    if arm.uses_llm:
        from .llm import confirm_cost, estimate_cost_usd
        n = len(targets)
        est = estimate_cost_usd(n, 8_000, 800, cfg)
        confirm_cost(n, est, cfg)

    pages: List[OptimisedPage] = []
    extras: Dict[str, Dict] = {}
    n_fail = 0
    for row in targets:
        page = load_frozen_page(store, row, cfg)
        try:
            opt = arm.optimise(page, facts)
        except Exception as exc:
            n_fail += 1
            print(f"  FAIL {arm_name} {page.url}: {exc}")
            raise
        opt.notes.setdefault("preserves_length", arm.preserves_length)
        if arm_name in ("ssr_visible", "ssr_visible_digitfix"):
            from .verifier import verify_ssr_page
            result = verify_ssr_page(page, opt, cfg)
        elif arm_name == "freshness_signal":
            from .verifier import verify_freshness_page
            result = verify_freshness_page(page, opt, cfg)
        else:
            result = verify_page(page, opt, facts, cfg)
        if arm_name == "schema_markup":
            schema_errs = validate_jsonld(opt.html)
            if schema_errs:
                result.ok = False
                from .verifier import SpanFailure
                for e in schema_errs:
                    result.failures.append(SpanFailure("schema", e, e))
        if arm_name == "freshness_signal":
            from .arms.freshness_signal import FRESH_SCRIPT_ID
            schema_errs = validate_jsonld(opt.html, script_id=FRESH_SCRIPT_ID)
            if schema_errs:
                result.ok = False
                from .verifier import SpanFailure
                for e in schema_errs:
                    result.failures.append(SpanFailure("schema", e, e))
        if not result.ok:
            write_failure_report(opt, page, result, cfg)
            raise RuntimeError(
                f"{arm_name} verification failed for {page.url}. "
                f"See results/verification_failures/{arm_name}/"
            )
        written = write_optimised_page(
            store, arm_name, page, opt.html, opt.notes, cfg, clean=opt.clean)
        written.claims = opt.claims
        pages.append(written)
        extra = {}
        if "faq_pairs_generated" in opt.notes:
            extra["faq_pairs_generated"] = opt.notes["faq_pairs_generated"]
        if extra:
            extras[page.url] = extra
        print(f"  {arm_name}  {page.page_type:<8}  "
              f"{page.words:>5}->{written.optimised_words:<5}  {page.url}")

    vpath = write_volume_csv(arm_name, pages, extras, cfg)
    content_sha = arm_content_sha256(store, arm_name)
    manifest_path = store.root / "arms" / arm_name / "arm_manifest.json"
    manifest_path.write_text(json.dumps({
        "arm": arm_name,
        "run_id": store.run_id,
        "content_sha256": content_sha,
        "n_pages": len(pages),
        "evaluation_unit": "clean_text",
    }, indent=2), encoding="utf-8")
    print(f"  wrote {len(pages)} pages  volume={vpath}")
    print(f"  arm content sha256={content_sha[:16]}...")
    if n_fail:
        raise RuntimeError(f"{n_fail} pages failed to optimise")
    return vpath
