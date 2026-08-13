"""Exact-URL Common Crawl lookup via data.commoncrawl.org cluster.idx.

Avoids the rate-limited index.commoncrawl.org API.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from geo_bench.retrieval.cleaner import clean_html

DATA = "https://data.commoncrawl.org"
CACHE = Path("cache/commoncrawl")
CACHE.mkdir(parents=True, exist_ok=True)

DEFAULT_CRAWLS = (
    "CC-MAIN-2026-30",
    "CC-MAIN-2026-25",
    "CC-MAIN-2026-21",
    "CC-MAIN-2026-17",
    "CC-MAIN-2026-12",
)


def surt_key(url: str) -> str:
    u = urlsplit(url.strip())
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    parts.reverse()
    path = u.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return ",".join(parts) + ")" + path


def ensure_cluster_idx(crawl: str) -> Path:
    dest = CACHE / crawl / "cluster.idx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    url = f"{DATA}/cc-index/collections/{crawl}/indexes/cluster.idx"
    print(f"  [cc-idx] downloading cluster.idx for {crawl} …", flush=True)
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(".partial")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                if chunk:
                    fh.write(chunk)
        tmp.replace(dest)
    print(f"  [cc-idx] saved {dest} ({dest.stat().st_size:,} bytes)", flush=True)
    return dest


def _primary_key(line: bytes) -> str:
    text = line.decode("utf-8", "replace")
    head = text.split("\t", 1)[0]
    return head.split(" ", 1)[0]


def find_cdx_location(cluster_path: Path, urlkey: str) -> Optional[Dict]:
    lines = cluster_path.read_bytes().splitlines()
    lo, hi = 0, len(lines) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        key = _primary_key(lines[mid])
        if key <= urlkey:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    text = lines[best].decode("utf-8", "replace")
    try:
        head, rest = text.split("\t", 1)
        cdx, offset, length, *_ = rest.split("\t")
        return {
            "cdx": cdx.strip(),
            "offset": int(offset),
            "length": int(length),
            "primary_key": head.split(" ", 1)[0],
        }
    except Exception:
        return None


def _parse_cdxj_line(line: bytes) -> Optional[Dict]:
    text = line.decode("utf-8", "replace").strip()
    if not text:
        return None
    # CDXJ: urlkey timestamp {json}
    try:
        brace = text.index("{")
    except ValueError:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    meta = text[:brace].strip()
    payload = text[brace:]
    try:
        rec = json.loads(payload)
    except json.JSONDecodeError:
        return None
    parts = meta.split()
    if parts:
        rec.setdefault("urlkey", parts[0])
    if len(parts) > 1:
        rec.setdefault("timestamp", parts[1])
    return rec


def fetch_cdx_records(crawl: str, loc: Dict) -> List[Dict]:
    url = f"{DATA}/cc-index/collections/{crawl}/indexes/{loc['cdx']}"
    start = loc["offset"]
    end = loc["offset"] + loc["length"] - 1
    resp = requests.get(
        url, headers={"Range": f"bytes={start}-{end}"}, timeout=180)
    if resp.status_code not in (200, 206):
        return []
    raw = resp.content
    try:
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    except Exception:
        return []
    out = []
    for line in raw.splitlines():
        rec = _parse_cdxj_line(line)
        if rec:
            out.append(rec)
    return out


def lookup_record(crawl: str, page_url: str) -> Optional[Dict]:
    key = surt_key(page_url)
    cluster = ensure_cluster_idx(crawl)
    loc = find_cdx_location(cluster, key)
    if not loc:
        return None
    recs = fetch_cdx_records(crawl, loc)
    path = urlsplit(page_url).path.rstrip("/")
    good = []
    for rec in recs:
        status = str(rec.get("status") or "")
        mime = (rec.get("mime") or "").lower()
        u = rec.get("url") or ""
        uk = rec.get("urlkey") or ""
        if uk != key and path not in u:
            continue
        if status and status != "200":
            continue
        if mime and "html" not in mime:
            continue
        # require exact path match when possible
        if path and urlsplit(u).path.rstrip("/") != path:
            continue
        good.append(rec)
    if not good:
        return None
    good.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return good[0]


def fetch_warc_html(rec: Dict) -> str:
    filename = rec.get("filename") or ""
    if not filename:
        return ""
    offset = int(rec["offset"])
    length = int(rec["length"])
    resp = requests.get(
        f"{DATA}/{filename}",
        headers={"Range": f"bytes={offset}-{offset + length - 1}"},
        timeout=180,
    )
    if resp.status_code not in (200, 206) or not resp.content:
        return ""
    raw = resp.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    sep = b"\r\n\r\n"
    i = raw.find(sep)
    if i < 0:
        return ""
    rest = raw[i + 4:]
    j = rest.find(sep)
    if j < 0:
        return ""
    body = rest[j + 4:]
    nxt = body.find(b"\nWARC/")
    if nxt > 0:
        body = body[:nxt]
    return body.decode("utf-8", errors="replace")


def fetch_exact_url(page_url: str, crawls: Tuple[str, ...] = DEFAULT_CRAWLS
                    ) -> Optional[Dict]:
    """Return {html, cc_url, cc_index, cc_timestamp, words} or None."""
    for crawl in crawls:
        try:
            rec = lookup_record(crawl, page_url)
        except Exception as exc:
            print(f"  [cc-idx] {crawl} error: {exc}", flush=True)
            continue
        if not rec:
            continue
        html = fetch_warc_html(rec)
        if not html:
            continue
        body, jl = clean_html(html)
        words = len((body + " " + jl).split())
        if words < 40:
            continue
        return {
            "html": html,
            "cc_url": rec.get("url") or page_url,
            "cc_index": crawl,
            "cc_timestamp": rec.get("timestamp") or "",
            "cc_filename": rec.get("filename") or "",
            "words": words,
        }
    return None


if __name__ == "__main__":
    u = "https://www.expedia.com.au/lp/flights/syd/mel/sydney-to-melbourne"
    print("surt", surt_key(u))
    got = fetch_exact_url(u, crawls=("CC-MAIN-2026-21",))
    print("words", got["words"] if got else None, got.get("cc_timestamp") if got else None)
