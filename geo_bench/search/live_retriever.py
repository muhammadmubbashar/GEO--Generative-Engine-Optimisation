"""Orchestrate fan-out → live search → freeze → one Passage per analysed doc."""
from __future__ import annotations

import csv
import hashlib
import json
import gzip
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import requests
from rank_bm25 import BM25Okapi

from ..api.base import Passage
from ..api.offline_client import tokenize
from ..config import CONFIG, Config
from ..crawler.fetcher import Fetcher
from ..retrieval.chunker import split_text
from ..retrieval.cleaner import clean_html
from .base import SearchResult
from .cache import SearchCache
from .factory import get_search_client
from .fanout import fanout_queries

if TYPE_CHECKING:
    from ..experiment.run_store import RunStore

_LIVE_FETCH_TIMEOUT = 10
_LIVE_ROBOTS_TIMEOUT = 5


def normalise_url(url: str) -> str:
    """Dedupe key: scheme/host/path; drop fragment and tracking params."""
    u = urllib.parse.urlsplit(url.strip())
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = u.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=False)
    drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "fbclid"}
    q = [(k, v) for k, v in q if k.lower() not in drop]
    query = urllib.parse.urlencode(sorted(q))
    return urllib.parse.urlunsplit((u.scheme.lower() or "https", host, path,
                                    query, ""))


def brand_for_url(url: str, cfg: Config = CONFIG) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for domain, brand in cfg.brand_domains:
        if host == domain or host.endswith("." + domain):
            return brand
    return "other"


def domain_of(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _best_chunk(text: str, query: str, cfg: Config) -> str:
    chunks = split_text(text, cfg)
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0]
    tokenized = [tokenize(c) for c in chunks]
    if not any(tokenized):
        return chunks[0]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    return chunks[int(scores.argmax())]


@dataclass
class LivePool:
    """Analysed shortlist + full-capture metadata for auditing."""
    passages: List[Passage]
    fanout_queries: List[str]
    retrieved_urls: List[str]          # analysis-depth URLs (generation pool)
    retrieved_ranks: List[int]
    retrieved_brands: List[str]
    fc_present: bool                   # in analysis pool
    fc_search_rank: Optional[int]      # best rank in full capture (may be >10)
    fc_in_capture: bool
    n_distinct_domains: int            # within analysis pool
    search_captured_at: str
    hit_counts: Dict[str, int] = field(default_factory=dict)
    capture_results: List[Dict] = field(default_factory=list)
    brand_ranks: Dict[str, Optional[int]] = field(default_factory=dict)
    # Known brands (FC + rivals) with usable cleaned text in the analysis pool.
    brands_usable: List[str] = field(default_factory=list)
    # Known brands missing usable content (absent from pool OR bot-wall/thin).
    brands_missing_usable: List[str] = field(default_factory=list)
    page_fetch_log: List[Dict] = field(default_factory=list)
    fetch_user_agent: str = ""
    analysis_depth: int = 10
    capture_depth: int = 20

    def meta_dict(self) -> Dict:
        return {
            "fanout_queries": self.fanout_queries,
            "retrieved_urls": self.retrieved_urls,
            "retrieved_ranks": self.retrieved_ranks,
            "retrieved_brands": self.retrieved_brands,
            "fc_present": self.fc_present,
            "fc_search_rank": self.fc_search_rank,
            "fc_in_capture": self.fc_in_capture,
            "n_distinct_domains": self.n_distinct_domains,
            "search_captured_at": self.search_captured_at,
            "brand_ranks": self.brand_ranks,
            "brands_usable": self.brands_usable,
            "brands_missing_usable": self.brands_missing_usable,
            "page_fetch_log": self.page_fetch_log,
            "fetch_user_agent": self.fetch_user_agent,
            "analysis_depth": self.analysis_depth,
            "capture_depth": self.capture_depth,
            "capture_results": self.capture_results,
        }

    def print_pool(self, query: str = "") -> None:
        print(f"\n=== LIVE POOL === query={query!r}")
        print(f"fan-out ({len(self.fanout_queries)}):")
        for i, q in enumerate(self.fanout_queries, 1):
            print(f"  {i}. {q}")
        print(f"fc_in_capture={self.fc_in_capture}  "
              f"fc_search_rank={self.fc_search_rank}  "
              f"fc_in_analysis={self.fc_present}  "
              f"domains={self.n_distinct_domains}  "
              f"captured_at={self.search_captured_at}")
        print(f"brand_ranks={self.brand_ranks}")
        print(f"brands_usable={self.brands_usable}")
        print(f"brands_missing_usable={self.brands_missing_usable}")
        print("--- analysed (generation) ---")
        for rank, url, brand in zip(
                self.retrieved_ranks, self.retrieved_urls, self.retrieved_brands):
            print(f"{rank:>4}  {brand:<14}       {url}")
        thin = sum(1 for p in self.passages if p.words < 50)
        print(f"passages={len(self.passages)}  thin_pages(<50w)={thin}")


