"""Download pages the way AI crawlers read them, then freeze the result.

NO JAVASCRIPT IS EVER EXECUTED. Vercel/MERJ's measurement of AI crawler
traffic found GPTBot, ClaudeBot and PerplexityBot do not run JavaScript, so a
plain HTTP GET reproduces what they see. Using a headless browser here would
destroy the central construct of the study.

Every page is recorded with a timestamp, HTTP status, method and SHA-256. The
checksum is what makes "frozen" verifiable rather than merely asserted.
"""
import csv
import datetime as _dt
import hashlib
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import requests

from ..config import CONFIG, Config

USER_AGENT = ("Team62-QUT-Research-Fetcher "
              "(student capstone; contact: teamlead@example.com)")
DELAY_SECONDS = 10          # matches Flight Centre's own robots.txt Crawl-delay


@dataclass
class ManifestRow:
    url: str
    brand: str
    page_type: str
    file: str
    fetched_at: str
    http_status: int
    method: str             # "script" | "manual-view-source"
    words: int
    sha256: str


class Fetcher:
    """Politely download a URL list into corpus/<arm>/<brand>/ and manifest it."""

    def __init__(self, cfg: Config = CONFIG, delay: float = DELAY_SECONDS):
        self.cfg = cfg
        self.delay = delay
        self._robots_cache: dict = {}

    # -- politeness ------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
        if root not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self._robots_cache[root] = rp
        rp = self._robots_cache[root]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    # -- fetch -----------------------------------------------------------
    def fetch_one(self, url: str) -> Optional[requests.Response]:
        if not self._allowed(url):
            print(f"  [skip] robots.txt disallows {url}")
            return None
        try:
            return requests.get(url, timeout=30, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-AU,en;q=0.9"})
        except Exception as exc:
            print(f"  [FAILED] {url}: {exc}\n"
                  f"           fall back to Chrome > Ctrl+U > save, and log "
                  f"method='manual-view-source'")
            return None

    def fetch_all(self, urls_csv: Path, arm: str = "baseline") -> List[ManifestRow]:
        rows = list(csv.DictReader(open(urls_csv, encoding="utf-8")))
        out_root = self.cfg.corpus_dir / arm
        manifest: List[ManifestRow] = []
        for i, row in enumerate(rows, 1):
            url, brand = row["url"].strip(), row["brand"].strip()
            print(f"[{i}/{len(rows)}] {url}")
            resp = self.fetch_one(url)
            if resp is None:
                continue
            if resp.status_code != 200:
                print(f"  [warn] HTTP {resp.status_code} — if blocked, save "
                      f"manually and record the method")
            folder = out_root / brand
            folder.mkdir(parents=True, exist_ok=True)
            name = urllib.parse.quote(url, safe="")[-80:] + ".html"
            path = folder / name
            path.write_text(resp.text, encoding="utf-8")
            manifest.append(ManifestRow(
                url=url, brand=brand, page_type=row.get("page_type", ""),
                file=str(path), fetched_at=_dt.datetime.now().isoformat(timespec="seconds"),
                http_status=resp.status_code, method="script",
                words=len(resp.text.split()),
                sha256=hashlib.sha256(resp.text.encode()).hexdigest()[:16]))
            time.sleep(self.delay)
        self.write_manifest(manifest, arm)
        return manifest

    def write_manifest(self, rows: List[ManifestRow], arm: str) -> Path:
        path = self.cfg.corpus_dir / f"manifest_{arm}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys())
                               if rows else ["url"])
            w.writeheader()
            for r in rows:
                w.writerow(asdict(r))
        print(f"\nManifest: {path}")
        print("FREEZE RULE: do not fetch again after the snapshot is committed.")
        return path

    # -- freeze verification ---------------------------------------------
    def verify(self, arm: str = "baseline") -> bool:
        """Re-hash every file and compare with the manifest. Run before every
        experiment: it is a gate, not a report."""
        path = self.cfg.corpus_dir / f"manifest_{arm}.csv"
        if not path.exists():
            print("No manifest — cannot verify.")
            return False
        ok = True
        for row in csv.DictReader(open(path, encoding="utf-8")):
            p = Path(row["file"])
            if not p.exists():
                print(f"  MISSING {p}"); ok = False; continue
            digest = hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()[:16]
            if digest != row["sha256"]:
                print(f"  CHANGED {p}"); ok = False
        print("Corpus verified — unchanged since freeze." if ok
              else "CORPUS ALTERED — stop and investigate.")
        return ok
