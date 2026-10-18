"""Per-run artefact layout under runs/<RUN_ID>/."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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
            "primary_endpoints": list(cfg.primary_endpoints),
            "secondary_endpoints": list(cfg.secondary_endpoints),
            "config": config_snapshot(cfg),
        }
        store.write_json(store.root / "metadata.json", meta)
        print(f"  RUN_ID={run_id}")
        if refresh:
            print("  WARNING: --refresh set - new freeze; not comparable to "
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

    def iter_page_metas(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for meta_path in sorted(self.pages_dir.glob("*/meta.json")):
            rows.append(json.loads(meta_path.read_text(encoding="utf-8")))
        return rows

    def manifest_path(self) -> Path:
        return self.root / "manifest.csv"

    def write_manifest(self) -> Path:
        """SHA-256 freeze ledger: every page, word count, fetch method, QC flags."""
        from ..crawler.quality import canonical_fetch_method, is_usable, needs_review

        rows: List[Dict[str, Any]] = []
        for meta in self.iter_page_metas():
            words = int(meta.get("words") or 0)
            method = canonical_fetch_method(
                str(meta.get("method") or ""),
                kind=str(meta.get("live_kind") or ""),
                words=words, cfg=self.cfg)
            rows.append({
                "url": meta.get("url") or "",
                "brand": meta.get("brand") or "",
                "words": words,
                "method": method,
                "needs_review": int(needs_review(words, self.cfg)),
                "usable": int(is_usable(words, method, self.cfg)),
                "http_status": meta.get("http_status", ""),
                "fetched_at": meta.get("fetched_at") or "",
                "sha256": meta.get("sha256") or "",
                "clean_sha256": meta.get("clean_sha256") or "",
            })
        path = self.manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = ["url", "brand", "words", "method", "needs_review", "usable",
                  "http_status", "fetched_at", "sha256", "clean_sha256"]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        return path

    def verify_frozen_pages(self, urls: Optional[List[str]] = None) -> None:
        """Re-hash every freeze page. Any mismatch raises — not a warning."""
        bad: List[str] = []
        manifest = self.manifest_path()
        if urls:
            targets = list(urls)
        else:
            targets = [m.get("url") or "" for m in self.iter_page_metas()]
            if manifest.exists():
                for row in csv.DictReader(manifest.open(encoding="utf-8")):
                    u = (row.get("url") or "").strip()
                    if u and u not in targets:
                        targets.append(u)

        seen: set = set()
        for url in targets:
            if not url or url in seen:
                continue
            seen.add(url)
            d = self.page_dir(url)
            meta_path = d / "meta.json"
            raw_path = d / "raw.html"
            if not meta_path.exists() or not raw_path.exists():
                bad.append(f"MISSING {url}")
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            stored = meta.get("sha256") or ""
            if digest != stored:
                bad.append(
                    f"CHANGED {url} (stored={stored[:12]} now={digest[:12]})")
            clean_path = d / "clean.txt"
            if not clean_path.exists() or not meta.get("clean_sha256"):
                bad.append(f"CLEAN-MISSING-OR-UNHASHED {url}")
            else:
                cdig = hashlib.sha256(clean_path.read_bytes()).hexdigest()
                if cdig != meta.get("clean_sha256"):
                    bad.append(f"CLEAN-CHANGED {url}")

        if manifest.exists():
            by_url = {r["url"]: r for r in csv.DictReader(
                manifest.open(encoding="utf-8")) if r.get("url")}
            for url in seen:
                row = by_url.get(url)
                if row is None:
                    bad.append(f"UNMANIFESTED {url}")
                    continue
                meta_path = self.page_dir(url) / "meta.json"
                if not meta_path.exists():
                    continue
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if row.get("sha256") and meta.get("sha256") != row["sha256"]:
                    bad.append(f"MANIFEST-MISMATCH {url}")
                if meta.get("clean_sha256") != row.get("clean_sha256"):
                    bad.append(f"CLEAN-MANIFEST-MISMATCH {url}")

        if bad:
            raise RuntimeError(
                "HASH VERIFICATION FAILED - freeze pages have changed. "
                "Stop. Do not run or score this experiment.\n  "
                + "\n  ".join(bad[:30])
                + (f"\n  ... and {len(bad) - 30} more" if len(bad) > 30 else "")
            )

    def set_active(self) -> Path:
        path = Path(self.cfg.active_run_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.run_id + "\n", encoding="utf-8")
        return path

    @classmethod
    def resolve(cls, run_id: Optional[str] = None,
                cfg: Config = CONFIG) -> "RunStore":
        rid = (run_id or "").strip()
        if not rid:
            active = Path(cfg.active_run_file)
            if active.exists():
                rid = active.read_text(encoding="utf-8").strip()
        if not rid:
            raise RuntimeError(
                "No freeze RUN_ID. Pass --from-run <RUN_ID> or run "
                "`geo freeze-live` / `geo lock --from-run` first "
                f"(expected {cfg.active_run_file}).")
        return cls.open(rid, cfg)

    def write_generation(self, arm: str, query_id: str, run: int,
                         seed: int, payload: Dict[str, Any]) -> Path:
        arm_dir = self.generation_dir / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        variant = payload.get("variant", "legacy")
        path = arm_dir / f"{variant}_{query_id}_seed{seed}_run{run:02d}.json"
        self.write_json(path, payload)
        return path

    def answers_jsonl(self, arm: str, variant: str) -> Path:
        return self.root / f"answers_{arm}_{variant}.jsonl"

    def scores_csv(self, arm: str, variant: str) -> Path:
        return self.scores_dir / f"scores_{arm}_{variant}.csv"
