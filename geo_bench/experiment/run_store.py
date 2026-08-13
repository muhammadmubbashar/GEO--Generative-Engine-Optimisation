"""Per-run artefact layout under runs/<RUN_ID>/."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional  # noqa: F401 — Optional used in write_page

from ..config import CONFIG, Config


def _short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def content_sha256(blob: str | bytes) -> str:
    if isinstance(blob, str):
        blob = blob.encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_run_id(layer: str, arm: str, variant: str, cfg: Config = CONFIG) -> str:
    date = time.strftime("%Y%m%d")
    snap = (
        f"{cfg.search_provider}|{cfg.search_region}|{cfg.search_language}|"
        f"{cfg.search_capture_depth}|{cfg.search_analysis_depth}|"
        f"{cfg.gen_model}|{cfg.embed_model}|{cfg.seeds}|{cfg.runs_per_query}"
    )
    return f"{date}_{layer}_{arm}_{variant}_{_short_hash(snap)}"


def config_snapshot(cfg: Config = CONFIG) -> Dict[str, Any]:
    raw = asdict(cfg) if is_dataclass(cfg) else dict(cfg.__dict__)
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, Path):
            out[k] = str(v)
        elif isinstance(v, tuple):
            out[k] = list(v)
        else:
            out[k] = v
    return out


class RunStore:
    """Freeze + generation artefacts for one experimental execution."""

    def __init__(self, run_id: str, cfg: Config = CONFIG):
        self.cfg = cfg
        self.run_id = run_id
        self.root = Path(cfg.runs_dir) / run_id
        self.retrieval_dir = self.root / "retrieval"
        self.pages_dir = self.root / "pages"
        self.generation_dir = self.root / "generation"
        self.scores_dir = self.root / "scores"
        for d in (self.retrieval_dir, self.pages_dir, self.generation_dir,
                  self.scores_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create(cls, layer: str, arm: str, variant: str,
               cfg: Config = CONFIG, refresh: bool = False) -> "RunStore":
        run_id = make_run_id(layer, arm, variant, cfg)
        store = cls(run_id, cfg)
        meta = {
            "run_id": run_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "layer": layer,
            "arm": arm,
            "variant": variant,
            "refresh": refresh,
            "search_provider": cfg.search_provider,
            "search_region": cfg.search_region,
            "search_language": cfg.search_language,
            "search_capture_depth": cfg.search_capture_depth,
            "search_analysis_depth": cfg.search_analysis_depth,
            "gen_model": cfg.gen_model,
            "embed_model": cfg.embed_model,
            "seeds": list(cfg.seeds),
            "runs_per_query": cfg.runs_per_query,
            "primary_endpoints": ["pawc", "citation_share"],
            "config": config_snapshot(cfg),
        }
        store.write_json(store.root / "metadata.json", meta)
        print(f"  RUN_ID={run_id}")
        if refresh:
            print("  WARNING: --refresh set — new freeze; not comparable to "
                  "prior RUN_ID without re-baselining.")
        return store

    @classmethod
    def open(cls, run_id: str, cfg: Config = CONFIG) -> "RunStore":
        store = cls(run_id, cfg)
        if not (store.root / "metadata.json").exists():
            raise FileNotFoundError(f"no run at {store.root}")
        return store

    def write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    def write_retrieval(self, query_id: str, payload: Dict[str, Any]) -> Path:
        path = self.retrieval_dir / f"{query_id}.json"
        self.write_json(path, payload)
        return path

    def read_retrieval(self, query_id: str) -> Dict[str, Any]:
        path = self.retrieval_dir / f"{query_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing freeze retrieval: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def page_dir(self, url: str) -> Path:
        return self.pages_dir / url_hash(url)

    def write_page(self, url: str, html: str, clean: str, *,
                   http_status: int, method: str,
                   extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        d = self.page_dir(url)
        d.mkdir(parents=True, exist_ok=True)
        raw_path = d / "raw.html"
        clean_path = d / "clean.txt"
        # Hash the exact bytes on disk (encoding can change str vs file).
        raw_bytes = (html or "").encode("utf-8", errors="replace")
        clean_bytes = (clean or "").encode("utf-8", errors="replace")
        raw_path.write_bytes(raw_bytes)
        clean_path.write_bytes(clean_bytes)
        meta = {
            "url": url,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "http_status": http_status,
            "method": method,
            "words": len((clean or "").split()),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "clean_sha256": hashlib.sha256(clean_bytes).hexdigest(),
        }
        if extra:
            meta.update(extra)
        self.write_json(d / "meta.json", meta)
        return meta

    def read_page(self, url: str) -> Optional[Dict[str, Any]]:
        d = self.page_dir(url)
        meta_path = d / "meta.json"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        html = (d / "raw.html").read_bytes().decode("utf-8", errors="replace")
        clean = (d / "clean.txt").read_bytes().decode("utf-8", errors="replace")
        meta["html"] = html
        meta["clean"] = clean
        return meta

    def repair_page_hashes(self) -> int:
        """Recompute sha256 from on-disk raw.html (one-time freeze repair)."""
        n = 0
        for meta_path in self.pages_dir.glob("*/meta.json"):
            raw_path = meta_path.parent / "raw.html"
            clean_path = meta_path.parent / "clean.txt"
            if not raw_path.exists():
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            raw_bytes = raw_path.read_bytes()
            meta["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
            if clean_path.exists():
                meta["clean_sha256"] = hashlib.sha256(
                    clean_path.read_bytes()).hexdigest()
            self.write_json(meta_path, meta)
            n += 1
        return n

    def verify_frozen_pages(self, urls: List[str]) -> None:
        """Raise if any frozen competitor/FC page hash drifted."""
        bad: List[str] = []
        for url in urls:
            d = self.page_dir(url)
            meta_path = d / "meta.json"
            raw_path = d / "raw.html"
            if not meta_path.exists() or not raw_path.exists():
                bad.append(f"MISSING {url}")
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            if digest != meta.get("sha256"):
                bad.append(f"CHANGED {url} (stored={meta.get('sha256')[:12]} "
                           f"now={digest[:12]})")
        if bad:
            raise RuntimeError(
                "Frozen pool hash verification FAILED — competitor/page drift "
                "detected. Do not compare arms against this freeze.\n  "
                + "\n  ".join(bad[:20])
                + (f"\n  ... and {len(bad) - 20} more" if len(bad) > 20 else "")
            )

    def write_generation(self, arm: str, query_id: str, run: int,
                         seed: int, payload: Dict[str, Any]) -> Path:
        arm_dir = self.generation_dir / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        path = arm_dir / f"{query_id}_seed{seed}_run{run:02d}.json"
        self.write_json(path, payload)
        return path

    def answers_jsonl(self, arm: str, variant: str) -> Path:
        return self.root / f"answers_{arm}_{variant}.jsonl"

    def scores_csv(self, arm: str, variant: str) -> Path:
        return self.scores_dir / f"scores_{arm}_{variant}.csv"
