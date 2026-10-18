"""Selection stage — the engine-realistic gatekeeper.

Real AI search engines (documented for ChatGPT Search) do not read every
result: they see the SERP metadata (title + snippet + URL) and decide which
pages to open. Our fixed/reindexed variants skip that decision, so a page
whose *snippet* is unconvincing never loses the chance to be read.

This stage replays the decision over the FROZEN Brave capture (top 20 rows,
title/snippet exactly as captured — no live traffic, no new bytes). The LLM
picks up to `selection_top_n` results it would open to answer the query.

Measured per (query, seed, run):
    fc_selected        was any Flight Centre result picked?
    fc_selection_rank  1-based rank of FC within the model's ordered picks
    fc_capture_rank    FC's frozen SERP rank (covariate)
    selected_positions the picked capture positions, in the model's order

Optimisation arms can later swap FC's title/snippet (a Type-B intervention:
meta description / title rewriting) and measure the selection delta.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..api import get_client
from ..config import CONFIG, Config
from .run_store import RunStore

SELECTION_PROMPT = """You are the retrieval component of an AI search \
assistant. A user asked:

"{query}"

Below are the web search results (rank, title, URL, snippet). Choose the \
results you would open and read in order to write a grounded, cited answer. \
Pick at most {top_n}. Order your picks from most to least useful.

Return ONLY a JSON array of the result numbers, e.g. [3, 1, 7].

Results:
{results}"""


def _format_results(rows: Sequence[Dict]) -> str:
    lines = []
    for r in rows:
        title = (r.get("title") or "").strip() or "(no title)"
        snippet = re.sub(r"\s+", " ", (r.get("snippet") or "").strip())
        lines.append(f"[{r['position']}] {title}\n"
                     f"    {r.get('url', '')}\n"
                     f"    {snippet}")
    return "\n\n".join(lines)


def _parse_selection(raw: str, valid: Set[int], top_n: int) -> List[int]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M)
    m = re.search(r"\[[\d\s,]*\]", text)
    if not m:
        raise RuntimeError(f"selection did not return a JSON array: {raw[:200]!r}")
    picks = json.loads(m.group(0))
    out: List[int] = []
    for n in picks:
        n = int(n)
        if n in valid and n not in out:
            out.append(n)
    if not out:
        raise RuntimeError(f"selection returned no valid result numbers: {raw[:200]!r}")
    return out[:top_n]


class SelectionRunner:
    def __init__(self, cfg: Config = CONFIG):
        self.cfg = cfg
        model = cfg.selection_model or cfg.gen_model
        from dataclasses import replace
        self._client = get_client(replace(cfg, gen_model=model))

    def _fieldnames(self) -> List[str]:
        return ["query_id", "query", "stratum", "arm", "seed", "run",
                "model", "run_id", "n_capture", "selected_positions",
                "selected_brands", "fc_in_capture", "fc_capture_rank",
                "fc_selected", "fc_selection_rank"]

    def _done(self, path: Path, run_id: str) -> Set[Tuple[str, int, int]]:
        if not path.exists():
            return set()
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        if any(r.get("run_id") and r["run_id"] != run_id for r in rows):
            bak = path.with_suffix(".stale.csv")
            path.rename(bak)
            print(f"  archived stale selection rows -> {bak}")
            return set()
        return {(r["query_id"], int(r["seed"]), int(r["run"])) for r in rows}

    def run(self, arm: str = "baseline", from_run: Optional[str] = None,
            queries_path: Optional[Path] = None, once: bool = False) -> Path:
        if arm != "baseline":
            raise RuntimeError(
                "selection arms need swapped FC titles/snippets; only "
                "baseline is implemented until optimisation pages exist.")
        store = RunStore.resolve(from_run, self.cfg)
        qpath = queries_path or self.cfg.queries_file
        queries = list(csv.DictReader(qpath.open(encoding="utf-8")))
        seeds = self.cfg.seeds[:1] if once else self.cfg.seeds
        runs = 1 if once else self.cfg.runs_per_query
        top_n = self.cfg.selection_top_n

        out = self.cfg.selection_path(arm)
        out.parent.mkdir(parents=True, exist_ok=True)
        done = self._done(out, store.run_id)
        write_header = not out.exists() or out.stat().st_size == 0
        n_wrote = 0
        with out.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=self._fieldnames())
            if write_header:
                w.writeheader()
            for qi, row in enumerate(queries, 1):
                qid = row["id"]
                try:
                    data = store.read_retrieval(qid)
                except FileNotFoundError:
                    print(f"  [{qi}/{len(queries)}] {qid}  SKIP (no freeze capture)")
                    continue
                capture = data.get("results") or []
                if not capture:
                    print(f"  [{qi}/{len(queries)}] {qid}  SKIP (empty capture)")
                    continue
                valid = {int(r["position"]) for r in capture}
                brand_by_pos = {int(r["position"]): (r.get("brand") or "other")
                                for r in capture}
                fc_pos = [p for p, b in brand_by_pos.items()
                          if b == self.cfg.our_brand]
                prompt = SELECTION_PROMPT.format(
                    query=row["query"], top_n=top_n,
                    results=_format_results(capture))
                pending = [(s, r) for s in seeds for r in range(1, runs + 1)
                           if (qid, s, r) not in done]
                if not pending:
                    print(f"  [{qi}/{len(queries)}] {qid}  already done")
                    continue
                for seed, run in pending:
                    raw = self._client.generate(
                        prompt, self.cfg.temperature, self.cfg.top_p)
                    picks = _parse_selection(raw, valid, top_n)
                    fc_rank = next(
                        (i for i, p in enumerate(picks, 1)
                         if brand_by_pos.get(p) == self.cfg.our_brand), "")
                    w.writerow({
                        "query_id": qid, "query": row["query"],
                        "stratum": row.get("stratum", ""),
                        "arm": arm, "seed": seed, "run": run,
                        "model": self._client.name, "run_id": store.run_id,
                        "n_capture": len(capture),
                        "selected_positions": ";".join(map(str, picks)),
                        "selected_brands": ";".join(
                            brand_by_pos.get(p, "other") for p in picks),
                        "fc_in_capture": int(bool(fc_pos)),
                        "fc_capture_rank": min(fc_pos) if fc_pos else "",
                        "fc_selected": int(bool(fc_rank)),
                        "fc_selection_rank": fc_rank,
                    })
                    fh.flush()
                    n_wrote += 1
                print(f"  [{qi}/{len(queries)}] {qid}  "
                      f"fc_capture_rank={min(fc_pos) if fc_pos else '-'}  "
                      f"({len(pending)} calls)")
        print(f"  selection -> {out}  (+{n_wrote} rows)")
        return out


def summarise_selection(path: Path, cfg: Config = CONFIG) -> str:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return "no selection rows"
    n = len(rows)
    in_cap = [r for r in rows if r["fc_in_capture"] == "1"]
    sel = sum(int(r["fc_selected"]) for r in in_cap)
    ranks = [int(r["fc_selection_rank"]) for r in in_cap
             if r["fc_selection_rank"]]
    lines = [
        f"selection calls:            {n}",
        f"FC in frozen capture:       {len(in_cap)}/{n} "
        f"({len(in_cap) / n:.0%})",
        f"P(FC selected | in capture): "
        f"{sel / len(in_cap):.0%}" if in_cap else "P(FC selected): n/a",
    ]
    if ranks:
        lines.append(f"FC selection rank (median): "
                     f"{sorted(ranks)[len(ranks) // 2]}")
    return "\n".join(lines)
