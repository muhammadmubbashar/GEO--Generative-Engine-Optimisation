"""Single source of truth for every experimental parameter.

Nothing in this package hard-codes a parameter. If a value were written in two
modules, two teammates could unknowingly run two different experiments and the
comparison would be void. Changing anything here requires one line in
decisions_log.md.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # ---- provider -----------------------------------------------------
    # For the real baseline: mode="openai", then set OPENAI_API_KEY in the shell.
    # Claude later: mode="anthropic" (+ ANTHROPIC_API_KEY and OPENAI_API_KEY for embeds).
    mode: str = "openai"             # "offline" | "ollama" | "openai" | "anthropic"
    gen_model: str = "gpt-5.6-luna"  # OpenAI chat model for generation
                                     # anthropic: e.g. "claude-sonnet-4-5"
                                     # ollama: e.g. "llama3.2:3b"
    embed_model: str = "text-embedding-3-small"  # OpenAI embeddings for retrieval
                                                 # ollama: "nomic-embed-text"
    ollama_host: str = "http://localhost:11434"
    temperature: float = 0.7          # Aggarwal et al.: temperature=0.7
    top_p: float = 1.0                # Aggarwal et al.: top_p=1
    # Only these modes may write scored deliverables. offline/ollama are for
    # pipeline smoke tests (--allow-demo); their outputs go under demo_dir.
    reportable_modes: tuple = ("openai", "anthropic")

    # ---- corpus -------------------------------------------------------
    our_brand: str = "flightcentre"
    brands: tuple = ("flightcentre", "skyscanner", "webjet", "expedia")
    # Chosen from a live probe of Australian flight queries: one metasearch
    # (Skyscanner), one AU-native OTA (Webjet), one global OTA (Expedia).
    # Kayak / momondo / Cheapflights excluded — all Booking Holdings, so
    # including several would count one corporate group as three rivals.

    # ---- chunking -----------------------------------------------------
    chunk_words: int = 350
    chunk_overlap: int = 40

    # ---- retrieval ----------------------------------------------------
    use_hybrid: bool = True           # BM25 + dense, fused by RRF. Entity
                                      # enrichment adds exact tokens (airline
                                      # names, fares, durations) that dense
                                      # retrieval alone under-rewards.
    rrf_k: int = 60
    # Aggarwal et al. used Google's top-5 once. With only 4 brands in the
    # mini-web, k=5 keeps the context tight and competitive (not padded).
    top_k: int = 5
    # Cap 2 with k=5 ⇒ at least 3 brands in every answer context. Cap 3
    # would let one brand own 60% of a 5-slot window.
    cap_per_brand: int = 2

    # ---- generation ---------------------------------------------------
    # Protocol: 5 runs × 2 seeds per query per arm per layer (pre-registered).
    runs_per_query: int = 5
    seeds: tuple = (1, 2)
    shuffle_passages: bool = True     # C-SEO Bench: context rank dominates,
                                      # so position must be randomised

    # ---- design -------------------------------------------------------
    retrieval_variants: tuple = ("fixed", "reindexed", "live")
    # fixed     : candidate set frozen from baseline; only FC passage TEXT is
    #             swapped. Replicates Aggarwal et al. exactly.
    # reindexed : index rebuilt per arm; retrieval can also respond.
    # live      : candidate pool from live web search (generation-stage only;
    #             search ranked the original page; FC text may be substituted).

    # ---- live retrieval layer -----------------------------------------
    # Provider is fixed for the entire study (Brave). Do not switch mid-run.
    search_provider: str = "brave"        # "brave" | "serper" | "tavily"
    # Capture deep, analyse shallow. Pool size follows the benchmark literature:
    # C-SEO Bench uses 10 documents per query, Aggarwal et al. use 5. It is NOT
    # set with reference to Flight Centre's observed rank. Sensitivity is
    # reported at k=5 and k=10. Local top_k stays 5.
    search_capture_depth: int = 20        # what we fetch metadata for and store
    search_analysis_depth: int = 10       # what enters the generation pool
    # Backward-compatible alias used by older call sites (= analysis depth).
    search_results_per_query: int = 10
    fanout_variants: int = 3              # 1 disables fan-out
    fanout_model: str = "gpt-5.6-luna"    # model used to paraphrase queries
    search_cache_dir: Path = Path("cache/search")
    fetch_cache_dir: Path = Path("cache/pages")
    fanout_cache_dir: Path = Path("cache/fanout")
    runs_dir: Path = Path("runs")
    search_region: str = "AU"             # client market
    search_language: str = "en"
    # Live page fetch: plain HTTP only (no JS). ONE user-agent for every brand
    # in the live layer — never mix research-bot and browser UAs across brands.
    # Skyscanner returns a JS shell to GPTBot/research UAs but SSR to this UA;
    # Expedia often returns HTTP 429. Fallback chain (exact URL only):
    #   1) live browser UA  2) local corpus  3) Common Crawl public archive
    # Soft/path matching is forbidden. Archive/corpus capture dates are a
    # documented confound (logged), not a silent substitute.
    live_fetch_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    live_fetch_min_words: int = 40        # below this → treat as thin/shell
    # Recent Common Crawl indexes to probe for exact-URL archive fallback.
    common_crawl_indexes: tuple = (
        "CC-MAIN-2026-30",
        "CC-MAIN-2026-25",
        "CC-MAIN-2026-21",
        "CC-MAIN-2026-17",
        "CC-MAIN-2026-12",
        "CC-MAIN-2025-51",
        "CC-MAIN-2025-47",
        "CC-MAIN-2025-43",
    )
    # Primary endpoints (pre-registered): PAWC and citation share — not inclusion.
    # Domain → brand tag for live passages; anything else is "other".
    brand_domains: tuple = (
        ("flightcentre.com.au", "flightcentre"),
        ("flightcentre.com", "flightcentre"),
        ("skyscanner.com.au", "skyscanner"),
        ("skyscanner.com", "skyscanner"),
        ("webjet.com.au", "webjet"),
        ("expedia.com.au", "expedia"),
        ("expedia.com", "expedia"),
    )

    arms: tuple = (
        "baseline",
        "position_control",     # force one FC passage to context position 1
        "schema_only",          # our contribution — untested by either paper
        "faq_structure_only",   # our contribution
        "statistics_addition",  # their method, fact-grounded
        "cite_sources",         # their method, real sources only
        "keyword_stuffing",     # negative control: both papers report failure
        "full_stack",
    )

    page_types: tuple = (
        "route", "origin_hub", "destination_hub", "deals_sale",
        "cabin_class", "multi_city_rtw", "airline", "flight_advice",
    )

    # ---- pre-registered primary analysis family -----------------------
    # Holm correction applies within this family only. All other metric ×
    # variant × stratum tables are exploratory and must be labelled as such.
    primary_stratum: str = "primary"       # Q01–Q22 flight consideration
    primary_metric: str = "pawc"
    primary_variant: str = "reindexed"

    # ---- paths --------------------------------------------------------
    corpus_dir: Path = Path("corpus")
    queries_file: Path = Path("queries/queries.csv")
    heldout_file: Path = Path("queries/heldout.csv")
    results_dir: Path = Path("results")

    @property
    def demo_dir(self) -> Path:
        return self.results_dir / "_demo"

    def index_path(self, arm: str) -> Path:
        return self.results_dir / f"index_{arm}.pkl"

    def vectors_path(self, arm: str) -> Path:
        return self.results_dir / f"vecs_{arm}.npz"

    def answers_path(self, arm: str, variant: str) -> Path:
        return self.results_dir / f"answers_{arm}_{variant}.jsonl"

    def scores_path(self, arm: str, variant: str) -> Path:
        return self.results_dir / f"scores_{arm}_{variant}.csv"

    def resolve_answers_path(self, arm: str, variant: str) -> Path:
        """Prefer reportable results/; fall back to _demo/ for ollama smoke."""
        main = self.answers_path(arm, variant)
        if main.exists() and main.stat().st_size > 0:
            return main
        demo = self.demo_dir / main.name
        if demo.exists() and demo.stat().st_size > 0:
            return demo
        return main

    def resolve_scores_path(self, arm: str, variant: str,
                            answers: Path = None) -> Path:
        """Write scores next to the answers file (results/ or _demo/)."""
        ans = answers or self.resolve_answers_path(arm, variant)
        return ans.parent / f"scores_{arm}_{variant}.csv"


CONFIG = Config()
