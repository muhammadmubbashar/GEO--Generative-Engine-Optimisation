"""Full post-freeze pipeline on the ACTIVE freeze (Freeze v2, 50 queries).

qc -> route -> lock -> index -> controls -> reindexed 2x5 -> fixed 2x5 ->
selection 2x5 -> counted scores -> judge -> summaries.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geo_bench.cli import main
from geo_bench.config import CONFIG

RID = Path(CONFIG.active_run_file).read_text(encoding="utf-8").strip()


def _run(argv, tolerate=False) -> None:
    print(f"\n>>> geo {' '.join(argv)}", flush=True)
    t0 = time.time()
    rc = main(argv)
    print(f"<<< done in {time.time() - t0:.0f}s (rc={rc})", flush=True)
    if rc and not tolerate:
        raise SystemExit(rc)


if __name__ == "__main__":
    print(f"ACTIVE freeze: {RID}", flush=True)
    # Resume-safe: verify/qc/route/lock already succeeded on this freeze.
    skip_prep = "--from-index" in sys.argv
    if not skip_prep:
        _run(["verify", "--from-run", RID])
        _run(["qc", "--from-run", RID])
        _run(["route", "--from-run", RID])
        _run(["lock", "--from-run", RID])
    _run(["index", "baseline", "--from-run", RID])
    _run(["controls", "--from-run", RID])
    _run(["run", "baseline", "--variant", "reindexed", "--from-run", RID])
    _run(["run", "baseline", "--variant", "fixed", "--from-run", RID])
    _run(["select", "baseline", "--from-run", RID])
    _run(["score", "baseline", "--variant", "reindexed"])
    _run(["score", "baseline", "--variant", "fixed"])
    _run(["score", "baseline", "--variant", "reindexed", "--judge"])
    _run(["score", "baseline", "--variant", "fixed", "--judge"])
    print("\nDONE pipeline v2 (freeze -> judge)", flush=True)
