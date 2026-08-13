"""Command-line entry point.

    geo discover flightcentre.com.au flights
    geo coverage
    geo fetch                       # ONE TIME. Never after the freeze.
    geo verify
    geo clean                       # audit what boilerplate is removed
    geo qc
    geo index baseline
    geo controls
    geo run baseline --variant reindexed
    geo freeze-live                   # capture+fetch freeze into runs/<RUN_ID>/
    geo run baseline --variant live --from-run <RUN_ID> --once
    geo live-pool                     # dry-run: print live pools, no generation
    geo score baseline --variant live
    geo score baseline full_stack --variant reindexed
    geo stats --variant reindexed --metric pawc
    geo monopoly baseline --variant reindexed
    geo all baseline position_control     # index + run fixed/reindexed + score
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

from .config import CONFIG
from .crawler import CoverageGrid, Fetcher
from .crawler.discovery import filter_by_keywords, sitemap_urls
from .crawler.quality import run_quality_checks
from .evaluation import compare_arms, score_arm, summarise
from .evaluation.metrics import filter_rows, monopoly_report
from .evaluation.statistics import render
from .experiment import ExperimentRunner, run_control_tests
from .retrieval import build_index


def _validate_variant(variant: str) -> None:
    if variant not in CONFIG.retrieval_variants:
        raise SystemExit(
            f"unknown --variant {variant!r}; "
            f"allowed={CONFIG.retrieval_variants}")


def _quarantine_offline_results() -> int:
    """Move offline/demo answer+score files out of results/ into results/_demo/."""
    demo = CONFIG.demo_dir
    demo.mkdir(parents=True, exist_ok=True)
    moved = 0

    def _move(path: Path) -> None:
        nonlocal moved
        if not path.exists() or path.parent == demo:
            return
        dest = demo / path.name
        if dest.exists():
            dest.unlink()
        shutil.move(str(path), str(dest))
        moved += 1

    for path in list(CONFIG.results_dir.glob("answers_*.jsonl")):
        if path.parent == demo:
            continue
        is_demo = False
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                is_demo = True
            else:
                line = text.splitlines()[0]
                is_demo = (
                    "offline-deterministic" in line
                    or '"model": "offline' in line
                    or "llama3.2" in line  # ollama smoke models
                )
        except OSError:
            is_demo = True
        if is_demo:
            stem = path.name[len("answers_"):-len(".jsonl")]
            _move(path)
            _move(CONFIG.results_dir / f"scores_{stem}.csv")

    # Orphan score files left behind by partial runs
    for path in list(CONFIG.results_dir.glob("scores_*.csv")):
        if path.parent == demo:
            continue
        stem = path.name[len("scores_"):-len(".csv")]
        answers = CONFIG.results_dir / f"answers_{stem}.jsonl"
        if not answers.exists():
            _move(path)
    return moved


def _print_summary(arms, variant, stratum=None):
    sums = {}
    for a in arms:
        rows = score_arm(a, variant)
        if stratum:
            rows = filter_rows(rows, stratum=stratum)
        sums[a] = summarise(rows)
    label = f"VARIANT: {variant}" + (f"  stratum={stratum}" if stratum else "")
    print(f"\n{label}\n")
    keys = list(sums[arms[0]].keys())
    print(f"{'METRIC':<24}" + "".join(f"{a[:17]:>19}" for a in arms))
    print("-" * (24 + 19 * len(arms)))
    for key in keys:
        print(f"{key:<24}" + "".join(f"{sums[a].get(key, ''):>19}" for a in arms))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="geo", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover"); d.add_argument("domain"); d.add_argument("keywords", nargs="+")
    d.add_argument("--brand", default=None, help="write selected URLs to queries/urls.csv")
    d.add_argument("--origin", default="au", help="keep only routes departing this country ('' = all)")
    d.add_argument("--limit", type=int, default=80, help="how many to print")
    sub.add_parser("coverage")
    f = sub.add_parser("fetch"); f.add_argument("--arm", default="baseline")
    v = sub.add_parser("verify"); v.add_argument("--arm", default="baseline")
    q = sub.add_parser("qc"); q.add_argument("--arm", default="baseline")
    cl = sub.add_parser("clean"); cl.add_argument("--arm", default="baseline")
    i = sub.add_parser("index"); i.add_argument("arm", nargs="?", default="baseline")
    sub.add_parser("controls")
    r = sub.add_parser("run")
    r.add_argument("arm")
    r.add_argument("--variant", default="reindexed",
                   choices=list(CONFIG.retrieval_variants),
                   help="fixed | reindexed | live")
    r.add_argument("--heldout", action="store_true",
                   help="run queries/heldout.csv instead of the main set")
    r.add_argument("--allow-demo", action="store_true",
                   help="permit offline/ollama; writes under results/_demo/")
    r.add_argument("--once", action="store_true",
                   help="1 seed × 1 run only (for first answer inspection)")
    r.add_argument("--refresh", action="store_true",
                   help="live only: bypass search/page/fanout cache (loud)")
    r.add_argument("--from-run", default=None,
                   help="live only: generate from an existing freeze RUN_ID")
    fl = sub.add_parser(
        "freeze-live",
        help="freeze live search+pages for all queries into runs/<RUN_ID>/")
    fl.add_argument("--heldout", action="store_true")
    fl.add_argument("--refresh", action="store_true",
                    help="bypass search/page/fanout cache (loud)")
    fl.add_argument("--allow-demo", action="store_true")
    rf = sub.add_parser(
        "repair-freeze",
        help="re-fetch thin/bot-walled pages in a freeze RUN_ID "
             "(corpus + Common Crawl exact-URL fallback)")
    rf.add_argument("run_id")
    rf.add_argument("--brands", nargs="+",
                    default=["*"],
                    help="brands to repair, or * for every page (default: *)")
    lp = sub.add_parser(
        "live-pool",
        help="dry-run live retrieval: print candidate pools, no generation")
    lp.add_argument("--n", type=int, default=3,
                    help="how many queries from queries.csv (default 3)")
    lp.add_argument("--query", default=None,
                    help="run a single query string instead of CSV rows")
    lp.add_argument("--refresh", action="store_true",
                    help="bypass search/page/fanout cache (loud)")
    lp.add_argument("--urls-only", action="store_true",
                    help="skip page fetch; print search ranks/brands only")
    s = sub.add_parser("score")
    s.add_argument("arms", nargs="+")
    s.add_argument("--variant", default="reindexed",
                   choices=list(CONFIG.retrieval_variants))
    s.add_argument("--stratum", default=None,
                   help="filter summary to stratum (primary|secondary|heldout)")
    t = sub.add_parser("stats")
    t.add_argument("--variant", default=None,
                   help=f"default: primary_variant={CONFIG.primary_variant}")
    t.add_argument("--metric", default=None,
                   help=f"default: primary_metric={CONFIG.primary_metric}")
    t.add_argument("--stratum", default=None,
                   help=f"default: primary_stratum={CONFIG.primary_stratum}")
    t.add_argument("--drop-monopoly", action="store_true",
                   help="exclude queries where only one brand was retrieved")
    m = sub.add_parser("monopoly")
    m.add_argument("arm", nargs="?", default="baseline")
    m.add_argument("--variant", default="reindexed",
                   choices=list(CONFIG.retrieval_variants))
    a = sub.add_parser("all")
    a.add_argument("arms", nargs="+")
    a.add_argument("--allow-demo", action="store_true")
    a.add_argument("--once", action="store_true",
                   help="1 seed × 1 run only (for first answer inspection)")
    sub.add_parser("quarantine-demo",
                   help="move offline answer/score files into results/_demo/")
    sub.add_parser("clear-answers",
                   help="delete answer/score JSONL+CSV (keeps corpus + index files)")

    args = p.parse_args(argv)

    if args.cmd == "discover":
        from .crawler.selector import report, select, write_candidates
        urls = filter_by_keywords(sitemap_urls(args.domain), args.keywords)
        print(f"{len(urls):,} raw URLs for {args.domain}")
        rows = select(urls, CONFIG.queries_file, require_domestic_origin=args.origin)
        print("\n" + report(rows, len(urls)) + "\n")
        for row in rows[:args.limit]:
            print(f"  {row['page_type']:<18}{row['url']}")
        if args.brand:
            path = write_candidates(rows, args.brand, Path("queries/urls.csv"))
            print(f"\nAppended {len(rows)} rows to {path} (brand={args.brand})")
            print("REVIEW BEFORE FETCHING: check every row, then fill any NONE")
            print("cells in the coverage grid with a dated site: search.")

    elif args.cmd == "coverage":
        grid = CoverageGrid()
        g = grid.build(Path("queries/urls.csv"))
        print(f"Written: {grid.write(g)}\n")
        print(grid.summary(g))

    elif args.cmd == "fetch":
        Fetcher().fetch_all(Path("queries/urls.csv"), args.arm)

    elif args.cmd == "verify":
        return 0 if Fetcher().verify(args.arm) else 1

    elif args.cmd == "qc":
        print(run_quality_checks(args.arm).render())

    elif args.cmd == "clean":
        from .retrieval.parser import cleaning_report
        print("Boilerplate removal — words dropped per brand\n")
        for brand in CONFIG.brands:
            paths = sorted((CONFIG.corpus_dir / args.arm / brand).glob("*.html"))
            if paths:
                print(f"{brand:<16}{cleaning_report(paths)}")
        print("\nNavigation, footers, cookie banners and repeated chrome are")
        print("removed. JSON-LD is always preserved — schema is under test.")

    elif args.cmd == "index":
        print(build_index(args.arm).volume_table())

    elif args.cmd == "controls":
        results = run_control_tests()
        print("\nCONTROL TESTS\n" + "=" * 58)
        for result in results:
            print(result)
        ok = all(result.passed for result in results)
        print("=" * 58)
        print("ALL CONTROL TESTS PASSED — the environment is controlled." if ok
              else "SOME TESTS FAILED — fix before running any experiment.")
        return 0 if ok else 1

    elif args.cmd == "run":
        _validate_variant(args.variant)
        qpath = CONFIG.heldout_file if args.heldout else None
        try:
            print(ExperimentRunner().run(
                args.arm, args.variant, queries_path=qpath,
                allow_demo=args.allow_demo, once=args.once,
                refresh=args.refresh, from_run=args.from_run))
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "freeze-live":
        qpath = CONFIG.heldout_file if args.heldout else None
        try:
            store = ExperimentRunner().freeze_live(
                arm="baseline", queries_path=qpath,
                refresh=args.refresh, allow_demo=args.allow_demo)
            print(store.root)
            print("\nNext: generate against this freeze (no re-fetch):")
            print(f"  geo run baseline --variant live --from-run {store.run_id} --once")
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "repair-freeze":
        from .experiment.run_store import RunStore
        from .search import LiveRetriever
        try:
            store = RunStore.open(args.run_id)
            stats = LiveRetriever(CONFIG).repair_store_pages(
                store, brands=args.brands)
            print(f"checked={stats['checked']} repaired={stats['repaired']} "
                  f"still_thin={stats['still_thin']}")
            print("Re-generate with: "
                  f"geo run baseline --variant live --from-run {args.run_id} --once")
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "live-pool":
        from .search import LiveRetriever
        try:
            retriever = LiveRetriever(CONFIG, refresh=args.refresh)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        if args.query:
            queries = [{"id": "adhoc", "query": args.query}]
        else:
            rows = list(csv.DictReader(
                CONFIG.queries_file.open(encoding="utf-8")))
            queries = rows[: max(1, args.n)]
        mode = "urls-only" if args.urls_only else "search+fetch"
        print(f"Live-pool dry-run ({len(queries)} quer"
              f"{'y' if len(queries) == 1 else 'ies'}, {mode}) — no generation")
        summary = []
        try:
            for row in queries:
                pool = retriever.build_pool(
                    row["query"], urls_only=args.urls_only,
                    query_id=row.get("id", "adhoc"))
                pool.print_pool(row["query"])
                summary.append({
                    "id": row.get("id", ""),
                    "fc_present": pool.fc_present,
                    "fc_in_capture": pool.fc_in_capture,
                    "fc_search_rank": pool.fc_search_rank,
                    "n_domains": pool.n_distinct_domains,
                    "n_other": sum(1 for b in pool.retrieved_brands
                                   if b == "other"),
                    "n_fc": sum(1 for b in pool.retrieved_brands
                                if b == "flightcentre"),
                })
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        if summary:
            print("\n=== SUMMARY ===")
            print(f"{'id':<6}{'anl':>4}{'cap':>4}{'rank':>6}{'#fc':>5}"
                  f"{'dom':>5}{'other':>7}")
            for s in summary:
                print(f"{s['id']:<6}"
                      f"{'Y' if s['fc_present'] else 'N':>4}"
                      f"{'Y' if s['fc_in_capture'] else 'N':>4}"
                      f"{str(s['fc_search_rank'] or '-'):>6}"
                      f"{s['n_fc']:>5}{s['n_domains']:>5}{s['n_other']:>7}")
            n_fc = sum(1 for s in summary if s["fc_present"])
            n_cap = sum(1 for s in summary if s["fc_in_capture"])
            ranks = [s["fc_search_rank"] for s in summary
                     if s["fc_search_rank"] is not None]
            print(f"\nFC in analysis pool (k=10): {n_fc}/{len(summary)}")
            print(f"FC in capture (k=20): {n_cap}/{len(summary)}")
            if ranks:
                print(f"FC best capture rank: min={min(ranks)} median="
                      f"{sorted(ranks)[len(ranks)//2]} max={max(ranks)}")
        print("\nInspect pools above. When satisfied:")
        print("  geo freeze-live")
        print("  geo run baseline --variant live --from-run <RUN_ID> --once")

    elif args.cmd == "score":
        _validate_variant(args.variant)
        _print_summary(args.arms, args.variant, stratum=args.stratum)

    elif args.cmd == "stats":
        variant = args.variant or CONFIG.primary_variant
        metric = args.metric or CONFIG.primary_metric
        stratum = args.stratum or CONFIG.primary_stratum
        print(render(
            compare_arms(variant, metric, stratum=stratum,
                         drop_monopoly=args.drop_monopoly),
            metric, variant))

    elif args.cmd == "monopoly":
        _validate_variant(args.variant)
        rows = score_arm(args.arm, args.variant)
        print(monopoly_report(rows))

    elif args.cmd == "quarantine-demo":
        n = _quarantine_offline_results()
        print(f"Moved {n} offline demo file(s) into {CONFIG.demo_dir}")

    elif args.cmd == "clear-answers":
        n = 0
        patterns = ("answers_*.jsonl", "scores_*.csv")
        for folder in (CONFIG.results_dir, CONFIG.demo_dir):
            if not folder.exists():
                continue
            for pat in patterns:
                for path in folder.glob(pat):
                    path.unlink()
                    print(f"  deleted {path}")
                    n += 1
        # Old embedding index must be rebuilt for the new provider
        for path in (CONFIG.index_path("baseline"),
                     CONFIG.vectors_path("baseline")):
            if path.exists():
                path.unlink()
                print(f"  deleted {path} (rebuild with: geo index baseline)")
                n += 1
        print(f"Cleared {n} file(s). Corpus HTML + manifest kept.")

    elif args.cmd == "all":
        for arm in args.arms:
            print(f"\n=== INDEX {arm} ===")
            print(build_index(arm).volume_table())
        runner = ExperimentRunner()
        try:
            # live needs Brave + costs search/fetch; run explicitly via
            # --variant live after geo live-pool review.
            local_variants = [v for v in CONFIG.retrieval_variants
                              if v != "live"]
            for variant in local_variants:
                for arm in args.arms:
                    print(f"\n=== RUN {arm} [{variant}] ===")
                    runner.run(arm, variant, allow_demo=args.allow_demo,
                               once=args.once)
                _print_summary(args.arms, variant, stratum=CONFIG.primary_stratum)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
