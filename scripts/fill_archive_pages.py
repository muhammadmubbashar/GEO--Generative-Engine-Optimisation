"""Fill remaining unusable freeze pages via Common Crawl cluster.idx."""
from __future__ import annotations

import json
import time

from geo_bench.config import CONFIG
from geo_bench.experiment.run_store import RunStore
from geo_bench.retrieval.cleaner import clean_html
from geo_bench.search.live_retriever import LiveRetriever, brand_for_url

RUN_ID = "20260810_live_baseline_live_9b573c71"


def main() -> None:
    store = RunStore.open(RUN_ID, CONFIG)
    lr = LiveRetriever(CONFIG, refresh=False, store=store)
    items = []
    for meta_path in sorted(store.pages_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        url = meta.get("url") or ""
        brand = brand_for_url(url, CONFIG)
        html = (meta_path.parent / "raw.html").read_text(
            encoding="utf-8", errors="replace")
        kind = lr._classify_html(html, int(meta.get("http_status") or 0))
        if kind == "ok":
            if not meta.get("content_ok"):
                body, jsonld = clean_html(html)
                clean = (body + " " + jsonld).strip()
                method0 = meta.get("method") or "browser-ua"
                if str(method0).startswith("browser-ua-"):
                    method0 = "browser-ua"
                store.write_page(
                    url, html, clean,
                    http_status=int(meta.get("http_status") or 200),
                    method=method0,
                    extra={
                        "content_ok": True,
                        "fetch_user_agent": meta.get(
                            "fetch_user_agent", CONFIG.live_fetch_user_agent),
                        "reclassified": True,
                    },
                )
                print(f"[reclassified-ok] {brand} words={len(clean.split())}")
            continue
        items.append((0 if brand == "expedia" else 1, brand, url, kind))

    items.sort()
    print(f"to_fill={len(items)}", flush=True)
    repaired = still = 0
    for i, (_, brand, url, kind) in enumerate(items, 1):
        print(f"\n[{i}/{len(items)}] {brand} {kind}\n  {url}", flush=True)
        filled = lr._archive_fill(url, live_kind=kind)
        if filled is None:
            still += 1
            print(f"  [still-{kind}]", flush=True)
            continue
        html, status, method, fextra = filled
        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        store.write_page(url, html, clean, http_status=status,
                         method=method, extra=fextra)
        repaired += 1
        print(f"  [ok] words={len(clean.split())} via {method}", flush=True)
        time.sleep(0.5)

    lr._refresh_retrieval_coverage(store)
    print(f"\nDONE repaired={repaired} still={still}", flush=True)
    print("\nExpedia:")
    for meta_path in sorted(store.pages_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if brand_for_url(meta["url"], CONFIG) != "expedia":
            continue
        print(f"  w={meta.get('words'):5} ok={meta.get('content_ok')} "
              f"{meta.get('method'):28} {meta['url'][:75]}")


if __name__ == "__main__":
    main()
