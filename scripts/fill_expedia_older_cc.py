"""Try older Common Crawl indexes for remaining Expedia bot-walls."""
from geo_bench.config import CONFIG
from geo_bench.experiment.run_store import RunStore
from geo_bench.retrieval.cleaner import clean_html
from geo_bench.search.common_crawl import fetch_exact_url
from geo_bench.search.live_retriever import LiveRetriever, brand_for_url

RUN_ID = "20260810_live_baseline_live_9b573c71"
OLDER = (
    "CC-MAIN-2025-51",
    "CC-MAIN-2025-47",
    "CC-MAIN-2025-43",
    "CC-MAIN-2025-33",
    "CC-MAIN-2024-51",
)


def main() -> None:
    store = RunStore.open(RUN_ID, CONFIG)
    lr = LiveRetriever(CONFIG, refresh=False, store=store)
    targets = []
    for meta_path in sorted(store.pages_dir.glob("*/meta.json")):
        meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
        if brand_for_url(meta["url"], CONFIG) != "expedia":
            continue
        if meta.get("content_ok"):
            continue
        targets.append(meta["url"])
    print("remaining expedia", len(targets))
    for url in targets:
        print("\n?", url, flush=True)
        got = fetch_exact_url(url, crawls=OLDER)
        if not got:
            print("  no hit in older crawls", flush=True)
            continue
        body, jl = clean_html(got["html"])
        clean = (body + " " + jl).strip()
        extra = {
            "fetch_user_agent": CONFIG.live_fetch_user_agent,
            "content_ok": True,
            "fallback": True,
            "fallback_live_url": url,
            "fallback_cc_url": got["cc_url"],
            "fallback_cc_index": got["cc_index"],
            "fallback_cc_timestamp": got["cc_timestamp"],
            "live_kind": "bot-wall",
        }
        store.write_page(
            url, got["html"], clean, http_status=200,
            method="common-crawl-exact-url", extra=extra)
        print(f"  filled words={got['words']} via {got['cc_index']} "
              f"@{got['cc_timestamp']}", flush=True)
        lr._log_fallback({
            "live_url": url,
            "cc_url": got["cc_url"],
            "cc_index": got["cc_index"],
            "cc_timestamp": got["cc_timestamp"],
            "words": got["words"],
            "source": "common-crawl",
            "note": "Older CC crawl exact-URL fill",
        }, "common-crawl")
    lr._refresh_retrieval_coverage(store)
    print("\nExpedia final:")
    import json
    for meta_path in sorted(store.pages_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if brand_for_url(meta["url"], CONFIG) != "expedia":
            continue
        print(f"  w={meta.get('words'):5} ok={meta.get('content_ok')} "
              f"{meta.get('method')}")


if __name__ == "__main__":
    main()
