"""Command-line entry point.

    geo freeze-live
    geo verify --from-run <RUN_ID>
    geo qc --from-run <RUN_ID>
    geo lock --from-run <RUN_ID>
    geo route --from-run <RUN_ID>
    geo index baseline --from-run <RUN_ID>
    geo controls --from-run <RUN_ID>
    geo run baseline --variant reindexed --from-run <RUN_ID>
    geo run baseline --variant fixed --from-run <RUN_ID>
    geo score baseline --variant reindexed
    geo score baseline --variant reindexed --judge
    geo stats --variant reindexed
    geo calibrate baseline --variant reindexed
    geo kappa results/calibration_sample.csv
    geo extract-facts
    geo optimise <arm>
    geo verify-arm <arm>
    geo diff <arm> --url <url>
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

from .config import CONFIG
from .crawler.quality import run_freeze_qc
from .evaluation import (
    compare_arms, score_arm, summarise, judge_arm,
    export_calibration_sample, kappa_report,
)
from .evaluation.metrics import filter_rows, monopoly_report
from .evaluation.statistics import render, render_families
from .experiment import (
    ExperimentRunner, run_control_tests, RunStore,
    write_lock, write_routing_csv, render_routing,
    SelectionRunner, summarise_selection,
)
from .retrieval import build_index


def _validate_variant(variant: str) -> str:
    if variant == "live":
        print("WARNING: --variant live is retired; using fixed.", file=sys.stderr)
        return "fixed"
    if variant not in CONFIG.retrieval_variants:
        raise SystemExit(
            f"unknown --variant {variant!r}; "
            f"allowed={CONFIG.retrieval_variants}")
    return variant


def _quarantine_offline_results() -> int:
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
                    or "llama3.2" in line
                )
        except OSError:
            is_demo = True
        if is_demo:
            stem = path.name[len("answers_"):-len(".jsonl")]
            _move(path)
            _move(CONFIG.results_dir / f"scores_{stem}.csv")
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

    fl = sub.add_parser("freeze-live", help="Brave capture + fetch/QC freeze")
    fl.add_argument("--heldout", action="store_true")
    fl.add_argument("--final", action="store_true",
                    help="required to freeze held-out queries (end of study)")
    fl.add_argument("--queries", default=None,
                    help="alternate queries CSV (e.g. an expansion batch)")
    fl.add_argument("--refresh", action="store_true")
    fl.add_argument("--allow-demo", action="store_true")

    v = sub.add_parser("verify", help="re-hash freeze pages; FAIL on mismatch")
    v.add_argument("--from-run", default=None)

    q = sub.add_parser("qc", help="usable-content QC + per-query usable counts")
    q.add_argument("--from-run", default=None)

    lk = sub.add_parser("lock", help="write protocol_lock.json for a freeze")
    lk.add_argument("--from-run", default=None)

    rt = sub.add_parser("route", help="FC position routing -> results/routing.csv")
    rt.add_argument("--from-run", default=None)

    i = sub.add_parser("index", help="hybrid index over the frozen live pool")
    i.add_argument("arm", nargs="?", default="baseline")
    i.add_argument("--from-run", default=None)

    c = sub.add_parser("controls")
    c.add_argument("--from-run", default=None)

    r = sub.add_parser("run")
    r.add_argument("arm")
    r.add_argument("--variant", default="reindexed",
                   help="fixed | reindexed")
    r.add_argument("--heldout", action="store_true")
    r.add_argument("--final", action="store_true",
                   help="required to run held-out queries")
    r.add_argument("--allow-demo", action="store_true")
    r.add_argument("--once", action="store_true")
    r.add_argument("--refresh", action="store_true")
    r.add_argument("--from-run", default=None)
    r.add_argument("--accept-drift", action="store_true",
                   help="run despite config drift from the protocol lock "
                        "(exploratory only; drift is recorded)")

    sel = sub.add_parser(
        "select", help="LLM gatekeeper over frozen capture-20 (title+snippet)")
    sel.add_argument("arm", nargs="?", default="baseline")
    sel.add_argument("--from-run", default=None)
    sel.add_argument("--once", action="store_true")

    rf = sub.add_parser("repair-freeze")
    rf.add_argument("run_id")
    rf.add_argument("--brands", nargs="+", default=["*"])

    lp = sub.add_parser("live-pool")
    lp.add_argument("--n", type=int, default=3)
    lp.add_argument("--query", default=None)
    lp.add_argument("--refresh", action="store_true")
    lp.add_argument("--urls-only", action="store_true")

    s = sub.add_parser("score")
    s.add_argument("arms", nargs="+")
    s.add_argument("--variant", default="reindexed")
    s.add_argument("--stratum", default=None)
    s.add_argument("--judge", action="store_true",
                   help="run judged metrics (mask + one call per answer)")

    t = sub.add_parser("stats")
    t.add_argument("--variant", default=None)
    t.add_argument("--metric", default=None,
                   help="single metric (default: both endpoint families)")
    t.add_argument("--stratum", default=None)
    t.add_argument("--drop-monopoly", action="store_true")

    cal = sub.add_parser("calibrate", help="export 60-answer human calibration CSV")
    cal.add_argument("arm", nargs="?", default="baseline")
    cal.add_argument("--variant", default="reindexed")

    kp = sub.add_parser("kappa", help="Cohen's kappa from a filled calibration CSV")
    kp.add_argument("csv", nargs="?", default="results/calibration_sample.csv")

    m = sub.add_parser("monopoly")
    m.add_argument("arm", nargs="?", default="baseline")
    m.add_argument("--variant", default="reindexed")

    a = sub.add_parser("all")
    a.add_argument("arms", nargs="+")
    a.add_argument("--from-run", default=None)
    a.add_argument("--allow-demo", action="store_true")
    a.add_argument("--once", action="store_true")

    sub.add_parser("quarantine-demo")
    sub.add_parser("clear-answers")

    xf = sub.add_parser(
        "extract-facts",
        help="candidate facts + fact_coverage.csv from freeze FC pages")
    xf.add_argument("--from-run", default=None)

    opt = sub.add_parser("optimise", help="write optimised FC pages for one arm")
    opt.add_argument("arm")
    opt.add_argument("--from-run", default=None)

    va = sub.add_parser("verify-arm", help="print added claims; require human sign-off")
    va.add_argument("arm")
    va.add_argument("--from-run", default=None)

    df = sub.add_parser("diff", help="before/after HTML for one URL")
    df.add_argument("arm")
    df.add_argument("--url", required=True)
    df.add_argument("--from-run", default=None)

    args = p.parse_args(argv)

    if args.cmd == "freeze-live":
        qpath = (CONFIG.heldout_file if args.heldout
                 else (Path(args.queries) if args.queries else None))
        try:
            store = ExperimentRunner().freeze_live(
                arm="baseline", queries_path=qpath,
                refresh=args.refresh, allow_demo=args.allow_demo,
                heldout=args.heldout, final=args.final)
            print(store.root)
            print("\nNext:")
            print(f"  geo lock --from-run {store.run_id}")
            print(f"  geo qc --from-run {store.run_id}")
            print(f"  geo index baseline --from-run {store.run_id}")
            print(f"  geo run baseline --variant reindexed --from-run {store.run_id}")
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "verify":
        try:
            store = RunStore.resolve(args.from_run)
            store.verify_frozen_pages()
            print(f"HASH VERIFICATION PASSED  run={store.run_id}  "
                  f"pages={len(store.iter_page_metas())}")
            return 0
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "qc":
        try:
            store = RunStore.resolve(args.from_run)
            store.verify_frozen_pages()
            report = run_freeze_qc(store)
            print(report.render())
            print(f"\nWritten: {CONFIG.results_dir / 'qc_pages.csv'}")
            print(f"         {CONFIG.results_dir / 'qc_queries.csv'}")
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "lock":
        try:
            store = RunStore.resolve(args.from_run)
            store.verify_frozen_pages()
            if not store.manifest_path().exists():
                store.write_manifest()
            write_lock(store)
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "route":
        try:
            store = RunStore.resolve(args.from_run)
            store.verify_frozen_pages()
            path = write_routing_csv(store)
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
            print(render_routing(rows))
            print(f"\nWritten: {path}")
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "index":
        try:
            store = RunStore.resolve(args.from_run)
            print(build_index(args.arm, store=store).volume_table())
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "controls":
        try:
            results = run_control_tests(run_id=args.from_run)
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print("\nCONTROL TESTS\n" + "=" * 58)
        for result in results:
            print(result)
        ok = all(result.passed for result in results)
        print("=" * 58)
        print("ALL CONTROL TESTS PASSED - the environment is controlled." if ok
              else "SOME TESTS FAILED - fix before running any experiment.")
        return 0 if ok else 1

    elif args.cmd == "run":
        variant = _validate_variant(args.variant)
        try:
            print(ExperimentRunner().run(
                args.arm, variant, allow_demo=args.allow_demo, once=args.once,
                refresh=args.refresh, from_run=args.from_run,
                heldout=args.heldout, final=args.final,
                accept_drift=args.accept_drift))
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "select":
        try:
            path = SelectionRunner().run(
                args.arm, from_run=args.from_run, once=args.once)
            print()
            print(summarise_selection(path))
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "repair-freeze":
        from .search import LiveRetriever
        try:
            store = RunStore.open(args.run_id)
            stats = LiveRetriever(CONFIG).repair_store_pages(
                store, brands=args.brands)
            store.write_manifest()
            print(f"checked={stats['checked']} repaired={stats['repaired']} "
                  f"still_thin={stats['still_thin']}")
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
            rows = list(csv.DictReader(CONFIG.queries_file.open(encoding="utf-8")))
            queries = rows[: max(1, args.n)]
        print(f"Live-pool dry-run ({len(queries)} quer"
              f"{'y' if len(queries) == 1 else 'ies'}) - no generation")
        try:
            for row in queries:
                pool = retriever.build_pool(
                    row["query"], urls_only=args.urls_only,
                    query_id=row.get("id", "adhoc"))
                pool.print_pool(row["query"])
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "score":
        variant = _validate_variant(args.variant)
        if args.judge:
            for arm in args.arms:
                print(f"=== JUDGE {arm} [{variant}] ===")
                judge_arm(arm, variant)
        _print_summary(args.arms, variant, stratum=args.stratum)

    elif args.cmd == "stats":
        variant = args.variant or CONFIG.primary_variant
        variant = _validate_variant(variant)
        if args.metric:
            print(render(
                compare_arms(variant, args.metric, stratum=args.stratum,
                             drop_monopoly=args.drop_monopoly),
                args.metric, variant))
        else:
            print(render_families(
                variant, stratum=args.stratum,
                drop_monopoly=args.drop_monopoly))

    elif args.cmd == "calibrate":
        variant = _validate_variant(args.variant)
        rows = score_arm(args.arm, variant)
        path = export_calibration_sample(rows)
        print(f"Wrote {path}  n={min(CONFIG.calibration_sample_size, len(rows))} "
              f"(or fewer if not enough scored answers)")
        print("Two graders score independently using SCORING_RUBRICS.md, "
              "then: geo kappa", path)

    elif args.cmd == "kappa":
        path = Path(args.csv)
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 1
        print(kappa_report(path))

    elif args.cmd == "monopoly":
        variant = _validate_variant(args.variant)
        rows = score_arm(args.arm, variant)
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
        for path in (CONFIG.index_path("baseline"),
                     CONFIG.vectors_path("baseline")):
            if path.exists():
                path.unlink()
                print(f"  deleted {path}")
                n += 1
        print(f"Cleared {n} file(s). Freeze under runs/ kept.")

    elif args.cmd == "all":
        try:
            store = RunStore.resolve(args.from_run)
            store.verify_frozen_pages()
            print(f"\n=== INDEX (freeze {store.run_id}) ===")
            print(build_index("baseline", store=store).volume_table())
            runner = ExperimentRunner()
            for variant in CONFIG.retrieval_variants:
                for arm in args.arms:
                    print(f"\n=== RUN {arm} [{variant}] ===")
                    runner.run(arm, variant, allow_demo=args.allow_demo,
                               once=args.once, from_run=store.run_id)
                _print_summary(args.arms, variant, stratum=CONFIG.primary_stratum)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "extract-facts":
        from .optimisation.builder import extract_facts, render_coverage_summary
        try:
            summary = extract_facts(from_run=args.from_run)
            print(render_coverage_summary(summary))
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "optimise":
        from .optimisation.builder import optimise_arm
        try:
            path = optimise_arm(args.arm, from_run=args.from_run)
            print(path)
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "verify-arm":
        from .optimisation.builder import load_arm_page, collect_targets
        from .optimisation.facts import FactTable
        import json as _json
        try:
            store = RunStore.resolve(args.from_run)
            facts = FactTable.load()
            tpath = CONFIG.optimisation_targets_path()
            if not tpath.exists():
                raise RuntimeError("run geo extract-facts first")
            rows = list(csv.DictReader(tpath.open(encoding="utf-8")))
            n_claims = 0
            n_unverified = 0
            print(f"VERIFY {args.arm}")
            for row in rows:
                opt = load_arm_page(store, args.arm, row["url"])
                if opt is None:
                    print(f"  MISSING {row['url']}")
                    n_unverified += 1
                    continue
                for c in opt.claims:
                    fact = facts.by_id(c.fact_id) if c.fact_id else None
                    status = fact.status if fact else "NO_FACT"
                    if status != "verified":
                        n_unverified += 1
                    n_claims += 1
                    src = fact.source_url if fact else c.source_url
                    print(f"  [{c.fact_id or '-'}|{status}] {c.span[:120]!r}")
                    print(f"      {row['url']}")
                    print(f"      source={src}")
            sign = CONFIG.arm_results_dir(args.arm) / "verification_signoff.json"
            if not sign.exists():
                print(f"\nNO SIGNOFF at {sign}")
                print("A named team member must write name + date there. "
                      "This command will not invent one.")
                return 1
            payload = _json.loads(sign.read_text(encoding="utf-8"))
            if not payload.get("signed_by") or not payload.get("signed_on"):
                print("signoff missing signed_by / signed_on")
                return 1
            if n_unverified:
                print(f"\nUNVERIFIED claims: {n_unverified}")
                return 1
            print(f"\nOK  claims={n_claims}  signed_by={payload['signed_by']}")
            return 0
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    elif args.cmd == "diff":
        from .optimisation.builder import load_arm_page, load_frozen_page
        from .optimisation.diff_report import render_diff
        from .optimisation.facts import FactTable
        try:
            store = RunStore.resolve(args.from_run)
            tpath = CONFIG.optimisation_targets_path()
            targets = {r["url"]: r for r in csv.DictReader(
                tpath.open(encoding="utf-8"))} if tpath.exists() else {}
            row = targets.get(args.url)
            if row is None:
                raise RuntimeError(f"url not in optimisation_targets.csv: {args.url}")
            page = load_frozen_page(store, row)
            opt = load_arm_page(store, args.arm, args.url)
            if opt is None:
                raise RuntimeError(f"no optimised page for {args.arm} {args.url}")
            print(render_diff(page, opt, FactTable.load()))
        except (RuntimeError, FileNotFoundError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
