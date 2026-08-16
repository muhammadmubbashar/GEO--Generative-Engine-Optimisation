"""One-off diagnostic: what does each frozen URL serve to AI-crawler UAs?

For every unique URL in the frozen capture, fetch once with each bot
user-agent (OAI-SearchBot = ChatGPT Search's fetcher, GPTBot = OpenAI's
training crawler) and compare cleaned word counts against the frozen
browser-UA fetch. This quantifies the Type-A access gap (bot-blocking /
cloaking / CSR shells) per brand.

Descriptive only — the frozen corpus is NOT touched. Output:
    results/bot_ua_probe.csv     one row per URL x UA
    printed per-brand summary

Usage:  python scripts/bot_ua_probe.py [RUN_ID] [--limit N]
"""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from geo_bench.config import CONFIG
from geo_bench.experiment.run_store import RunStore
from geo_bench.retrieval.cleaner import clean_html
from geo_bench.search.live_retriever import brand_for_url

BOT_UAS = {
    "oai-searchbot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
        "OAI-SearchBot/1.0; +https://openai.com/searchbot"),
    "gptbot": (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
        "GPTBot/1.1; +https://openai.com/gptbot"),
}
DELAY_S = 0.6
TIMEOUT_S = 25


def probe(url: str, ua: str) -> dict:
    try:
        resp = requests.get(url, headers={"User-Agent": ua},
                            timeout=TIMEOUT_S, allow_redirects=True)
        status = resp.status_code
        html = resp.text if status == 200 else ""
    except requests.RequestException as e:
        return {"http_status": 0, "words": 0, "error": type(e).__name__}
    words = 0
    if html:
        body, jsonld = clean_html(html)
        words = len((body + " " + jsonld).split())
    return {"http_status": status, "words": words, "error": ""}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run_id = args[0] if args else None
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    store = RunStore.resolve(run_id, CONFIG)
    metas = store.iter_page_metas()
    seen, urls = set(), []
    for m in metas:
        u = (m.get("url") or "").strip()
        if u and u not in seen:
            seen.add(u)
            urls.append((u, m))
    if limit:
        urls = urls[:limit]

    out = CONFIG.results_dir / "bot_ua_probe.csv"
    rows = []
    if out.exists():
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        for r in rows:
            for k in ("http_status", "words", "browser_words_frozen", "blocked"):
                r[k] = int(r[k] or 0)
        probed = {r["url"] for r in rows}
        urls = [(u, m) for u, m in urls if u not in probed]
        print(f"resume: {len(probed)} URLs already probed, "
              f"{len(urls)} to go")
    print(f"probing {len(urls)} frozen URLs x {len(BOT_UAS)} bot UAs "
          f"(freeze {store.run_id})")
    for i, (url, meta) in enumerate(urls, 1):
        brand = meta.get("brand") or brand_for_url(url, CONFIG)
        base_words = int(meta.get("words") or 0)
        for ua_name, ua in BOT_UAS.items():
            r = probe(url, ua)
            rows.append({
                "url": url, "brand": brand, "ua": ua_name,
                "http_status": r["http_status"], "words": r["words"],
                "browser_words_frozen": base_words,
                "word_ratio_vs_browser": (
                    round(r["words"] / base_words, 3) if base_words else ""),
                "blocked": int(r["http_status"] in (401, 403, 405, 429)
                               or r["http_status"] == 0),
                "error": r["error"],
            })
            time.sleep(DELAY_S)
        if i % 20 == 0 or i == len(urls):
            print(f"  {i}/{len(urls)} URLs done", flush=True)
            with out.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwritten: {out}")

    print(f"\n{'brand':<14}{'ua':<16}{'n':>4}{'blocked':>9}{'median words':>14}"
          f"{'browser med.':>14}")
    print("-" * 71)
    brands = sorted({r["brand"] for r in rows})
    for b in brands:
        for ua_name in BOT_UAS:
            sub = [r for r in rows if r["brand"] == b and r["ua"] == ua_name]
            if not sub:
                continue
            blocked = sum(r["blocked"] for r in sub)
            med = sorted(r["words"] for r in sub)[len(sub) // 2]
            bmed = sorted(r["browser_words_frozen"] for r in sub)[len(sub) // 2]
            print(f"{b:<14}{ua_name:<16}{len(sub):>4}{blocked:>9}"
                  f"{med:>14}{bmed:>14}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