class LiveRetriever:
    def __init__(self, cfg: Config = CONFIG, refresh: bool = False,
                 store: Optional["RunStore"] = None):
        self.cfg = cfg
        self.cache = SearchCache(cfg, refresh=refresh)
        self.search = get_search_client(cfg)
        self.fetcher = Fetcher(cfg, delay=0.25)
        self.store = store
        self._robots_cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def _robots_allowed(self, url: str) -> bool:
        """robots.txt check using the same live fetch UA as page gets."""
        ua = self.cfg.live_fetch_user_agent
        root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
        if root not in self._robots_cache:
            rp: Optional[urllib.robotparser.RobotFileParser] = (
                urllib.robotparser.RobotFileParser())
            try:
                resp = requests.get(
                    root + "/robots.txt", timeout=_LIVE_ROBOTS_TIMEOUT,
                    headers={"User-Agent": ua})
                if resp.status_code >= 400:
                    rp = None
                else:
                    rp.parse(resp.text.splitlines())
            except Exception:
                rp = None
            self._robots_cache[root] = rp
        rp = self._robots_cache[root]
        return True if rp is None else rp.can_fetch(ua, url)

    def _known_brands(self) -> Tuple[str, ...]:
        return self.cfg.brands

    def _brand_coverage(self, page_logs: List[Dict]
                        ) -> Tuple[List[str], List[str]]:
        """Usable vs missing among known commercial brands for one query."""
        usable: set = set()
        for row in page_logs:
            brand = row.get("brand") or "other"
            if brand in self._known_brands() and row.get("content_ok"):
                usable.add(brand)
        missing = [b for b in self._known_brands() if b not in usable]
        return sorted(usable), missing

    def _search_one(self, query: str) -> Tuple[List[SearchResult], str]:
        count = self.cfg.search_capture_depth
        region = self.cfg.search_region
        cached = self.cache.get_search(
            query, self.search.name, region, count)
        if cached:
            results = [
                SearchResult(
                    url=r["url"], title=r.get("title", ""),
                    snippet=r.get("snippet", ""), rank=r["rank"],
                    source_query=r.get("source_query", query))
                for r in cached["results"]
            ]
            return results, cached.get("captured_at", "")
        live = self.search.search(
            query, count=count, region=region,
            language=self.cfg.search_language)
        payload = self.cache.put_search(
            query, self.search.name, region, count,
            [{"url": r.url, "title": r.title, "snippet": r.snippet,
              "rank": r.rank, "source_query": r.source_query} for r in live])
        return live, payload["captured_at"]

    def _merge_capture(self, query: str
                       ) -> Tuple[List[SearchResult], Dict[str, int],
                                  List[str], str]:
        variants = fanout_queries(query, self.cfg, self.cache)
        self._persist_fanout_record(query, variants)
        batches: List[Tuple[List[SearchResult], str]] = []
        for v in variants:
            results, ts = self._search_one(v)
            batches.append((results, ts))

        best: Dict[str, SearchResult] = {}
        hits: Dict[str, int] = {}
        captured_at = ""
        for results, ts in batches:
            captured_at = captured_at or ts
            for r in results:
                key = normalise_url(r.url)
                hits[key] = hits.get(key, 0) + 1
                prev = best.get(key)
                if prev is None or r.rank < prev.rank:
                    best[key] = SearchResult(
                        url=r.url, title=r.title, snippet=r.snippet,
                        rank=r.rank, source_query=r.source_query)
        if not best:
            raise RuntimeError(
                f"live retrieval produced an empty merged pool for {query!r}")
        ordered = sorted(
            best.values(),
            key=lambda r: (r.rank, -hits[normalise_url(r.url)], r.url))
        capture = ordered[: self.cfg.search_capture_depth]
        if not capture:
            raise RuntimeError(f"live pool empty after truncation for {query!r}")
        return capture, hits, variants, (
            captured_at or time.strftime("%Y-%m-%dT%H:%M:%S"))

    def _brand_ranks(self, capture: List[SearchResult]) -> Dict[str, Optional[int]]:
        ranks: Dict[str, Optional[int]] = {b: None for b in self.cfg.brands}
        ranks["other"] = None
        for i, r in enumerate(capture, 1):
            brand = brand_for_url(r.url, self.cfg)
            # Position in merged capture list (1..20), not provider-native rank.
            if ranks.get(brand) is None:
                ranks[brand] = i
        return ranks

    def _passage_from_text(self, url: str, brand: str, text: str,
                           fallback: str) -> Passage:
        chunk = text.strip()
        if not chunk:
            chunk = fallback[:500]
        digest = hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:8]
        url_key = hashlib.sha1(normalise_url(url).encode()).hexdigest()[:12]
        return Passage(
            id=f"{brand}:{url_key}:0:{digest}",
            brand=brand, text=chunk, file=url,
            words=len(chunk.split()),
        )

    def freeze_query(self, query_id: str, query: str,
                     store: Optional["RunStore"] = None) -> LivePool:
        """Search+fetch analysis pages into RunStore; return generation pool."""
        store = store or self.store
        if store is None:
            raise RuntimeError("freeze_query requires a RunStore")
        capture, hits, variants, captured_at = self._merge_capture(query)
        brand_ranks = self._brand_ranks(capture)
        capture_rows = []
        for i, r in enumerate(capture, 1):
            brand = brand_for_url(r.url, self.cfg)
            capture_rows.append({
                "position": i,
                "rank": r.rank,
                "rank_merged": i,
                "url": r.url,
                "domain": domain_of(r.url),
                "title": r.title,
                "snippet": r.snippet,
                "brand": brand,
                "source_query": r.source_query,
                "hit_count": hits.get(normalise_url(r.url), 1),
            })

        analysis = capture[: self.cfg.search_analysis_depth]
        # Fetch + clean only analysis-depth pages (generation pool).
        passages: List[Passage] = []
        page_logs: List[Dict] = []
        for r in analysis:
            brand = brand_for_url(r.url, self.cfg)
            html, status, method, fextra = self._fetch_html(r.url)
            body, jsonld = clean_html(html)
            clean = (body + " " + jsonld).strip()
            content_ok = bool(fextra.get("content_ok"))
            store.write_page(
                r.url, html, clean, http_status=status, method=method,
                extra=fextra)
            chunk = _best_chunk(clean, query, self.cfg) if clean else ""
            if not chunk:
                chunk = (r.snippet or r.title or r.url)[:500]
            passages.append(self._passage_from_text(
                r.url, brand, chunk, r.snippet or r.title or r.url))
            page_logs.append({
                "url": r.url, "brand": brand, "http_status": status,
                "method": method, "content_ok": content_ok,
                "words": len(clean.split()),
                "fetch_user_agent": fextra.get("fetch_user_agent"),
                "fallback": bool(fextra.get("fallback")),
                "fallback_corpus_url": fextra.get("fallback_corpus_url"),
                "fallback_corpus_fetched_at": fextra.get(
                    "fallback_corpus_fetched_at"),
            })

        fc_positions = [row["position"] for row in capture_rows
                        if row["brand"] == self.cfg.our_brand]
        fc_in_capture = bool(fc_positions)
        fc_search_rank = min(fc_positions) if fc_positions else None
        analysis_brands = [brand_for_url(r.url, self.cfg) for r in analysis]
        fc_present = self.cfg.our_brand in analysis_brands
        domains = {domain_of(r.url) for r in analysis}
        usable, missing = self._brand_coverage(page_logs)

        store.write_retrieval(query_id, {
            "query_id": query_id,
            "query": query,
            "fanout_queries": variants,
            "engine": self.cfg.search_provider,
            "market": self.cfg.search_region,
            "language": self.cfg.search_language,
            "capture_depth": self.cfg.search_capture_depth,
            "analysis_depth": self.cfg.search_analysis_depth,
            "timestamp": captured_at,
            "fetch_user_agent": self.cfg.live_fetch_user_agent,
            "brand_ranks": brand_ranks,
            "brands_usable": usable,
            "brands_missing_usable": missing,
            "page_fetch_log": page_logs,
            "fc_in_capture": fc_in_capture,
            "fc_search_rank": fc_search_rank,
            "results": capture_rows,
            "analysis_urls": [r.url for r in analysis],
        })

        return LivePool(
            passages=passages,
            fanout_queries=variants,
            retrieved_urls=[r.url for r in analysis],
            retrieved_ranks=[r.rank for r in analysis],
            retrieved_brands=analysis_brands,
            fc_present=fc_present,
            fc_search_rank=fc_search_rank,
            fc_in_capture=fc_in_capture,
            n_distinct_domains=len(domains),
            search_captured_at=captured_at,
            hit_counts=hits,
            capture_results=capture_rows,
            brand_ranks=brand_ranks,
            brands_usable=usable,
            brands_missing_usable=missing,
            page_fetch_log=page_logs,
            fetch_user_agent=self.cfg.live_fetch_user_agent,
            analysis_depth=self.cfg.search_analysis_depth,
            capture_depth=self.cfg.search_capture_depth,
        )

    def pool_from_freeze(self, query_id: str, query: str,
                         store: Optional["RunStore"] = None) -> LivePool:
        """Load frozen retrieval + pages; verify hashes; build passages."""
        store = store or self.store
        if store is None:
            raise RuntimeError("pool_from_freeze requires a RunStore")
        data = store.read_retrieval(query_id)
        analysis_urls = data.get("analysis_urls") or [
            r["url"] for r in data["results"][: self.cfg.search_analysis_depth]
        ]
        store.verify_frozen_pages(analysis_urls)

        passages: List[Passage] = []
        urls, ranks, brands = [], [], []
        page_logs: List[Dict] = list(data.get("page_fetch_log") or [])
        if not page_logs:
            page_logs = []
        for url in analysis_urls:
            row = next(r for r in data["results"] if r["url"] == url)
            brand = row.get("brand") or brand_for_url(url, self.cfg)
            page = store.read_page(url)
            if page is None:
                raise RuntimeError(f"frozen page missing for {url}")
            clean = page.get("clean") or ""
            if not clean.strip() and page.get("html"):
                body, jsonld = clean_html(page["html"])
                clean = (body + " " + jsonld).strip()
                store.write_page(url, page["html"], clean,
                                 http_status=int(page.get("http_status") or 0),
                                 method=page.get("method") or "browser-ua")
            content_ok = bool(page.get("content_ok"))
            if "content_ok" not in page:
                content_ok = self._classify_html(
                    page.get("html") or "",
                    int(page.get("http_status") or 0)) == "ok"
            chunk = _best_chunk(clean, query, self.cfg) if clean else ""
            if not chunk:
                chunk = (row.get("snippet") or row.get("title") or url)[:500]
            passages.append(self._passage_from_text(
                url, brand, chunk, row.get("snippet") or url))
            urls.append(url)
            ranks.append(int(row.get("rank") or 0))
            brands.append(brand)
            if not any(p.get("url") == url for p in page_logs):
                page_logs.append({
                    "url": url, "brand": brand,
                    "http_status": page.get("http_status"),
                    "method": page.get("method"),
                    "content_ok": content_ok,
                    "words": len(clean.split()),
                    "fallback": bool(page.get("fallback")),
                    "fallback_corpus_url": page.get("fallback_corpus_url"),
                    "fallback_corpus_fetched_at": page.get(
                        "fallback_corpus_fetched_at"),
                })

        if not passages:
            raise RuntimeError(f"empty analysed pool from freeze for {query_id}")

        usable = list(data.get("brands_usable") or [])
        missing = list(data.get("brands_missing_usable") or [])
        if not usable and not missing:
            usable, missing = self._brand_coverage(page_logs)

        return LivePool(
            passages=passages,
            fanout_queries=data.get("fanout_queries") or [query],
            retrieved_urls=urls,
            retrieved_ranks=ranks,
            retrieved_brands=brands,
            fc_present=self.cfg.our_brand in brands,
            fc_search_rank=data.get("fc_search_rank"),
            fc_in_capture=bool(data.get("fc_in_capture")),
            n_distinct_domains=len({domain_of(u) for u in urls}),
            search_captured_at=data.get("timestamp") or "",
            capture_results=data.get("results") or [],
            brand_ranks=data.get("brand_ranks") or {},
            brands_usable=usable,
            brands_missing_usable=missing,
            page_fetch_log=page_logs,
            fetch_user_agent=(data.get("fetch_user_agent")
                              or self.cfg.live_fetch_user_agent),
            analysis_depth=int(data.get("analysis_depth")
                               or self.cfg.search_analysis_depth),
            capture_depth=int(data.get("capture_depth")
                              or self.cfg.search_capture_depth),
        )

    def build_pool(self, query: str, *, urls_only: bool = False,
                   query_id: str = "adhoc") -> LivePool:
        """Convenience: freeze-less build (uses disk search cache + page cache)."""
        capture, hits, variants, captured_at = self._merge_capture(query)
        brand_ranks = self._brand_ranks(capture)
        capture_rows = []
        for i, r in enumerate(capture, 1):
            brand = brand_for_url(r.url, self.cfg)
            capture_rows.append({
                "position": i, "rank": r.rank, "rank_merged": i,
                "url": r.url, "domain": domain_of(r.url),
                "title": r.title, "snippet": r.snippet, "brand": brand,
                "source_query": r.source_query,
                "hit_count": hits.get(normalise_url(r.url), 1),
            })
        analysis = capture[: self.cfg.search_analysis_depth]
        passages: List[Passage] = []
        page_logs: List[Dict] = []
        for r in analysis:
            brand = brand_for_url(r.url, self.cfg)
            if urls_only:
                snippet = (r.snippet or r.title or r.url)[:500]
                passages.append(self._passage_from_text(
                    r.url, brand, snippet, snippet))
                page_logs.append({
                    "url": r.url, "brand": brand, "content_ok": False,
                    "method": "urls-only",
                })
            else:
                html, status, method, fextra = self._fetch_html(r.url)
                body, jsonld = clean_html(html)
                text = (body + " " + jsonld).strip()
                chunk = _best_chunk(text, query, self.cfg) if text else ""
                if not chunk:
                    chunk = (r.snippet or r.title or r.url)[:500]
                passages.append(self._passage_from_text(
                    r.url, brand, chunk, r.snippet or r.title or r.url))
                if self.store is not None:
                    self.store.write_page(
                        r.url, html, text, http_status=status, method=method,
                        extra=fextra)
                page_logs.append({
                    "url": r.url, "brand": brand, "http_status": status,
                    "method": method,
                    "content_ok": bool(fextra.get("content_ok")),
                    "words": len(text.split()),
                    "fallback": bool(fextra.get("fallback")),
                })

        brands = [p.brand for p in passages]
        fc_positions = [row["position"] for row in capture_rows
                        if row["brand"] == self.cfg.our_brand]
        usable, missing = self._brand_coverage(page_logs)
        return LivePool(
            passages=passages,
            fanout_queries=variants,
            retrieved_urls=[r.url for r in analysis],
            retrieved_ranks=[r.rank for r in analysis],
            retrieved_brands=brands,
            fc_present=self.cfg.our_brand in brands,
            fc_search_rank=min(fc_positions) if fc_positions else None,
            fc_in_capture=bool(fc_positions),
            n_distinct_domains=len({domain_of(r.url) for r in analysis}),
            search_captured_at=captured_at,
            hit_counts=hits,
            capture_results=capture_rows,
            brand_ranks=brand_ranks,
            brands_usable=usable,
            brands_missing_usable=missing,
            page_fetch_log=page_logs,
            fetch_user_agent=self.cfg.live_fetch_user_agent,
            analysis_depth=self.cfg.search_analysis_depth,
            capture_depth=self.cfg.search_capture_depth,
        )

    def _persist_fanout_record(self, query: str, variants: List[str]) -> None:
        path = self.cfg.results_dir / "fanout_queries.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "query": query, "variants": variants,
            "model": self.cfg.fanout_model, "n": len(variants),
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _classify_html(self, html: str, status: int) -> str:
        """Return 'ok' | 'bot-wall' | 'js-shell' | 'thin' | 'empty'."""
        if not (html or "").strip():
            return "empty"
        # Prefer cleaned yield: a page with enough extractable text is usable
        # even if scripts mention captcha (false-positive wall labels).
        body, jsonld = clean_html(html)
        words = len((body + " " + jsonld).split())
        if words >= self.cfg.live_fetch_min_words:
            return "ok"
        low = html.lower()
        if status == 429 or "bot or not?" in low or (
                "captcha" in low and ("akamai" in low or "perimeter" in low
                                      or "challenge" in low)):
            return "bot-wall"
        if "enable javascript" in low and len(html) < 5000:
            return "js-shell"
        if words < self.cfg.live_fetch_min_words:
            return "thin"
        return "ok"

    def _corpus_fallback(self, url: str) -> Optional[Dict[str, str]]:
        """Exact-URL corpus match only. Soft/path matching is forbidden."""
        manifest = self.cfg.corpus_dir / "manifest_baseline.csv"
        if not manifest.exists():
            return None
        key = normalise_url(url)
        for row in csv.DictReader(manifest.open(encoding="utf-8")):
            u = (row.get("url") or "").strip()
            if not u or u.upper() == "NONE":
                continue
            if normalise_url(u) != key:
                continue
            path = Path(row["file"])
            if not path.exists():
                path = self.cfg.corpus_dir / "baseline" / row.get(
                    "brand", "") / Path(row["file"]).name
            if not path.exists():
                return None
            return {
                "html": path.read_text(encoding="utf-8", errors="replace"),
                "corpus_url": u,
                "corpus_path": str(path),
                "corpus_fetched_at": (row.get("fetched_at") or "").strip(),
                "corpus_method": (row.get("method") or "").strip(),
            }
        return None

    def _log_fallback(self, record: Dict, kind: str) -> None:
        path = self.cfg.results_dir / "corpus_fallback_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        if kind == "corpus":
            print(
                "  [corpus-fallback EXACT-URL] "
                f"live={record['live_url']}  corpus={record['corpus_url']}  "
                f"live_fetch={record['live_fetched_at']}  "
                f"corpus_capture={record['corpus_fetched_at'] or 'UNKNOWN'}  "
                "NOTE: corpus capture date may differ from live freeze — confound."
            )
        else:
            print(
                "  [common-crawl EXACT-URL] "
                f"live={record['live_url']}  "
                f"crawl={record.get('cc_index')}  "
                f"capture={record.get('cc_timestamp')}  "
                f"words≈{record.get('words', '?')}  "
                "NOTE: archive capture date may differ from live freeze — confound."
            )

    def _log_corpus_fallback(self, record: Dict) -> None:
        self._log_fallback(record, "corpus")

    def _cc_session(self) -> requests.Session:
        if not hasattr(self, "_cc_sess") or self._cc_sess is None:
            sess = requests.Session()
            sess.headers.update({
                "User-Agent": "Team62-QUT-GEO-Bench/1.0 (research; contact: teamlead@example.com)",
                "Accept": "application/json,text/plain,*/*",
            })
            self._cc_sess = sess
        return self._cc_sess

    def _cc_get(self, url: str, *, params: Optional[Dict] = None,
                headers: Optional[Dict] = None, timeout: int = 60,
                retries: int = 4) -> Optional[requests.Response]:
        """GET with polite backoff — Common Crawl indexes rate-limit aggressively."""
        sess = self._cc_session()
        delay = 1.5
        for attempt in range(retries):
            try:
                resp = sess.get(url, params=params, headers=headers,
                                timeout=timeout)
            except Exception as exc:
                print(f"  [common-crawl] attempt {attempt+1}/{retries}: {exc}")
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            if resp.status_code in (429, 503, 504) or (
                    resp.status_code == 500):
                print(f"  [common-crawl] HTTP {resp.status_code}; "
                      f"backoff {delay:.1f}s")
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            return resp
        return None

    def _common_crawl_fallback(self, url: str) -> Optional[Dict[str, str]]:
        """Exact-URL HTML from Common Crawl (data-host cluster.idx; dated)."""
        from .common_crawl import fetch_exact_url

        indexes = tuple(getattr(self.cfg, "common_crawl_indexes", ()) or ())
        got = fetch_exact_url(url, crawls=indexes or None)
        if not got:
            return None
        kind = self._classify_html(got["html"], 200)
        if kind != "ok":
            return None
        return {
            "html": got["html"],
            "cc_url": got["cc_url"],
            "cc_index": got["cc_index"],
            "cc_timestamp": got["cc_timestamp"],
            "cc_filename": got.get("cc_filename") or "",
            "words": str(got.get("words") or 0),
        }

    def _fetch_common_crawl_record(self, rec: Dict) -> str:
        """Download one WARC record by byte range and return HTML body."""
        from .common_crawl import fetch_warc_html
        return fetch_warc_html(rec)

    def _http_get(self, url: str, user_agent: str) -> Tuple[str, int]:
        if not self._robots_allowed(url):
            print(f"  [skip] robots.txt disallows {url}")
            return "", 0
        try:
            resp = requests.get(url, timeout=_LIVE_FETCH_TIMEOUT, headers={
                "User-Agent": user_agent,
                "Accept": ("text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,*/*;q=0.8"),
                "Accept-Language": "en-AU,en;q=0.9",
                "Cache-Control": "no-cache",
                "Upgrade-Insecure-Requests": "1",
            })
            time.sleep(self.fetcher.delay)
            return resp.text or "", resp.status_code
        except Exception as exc:
            print(f"  [FAILED] {url}: {exc}")
            return "", 0

    def _fetch_html(self, url: str, *, force: bool = False
                    ) -> Tuple[str, int, str, Dict]:
        """Plain HTTP with the single configured UA for every brand.

        Exact-URL corpus fallback only when live fetch is unusable.
        Returns (html, status, method, fetch_extra).
        """
        ua = self.cfg.live_fetch_user_agent
        live_fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        extra: Dict = {
            "fetch_user_agent": ua,
            "content_ok": False,
            "live_fetched_at": live_fetched_at,
        }

        if not force:
            cached = self.cache.get_page(url)
            if cached:
                html = cached.get("html") or ""
                status = int(cached.get("http_status") or 0)
                method = cached.get("method") or "cache"
                cached_ua = cached.get("fetch_user_agent") or ""
                # Reject mixed-UA or soft-fallback cache from earlier freezes.
                ua_ok = cached_ua == ua
                method_ok = method in (
                    "browser-ua",
                    "corpus-fallback-exact-url",
                    "common-crawl-exact-url",
                    "cache",
                )
                kind = self._classify_html(html, status)
                if kind == "ok" and ua_ok and method_ok:
                    extra["content_ok"] = True
                    extra["fetch_user_agent"] = ua
                    if method in (
                        "corpus-fallback-exact-url",
                        "common-crawl-exact-url",
                    ):
                        extra["fallback"] = True
                        for k in (
                            "fallback_corpus_url",
                            "fallback_corpus_fetched_at",
                            "fallback_cc_url",
                            "fallback_cc_index",
                            "fallback_cc_timestamp",
                        ):
                            if cached.get(k):
                                extra[k] = cached[k]
                    return html, status, method, extra
                why = (f"{kind}" if kind != "ok" else
                       ("ua-mismatch" if not ua_ok else "stale-method"))
                print(f"  [refetch] cached page is {why}: {url}")

        # Identical browser UA for FC, Skyscanner, Webjet, Expedia, other.
        html, status = self._http_get(url, ua)
        kind = self._classify_html(html, status)
        method = "browser-ua"
        if kind == "ok":
            extra["content_ok"] = True
            self.cache.put_page(url, html, status=status, method=method,
                                fetch_user_agent=ua)
            return html, status, method, extra

        print(f"  [live-fetch] {kind} status={status} for {url}")

        # Exact-URL corpus fallback only (documented capture-date confound).
        fb = self._corpus_fallback(url)
        if fb is not None:
            kind2 = self._classify_html(fb["html"], 200)
            if kind2 == "ok":
                # Guard: normalised URLs must be identical (never soft-match).
                if normalise_url(url) != normalise_url(fb["corpus_url"]):
                    raise AssertionError(
                        "corpus fallback URL mismatch: "
                        f"live={url!r} corpus={fb['corpus_url']!r}")
                log = {
                    "live_url": url,
                    "corpus_url": fb["corpus_url"],
                    "corpus_path": fb["corpus_path"],
                    "live_fetched_at": live_fetched_at,
                    "live_http_status": status,
                    "live_kind": kind,
                    "corpus_fetched_at": fb["corpus_fetched_at"],
                    "corpus_method": fb["corpus_method"],
                    "fetch_user_agent": ua,
                    "note": ("Corpus HTML substituted for bot-walled/thin live "
                             "fetch; capture dates may differ — confound."),
                }
                self._log_corpus_fallback(log)
                extra.update({
                    "content_ok": True,
                    "fallback": True,
                    "fallback_live_url": url,
                    "fallback_corpus_url": fb["corpus_url"],
                    "fallback_corpus_fetched_at": fb["corpus_fetched_at"],
                    "fallback_corpus_path": fb["corpus_path"],
                    "live_http_status": status,
                    "live_kind": kind,
                })
                self.cache.put_page(
                    url, fb["html"], status=200,
                    method="corpus-fallback-exact-url",
                    fetch_user_agent=ua)
                # Persist fallback URLs/dates on the cache record too.
                cpath = self.cache.page_path(url)
                crec = json.loads(cpath.read_text(encoding="utf-8"))
                crec.update({
                    "fallback_corpus_url": fb["corpus_url"],
                    "fallback_corpus_fetched_at": fb["corpus_fetched_at"],
                    "live_fetched_at": live_fetched_at,
                })
                cpath.write_text(json.dumps(crec, ensure_ascii=False),
                                 encoding="utf-8")
                return fb["html"], 200, "corpus-fallback-exact-url", extra

        # Exact-URL Common Crawl archive (public web crawl; dated confound).
        cc = self._common_crawl_fallback(url)
        if cc is not None:
            log = {
                "live_url": url,
                "cc_url": cc["cc_url"],
                "cc_index": cc["cc_index"],
                "cc_timestamp": cc["cc_timestamp"],
                "cc_filename": cc["cc_filename"],
                "live_fetched_at": live_fetched_at,
                "live_http_status": status,
                "live_kind": kind,
                "words": int(cc.get("words") or 0),
                "fetch_user_agent": ua,
                "source": "common-crawl",
                "note": ("Common Crawl HTML substituted for bot-walled/thin "
                         "live fetch; archive date may differ — confound."),
            }
            self._log_fallback(log, "common-crawl")
            extra.update({
                "content_ok": True,
                "fallback": True,
                "fallback_live_url": url,
                "fallback_cc_url": cc["cc_url"],
                "fallback_cc_index": cc["cc_index"],
                "fallback_cc_timestamp": cc["cc_timestamp"],
                "live_http_status": status,
                "live_kind": kind,
            })
            self.cache.put_page(
                url, cc["html"], status=200,
                method="common-crawl-exact-url",
                fetch_user_agent=ua)
            cpath = self.cache.page_path(url)
            crec = json.loads(cpath.read_text(encoding="utf-8"))
            crec.update({
                "fallback_cc_url": cc["cc_url"],
                "fallback_cc_index": cc["cc_index"],
                "fallback_cc_timestamp": cc["cc_timestamp"],
                "live_fetched_at": live_fetched_at,
            })
            cpath.write_text(json.dumps(crec, ensure_ascii=False),
                             encoding="utf-8")
            return cc["html"], 200, "common-crawl-exact-url", extra

        # Keep unusable shell — finding, not silent drop.
        method = f"browser-ua-{kind}"
        extra.update({"content_ok": False, "live_kind": kind})
        self.cache.put_page(url, html, status=status, method=method,
                            fetch_user_agent=ua)
        return html, status, method, extra

    def repair_store_pages(self, store: "RunStore",
                           brands: Optional[List[str]] = None) -> Dict[str, int]:
        """Re-fetch thin/bot-walled pages; fill via corpus/Common Crawl."""
        target = set(brands or ["*"])
        stats = {"checked": 0, "repaired": 0, "still_thin": 0,
                 "by_method": {}}
        for meta_path in sorted(store.pages_dir.glob("*/meta.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            url = meta.get("url") or ""
            brand = brand_for_url(url, self.cfg)
            if "*" not in target and brand not in target and "other" not in target:
                continue
            html0 = (meta_path.parent / "raw.html").read_text(
                encoding="utf-8", errors="replace")
            kind0 = self._classify_html(
                html0, int(meta.get("http_status") or 0))
            # Only repair pages that are still unusable after reclassification.
            if kind0 == "ok":
                # Re-label pages that already had usable cleaned text but were
                # marked bot-wall by an over-strict heuristic (e.g. captcha JS).
                if not meta.get("content_ok"):
                    body, jsonld = clean_html(html0)
                    clean = (body + " " + jsonld).strip()
                    method0 = meta.get("method") or "browser-ua"
                    if str(method0).startswith("browser-ua-"):
                        method0 = "browser-ua"
                    store.write_page(
                        url, html0, clean,
                        http_status=int(meta.get("http_status") or 200),
                        method=method0,
                        extra={
                            "content_ok": True,
                            "fetch_user_agent": meta.get(
                                "fetch_user_agent",
                                self.cfg.live_fetch_user_agent),
                            "reclassified": True,
                        },
                    )
                    stats["repaired"] += 1
                    print(f"  [reclassified-ok] {brand} "
                          f"words={len(clean.split())}: {url}")
                continue
            stats["checked"] += 1
            # Archive-first for pages already known unusable — avoid re-hitting
            # live 429 walls before consulting Common Crawl / corpus.
            filled = self._archive_fill(url, live_kind=kind0)
            if filled is not None:
                html, status, method, fextra = filled
            else:
                html, status, method, fextra = self._fetch_html(
                    url, force=True)
            body, jsonld = clean_html(html)
            clean = (body + " " + jsonld).strip()
            store.write_page(url, html, clean, http_status=status,
                             method=method, extra=fextra)
            stats["by_method"][method] = stats["by_method"].get(method, 0) + 1
            if fextra.get("content_ok"):
                stats["repaired"] += 1
                print(f"  [repaired] {brand} words={len(clean.split())} "
                      f"via {method}: {url}")
            else:
                stats["still_thin"] += 1
                print(f"  [still-{fextra.get('live_kind', kind0)}] "
                      f"{brand}: {url}")
        self._refresh_retrieval_coverage(store)
        return stats

    def _archive_fill(self, url: str, *, live_kind: str
                      ) -> Optional[Tuple[str, int, str, Dict]]:
        """Exact-URL corpus then Common Crawl; no live HTTP."""
        ua = self.cfg.live_fetch_user_agent
        live_fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        fb = self._corpus_fallback(url)
        if fb is not None and self._classify_html(fb["html"], 200) == "ok":
            if normalise_url(url) != normalise_url(fb["corpus_url"]):
                raise AssertionError(
                    "corpus fallback URL mismatch: "
                    f"live={url!r} corpus={fb['corpus_url']!r}")
            log = {
                "live_url": url,
                "corpus_url": fb["corpus_url"],
                "corpus_path": fb["corpus_path"],
                "live_fetched_at": live_fetched_at,
                "live_kind": live_kind,
                "corpus_fetched_at": fb["corpus_fetched_at"],
                "corpus_method": fb["corpus_method"],
                "fetch_user_agent": ua,
                "note": ("Corpus HTML substituted for bot-walled/thin live "
                         "fetch; capture dates may differ — confound."),
            }
            self._log_corpus_fallback(log)
            extra = {
                "fetch_user_agent": ua,
                "content_ok": True,
                "fallback": True,
                "fallback_live_url": url,
                "fallback_corpus_url": fb["corpus_url"],
                "fallback_corpus_fetched_at": fb["corpus_fetched_at"],
                "fallback_corpus_path": fb["corpus_path"],
                "live_kind": live_kind,
                "live_fetched_at": live_fetched_at,
            }
            return fb["html"], 200, "corpus-fallback-exact-url", extra

        cc = self._common_crawl_fallback(url)
        if cc is not None:
            log = {
                "live_url": url,
                "cc_url": cc["cc_url"],
                "cc_index": cc["cc_index"],
                "cc_timestamp": cc["cc_timestamp"],
                "cc_filename": cc["cc_filename"],
                "live_fetched_at": live_fetched_at,
                "live_kind": live_kind,
                "words": int(cc.get("words") or 0),
                "fetch_user_agent": ua,
                "source": "common-crawl",
                "note": ("Common Crawl HTML substituted for bot-walled/thin "
                         "live fetch; archive date may differ — confound."),
            }
            self._log_fallback(log, "common-crawl")
            extra = {
                "fetch_user_agent": ua,
                "content_ok": True,
                "fallback": True,
                "fallback_live_url": url,
                "fallback_cc_url": cc["cc_url"],
                "fallback_cc_index": cc["cc_index"],
                "fallback_cc_timestamp": cc["cc_timestamp"],
                "live_kind": live_kind,
                "live_fetched_at": live_fetched_at,
            }
            return cc["html"], 200, "common-crawl-exact-url", extra
        return None

    def _refresh_retrieval_coverage(self, store: "RunStore") -> None:
        """Rebuild page_fetch_log + brands_usable from repaired page metas."""
        for rpath in sorted(store.retrieval_dir.glob("Q*.json")):
            data = json.loads(rpath.read_text(encoding="utf-8"))
            analysis = data.get("analysis_urls") or [
                r["url"] for r in data.get("results", [])[
                    : self.cfg.search_analysis_depth]
            ]
            page_logs: List[Dict] = []
            for url in analysis:
                meta = store.read_page(url) or {}
                brand = brand_for_url(url, self.cfg)
                page_logs.append({
                    "url": url,
                    "brand": brand,
                    "http_status": meta.get("http_status"),
                    "method": meta.get("method"),
                    "content_ok": bool(meta.get("content_ok")),
                    "words": meta.get("words"),
                    "fetch_user_agent": meta.get("fetch_user_agent"),
                    "fallback": bool(meta.get("fallback")),
                    "fallback_corpus_url": meta.get("fallback_corpus_url"),
                    "fallback_corpus_fetched_at": meta.get(
                        "fallback_corpus_fetched_at"),
                    "fallback_cc_url": meta.get("fallback_cc_url"),
                    "fallback_cc_index": meta.get("fallback_cc_index"),
                    "fallback_cc_timestamp": meta.get("fallback_cc_timestamp"),
                })
            usable, missing = self._brand_coverage(page_logs)
            data["page_fetch_log"] = page_logs
            data["brands_usable"] = usable
            data["brands_missing_usable"] = missing
            store.write_json(rpath, data)

    def substitute_fc(self, pool: LivePool, arm: str) -> LivePool:
        if arm == "baseline":
            return pool
        arm_map = _load_arm_fc_text_by_url(arm, self.cfg)
        new_passages: List[Passage] = []
        for p in pool.passages:
            if p.brand != self.cfg.our_brand:
                new_passages.append(p)
                continue
            opt = arm_map.get(normalise_url(p.file))
            if opt is None:
                print(f"  [live] no optimised text for FC url={p.file} "
                      f"arm={arm}; keeping live baseline text")
                new_passages.append(p)
                continue
            chunk = _best_chunk(opt, pool.fanout_queries[0], self.cfg) or opt
            new_passages.append(self._passage_from_text(
                p.file, p.brand, chunk, chunk))
        return LivePool(
            passages=new_passages,
            fanout_queries=pool.fanout_queries,
            retrieved_urls=pool.retrieved_urls,
            retrieved_ranks=pool.retrieved_ranks,
            retrieved_brands=pool.retrieved_brands,
            fc_present=pool.fc_present,
            fc_search_rank=pool.fc_search_rank,
            fc_in_capture=pool.fc_in_capture,
            n_distinct_domains=pool.n_distinct_domains,
            search_captured_at=pool.search_captured_at,
            hit_counts=pool.hit_counts,
            capture_results=pool.capture_results,
            brand_ranks=pool.brand_ranks,
            brands_usable=pool.brands_usable,
            brands_missing_usable=pool.brands_missing_usable,
            page_fetch_log=pool.page_fetch_log,
            fetch_user_agent=pool.fetch_user_agent,
            analysis_depth=pool.analysis_depth,
            capture_depth=pool.capture_depth,
        )


def _load_arm_fc_text_by_url(arm: str, cfg: Config) -> Dict[str, str]:
    out: Dict[str, str] = {}
    manifest = cfg.corpus_dir / "manifest_baseline.csv"
    if not manifest.exists():
        return out
    arm_fc = cfg.corpus_dir / arm / cfg.our_brand
    if not arm_fc.is_dir():
        return out
    for row in csv.DictReader(manifest.open(encoding="utf-8")):
        if row.get("brand", "").strip() != cfg.our_brand:
            continue
        url = row.get("url", "").strip()
        if not url or url.upper() == "NONE":
            continue
        arm_path = arm_fc / Path(row["file"]).name
        if not arm_path.exists():
            continue
        body, jsonld = clean_html(
            arm_path.read_text(encoding="utf-8", errors="ignore"))
        text = (body + " " + jsonld).strip()
        if text:
            out[normalise_url(url)] = text
    return out
