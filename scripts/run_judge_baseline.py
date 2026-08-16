"""Judge baseline 2x5 answers (reindexed then fixed) and reprint summaries."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from geo_bench.cli import main


def _run(argv) -> None:
    print(f"\n>>> geo {' '.join(argv)}", flush=True)
    rc = main(argv)
    if rc:
        raise SystemExit(rc)


if __name__ == "__main__":
    _run(["score", "baseline", "--variant", "reindexed", "--judge"])
    _run(["score", "baseline", "--variant", "fixed", "--judge"])
    _run(["score", "baseline", "--variant", "reindexed", "--stratum", "primary"])
    _run(["score", "baseline", "--variant", "fixed", "--stratum", "primary"])
    print("\nDONE judge baseline", flush=True)
