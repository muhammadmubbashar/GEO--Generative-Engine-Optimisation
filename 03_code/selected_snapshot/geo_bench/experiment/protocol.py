"""Protocol lock — freeze experimental parameters to disk before runs."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import CONFIG, Config
from .run_store import RunStore, config_snapshot


def _git_commit() -> str:
    import subprocess
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True,
            text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except OSError:
        return ""


def lock_payload(cfg: Config = CONFIG, run_id: str = "") -> Dict[str, Any]:
    from ..generation.prompts import prompt_sha256
    return {
        "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "git_commit": _git_commit(),
        "prompt_sha256": prompt_sha256(),
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "shuffle_passages": cfg.shuffle_passages,
        "fixed_source_unit": cfg.fixed_source_unit,
        "page_prompt_chars": cfg.page_prompt_chars,
        "passage_prompt_chars": cfg.passage_prompt_chars,
        "chunk_words": cfg.chunk_words,
        "chunk_overlap": cfg.chunk_overlap,
        "chunk_max_chars": cfg.chunk_max_chars,
        "rrf_k": cfg.rrf_k,
        "bm25_k1": cfg.bm25_k1,
        "bm25_b": cfg.bm25_b,
        "cap_scope": cfg.cap_scope,
        "gen_model": cfg.gen_model,
        "embed_model": cfg.embed_model,
        "judge_model": cfg.judge_model,
        "judge_temperature": cfg.judge_temperature,
        "rubric_version": cfg.rubric_version,
        "seeds": list(cfg.seeds),
        "runs_per_query": cfg.runs_per_query,
        "arms": list(cfg.arms),
        "retrieval_variants": list(cfg.retrieval_variants),
        "primary_endpoints": list(cfg.primary_endpoints),
        "secondary_endpoints": list(cfg.secondary_endpoints),
        "statistical_tests": list(cfg.statistical_tests),
        "thin_page_word_threshold": cfg.thin_page_word_threshold,
        "min_usable_docs_per_query": cfg.min_usable_docs_per_query,
        "search_provider": cfg.search_provider,
        "search_capture_depth": cfg.search_capture_depth,
        "search_analysis_depth": cfg.search_analysis_depth,
        "top_k": cfg.top_k,
        "cap_per_brand": cfg.cap_per_brand,
        "config": config_snapshot(cfg),
    }


def lock_hash(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_lock(store: RunStore, cfg: Config = CONFIG) -> Path:
    payload = lock_payload(cfg, store.run_id)
    path = store.root / "protocol_lock.json"
    store.write_json(path, payload)
    store.set_active()
    print(f"  protocol lock -> {path}")
    print(f"  sha256={lock_hash(payload)[:16]}...")
    print(f"  locked_at={payload['locked_at']}")
    return path


def read_lock(store: RunStore) -> Optional[Dict[str, Any]]:
    path = store.root / "protocol_lock.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def diff_against_lock(lock: Dict[str, Any],
                      cfg: Config = CONFIG) -> List[str]:
    """Return human-readable differences between current config and the lock."""
    diffs: List[str] = []
    from ..generation.prompts import prompt_sha256
    checks = [
        ("gen_model", cfg.gen_model),
        ("embed_model", cfg.embed_model),
        ("judge_model", cfg.judge_model),
        ("judge_temperature", cfg.judge_temperature),
        ("rubric_version", cfg.rubric_version),
        ("runs_per_query", cfg.runs_per_query),
        ("temperature", cfg.temperature),
        ("top_p", cfg.top_p),
        ("shuffle_passages", cfg.shuffle_passages),
        ("fixed_source_unit", cfg.fixed_source_unit),
        ("page_prompt_chars", cfg.page_prompt_chars),
        ("passage_prompt_chars", cfg.passage_prompt_chars),
        ("chunk_words", cfg.chunk_words),
        ("chunk_overlap", cfg.chunk_overlap),
        ("chunk_max_chars", cfg.chunk_max_chars),
        ("rrf_k", cfg.rrf_k),
        ("bm25_k1", cfg.bm25_k1),
        ("bm25_b", cfg.bm25_b),
        ("cap_scope", cfg.cap_scope),
        ("prompt_sha256", prompt_sha256()),
        ("thin_page_word_threshold", cfg.thin_page_word_threshold),
        ("min_usable_docs_per_query", cfg.min_usable_docs_per_query),
        ("search_provider", cfg.search_provider),
        ("search_capture_depth", cfg.search_capture_depth),
        ("search_analysis_depth", cfg.search_analysis_depth),
        ("top_k", cfg.top_k),
        ("cap_per_brand", cfg.cap_per_brand),
    ]
    for key, current in checks:
        locked = lock.get(key)
        if locked is not None and locked != current:
            diffs.append(f"{key}: lock={locked!r} now={current!r}")
    for key in ("seeds", "arms", "retrieval_variants",
                "primary_endpoints", "secondary_endpoints",
                "statistical_tests"):
        locked = lock.get(key)
        current = list(getattr(cfg, key))
        if locked is not None and list(locked) != current:
            diffs.append(f"{key}: lock={locked!r} now={current!r}")
    return diffs


def check_lock(store: RunStore, cfg: Config = CONFIG,
               metadata: Optional[Dict[str, Any]] = None,
               strict: bool = True
               ) -> Tuple[Optional[str], List[str]]:
    """Compare config to lock. Hard-fail on drift unless strict=False.

    A run whose parameters differ from the lock is a different experiment;
    silently continuing would let incomparable rows mix in one CSV. Pass
    strict=False (CLI --accept-drift) only for explicitly exploratory runs;
    the drift is still recorded in metadata.

    Returns (lock_sha256 or None, list of diff strings).
    """
    lock = read_lock(store)
    if lock is None:
        msg = (
            f"WARNING: no protocol_lock.json at {store.root}. "
            f"Run `geo lock --from-run {store.run_id}` before reportable runs."
        )
        print(msg)
        if metadata is not None:
            metadata["protocol_lock_sha256"] = ""
            metadata["protocol_lock_missing"] = True
            metadata["protocol_lock_diffs"] = [msg]
        return None, [msg]

    sha = lock_hash(lock)
    diffs = diff_against_lock(lock, cfg)
    if diffs:
        print("=" * 64)
        print("CURRENT CONFIG DIFFERS FROM PROTOCOL LOCK")
        print(f"  lock file: {store.root / 'protocol_lock.json'}")
        print(f"  lock sha256: {sha}")
        for d in diffs:
            print(f"  DIFF  {d}")
        print("=" * 64)
        if strict:
            raise RuntimeError(
                "Config drift against protocol lock (see DIFF lines above). "
                "Either restore the locked parameters, re-lock after a "
                "decisions_log.md entry (geo lock --from-run <RUN_ID>), or "
                "pass --accept-drift for an explicitly exploratory run."
            )
        print("  --accept-drift: run continues, but results must not be")
        print("  mixed with runs that used the locked parameters.")
    if metadata is not None:
        metadata["protocol_lock_sha256"] = sha
        metadata["protocol_lock_missing"] = False
        metadata["protocol_lock_diffs"] = diffs
        if diffs:
            metadata["protocol_lock_drift_accepted"] = True
    return sha, diffs
