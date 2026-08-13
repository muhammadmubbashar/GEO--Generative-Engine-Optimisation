"""Sitemap sweep — layer one of a three-layer collection procedure.

    1  sitemap sweep      (this module)   systematic, fast
    2  per-query site:    (manual)        catches what sitemaps miss, and
                                          produces the dated NONE evidence
    3  one-hop link crawl (manual)        catches oddly-slugged pages

Layer 2 is the one that matters most: it removes the researcher's judgement
about which page is relevant and hands it to an external system, applied
identically to every brand.
"""
import re
from typing import List

import requests

USER_AGENT = "Team62-QUT-Research-Fetcher (student capstone)"


def _get(url: str) -> str:
    try:
        return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30).text
    except Exception as exc:
        print(f"  [skip] {url}: {exc}")
        return ""


def sitemap_urls(domain: str, max_child_maps: int = 200) -> List[str]:
    robots = _get(f"https://{domain}/robots.txt")
    maps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots) or [f"https://{domain}/sitemap.xml"]
    urls: List[str] = []
    for sm in maps:
        found = re.findall(r"<loc>\s*(.*?)\s*</loc>", _get(sm))
        children = [u for u in found if "sitemap" in u.lower()
                    and u.endswith((".xml", ".xml.gz"))]
        urls += [u for u in found if u not in children]
        for child in children[:max_child_maps]:
            urls += re.findall(r"<loc>\s*(.*?)\s*</loc>", _get(child))
    return list(dict.fromkeys(urls))


def filter_by_keywords(urls: List[str], keywords: List[str]) -> List[str]:
    kw = [k.lower() for k in keywords]
    return [u for u in urls if any(k in u.lower() for k in kw)]
