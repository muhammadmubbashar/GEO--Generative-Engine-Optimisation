"""Single source of truth for every experimental parameter.

Nothing in this package hard-codes a parameter. If a value were written in two
modules, two teammates could unknowingly run two different experiments and the
comparison would be void. Changing anything here requires one line in
decisions_log.md.
"""
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE from .env without overriding a real environment."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()


@dataclass(frozen=True)
class Config:
    # ---- provider -----------------------------------------------------
    mode: str = "openai"             # "offline" | "ollama" | "openai" | "anthropic"
    gen_model: str = "gpt-5.6-luna"
    embed_model: str = "text-embedding-3-small"
    ollama_host: str = "http://localhost:11434"
    temperature: float = 0.7          # Aggarwal et al.: temperature=0.7
    top_p: float = 1.0                # Aggarwal et al.: top_p=1
    reportable_modes: tuple = ("openai", "anthropic")

    # ---- brands -------------------------------------------------------
    our_brand: str = "flightcentre"
    brands: tuple = ("flightcentre", "skyscanner", "webjet", "expedia")

    # ---- chunking -----------------------------------------------------
    chunk_words: int = 350
    chunk_overlap: int = 40
    # Hard cap so one "word" of concatenated JS/JSON cannot blow the
    # embedding 8192-token limit (~4 chars/token worst case).
    chunk_max_chars: int = 12000

    # ---- retrieval ----------------------------------------------------
    use_hybrid: bool = True
    rrf_k: int = 60
    top_k: int = 5
    cap_per_brand: int = 2
    # "brand": all unlisted domains share one `other` budget (primary,
    # locked with the baseline). "domain": cap applies per registrable
    # domain — sensitivity index only, never mixed with primary results.
    cap_scope: str = "brand"
    # rank_bm25 defaults, pinned so the lexical side is reproducible.
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    # ---- generation ---------------------------------------------------
    runs_per_query: int = 5
    seeds: tuple = (1, 2)
    shuffle_passages: bool = True
    # fixed = Aggarwal / C-SEO Bench / AutoGEO: cleaned FULL page per URL.
    # reindexed = ALCE-style RAG: one 350-word chunk (passage_prompt_chars).
    # page_prompt_chars ~24k (~3,500+ words) covers FC and typical OTA pages;
    # longer pages truncate at this cap (safety, not a second chunker).
    fixed_source_unit: str = "full_page"
    page_prompt_chars: int = 24000
    passage_prompt_chars: int = 2600

    # ---- design -------------------------------------------------------
    # Freeze (Brave capture) is upstream. Experimental layers:
    #   fixed     : frozen analysis-pool candidates; FC text swapped only
    #   reindexed : hybrid retrieval over ALL freeze pages (every query)
    retrieval_variants: tuple = ("fixed", "reindexed")

    # ---- live retrieval / freeze --------------------------------------
    search_provider: str = "brave"
    search_capture_depth: int = 20
    search_analysis_depth: int = 10
    search_results_per_query: int = 10
    fanout_variants: int = 3
    fanout_model: str = "gpt-5.6-luna"
    search_cache_dir: Path = Path("cache/search")
    fetch_cache_dir: Path = Path("cache/pages")
    fanout_cache_dir: Path = Path("cache/fanout")
    runs_dir: Path = Path("runs")
    search_region: str = "AU"
    search_language: str = "en"
    live_fetch_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    live_fetch_delay_seconds: float = 0.25
    # Below this after cleaning → treat live fetch as thin/shell and try CC.
    live_fetch_min_words: int = 40
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
        "ssr_visible",
        "position_control",
        "schema_only",
        "faq_structure_only",
        "statistics_addition",
        "cite_sources",
        "keyword_stuffing",
        "full_stack",
    )
    heldout_arms: tuple = ("baseline", "full_stack")

    # ---- usable-content QC --------------------------------------------
    min_usable_docs_per_query: int = 5
    thin_page_word_threshold: int = 200

    # ---- judged metrics (SCORING_RUBRICS.md v1.0) ---------------------
    judge_model: str = "gpt-5.6-luna"
    judge_temperature: float = 0.0
    rubric_version: str = "1.0"
    rubric_file: Path = Path("SCORING_RUBRICS.md")
    calibration_sample_size: int = 60
    kappa_threshold: float = 0.6
    extra_mask_brands: tuple = (
        "kayak", "momondo", "cheapflights", "booking.com", "tripadvisor",
        "orbitz", "priceline", "agoda", "lastminute", "cheapoair",
        "travelocity", "hotels.com", "trivago",
    )

    # ---- pre-registered endpoint families -----------------------------
    # Holm applies across arms × endpoints inside one family.
    primary_endpoints: tuple = ("pawc", "citation_share")
    secondary_endpoints: tuple = (
        "relevance", "response_quality", "inclusion", "retrieval_rank",
    )
    primary_stratum: str = "primary"
    primary_metric: str = "pawc"
    primary_variant: str = "reindexed"
    statistical_tests: tuple = (
        "wilcoxon_signed_rank_two_tailed",
        "bootstrap_95ci",
        "holm",
    )

    # ---- selection stage (engine-realistic gatekeeper) ----------------
    # Real engines (documented for ChatGPT Search) read title+snippet
    # metadata and decide which pages to fetch. This stage replays that
    # decision over the FROZEN capture-20 rows; it changes nothing else.
    selection_top_n: int = 5
    selection_model: str = ""          # empty = gen_model

    # ---- paths --------------------------------------------------------
    queries_file: Path = Path("queries/queries.csv")
    queries_expansion_file: Path = Path("queries/queries_expansion.csv")
    heldout_file: Path = Path("queries/heldout.csv")
    results_dir: Path = Path("results")
    active_run_file: Path = Path("runs/ACTIVE")

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

    def routing_path(self) -> Path:
        return self.results_dir / "routing.csv"

    def selection_path(self, arm: str) -> Path:
        return self.results_dir / f"selection_{arm}.csv"

    def resolve_answers_path(self, arm: str, variant: str) -> Path:
        main = self.answers_path(arm, variant)
        if main.exists() and main.stat().st_size > 0:
            return main
        demo = self.demo_dir / main.name
        if demo.exists() and demo.stat().st_size > 0:
            return demo
        return main

    def resolve_scores_path(self, arm: str, variant: str,
                            answers: Path = None) -> Path:
        ans = answers or self.resolve_answers_path(arm, variant)
        return ans.parent / f"scores_{arm}_{variant}.csv"


CONFIG = Config()
