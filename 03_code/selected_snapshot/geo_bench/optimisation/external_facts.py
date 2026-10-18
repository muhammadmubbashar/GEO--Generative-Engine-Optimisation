"""External (third-party) facts for `cite_sources`.

`FactTable` in facts.py holds facts extracted from Flight Centre's own freeze
pages — its source_url is always an FC URL, so it can never ground an
attribution that points anywhere but Flight Centre itself. `cite_sources`
exists to test genuine authority attribution, which means the source must be
an independent, checkable third party (config.py CONFIG.our_brand excluded).

This is a separate, small, human-curated table. Each row is matched to pages
by `match_type` (a named predicate below), never by "any page" — a fact only
attaches to a page when something on that page actually makes it relevant
(e.g. the page lists a Star Alliance partner airline by name), so a citation
never reads as a non sequitur.
"""
from __future__ import annotations

import csv
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

from ..config import CONFIG, Config

EXTERNAL_FACT_FIELDS = (
    "fact_id", "claim", "value", "unit", "sentence", "source_url",
    "source_name", "match_type", "verified_by", "verified_on", "status",
)

# Airlines that are actual Star Alliance members (as named on FC's own
# "Airline partners" sections). EXT0001 only attaches to a page when one of
# these appears in the page's own text — not to every international route.
_STAR_ALLIANCE_MEMBERS = (
    "Air New Zealand", "Singapore Airlines", "United Airlines", "Lufthansa",
    "ANA", "All Nippon Airways", "EVA Air", "Turkish Airlines", "Air Canada",
    "Swiss International", "Austrian Airlines", "Asiana Airlines",
    "Air China", "Air India", "Avianca", "Copa Airlines", "Croatia Airlines",
    "Egyptair", "Ethiopian Airlines", "LOT Polish Airlines",
    "Shenzhen Airlines", "South African Airways", "TAP Air Portugal",
    "Thai Airways",
)


@dataclass
class ExternalFact:
    fact_id: str
    claim: str
    value: str
    unit: str
    sentence: str
    source_url: str
    source_name: str
    match_type: str
    verified_by: str = ""
    verified_on: str = ""
    status: str = "candidate"

    def as_row(self) -> Dict[str, str]:
        return {k: str(getattr(self, k) or "") for k in EXTERNAL_FACT_FIELDS}

    def visible_sentence(self) -> str:
        return self.sentence

    @property
    def is_verified(self) -> bool:
        return self.status == "verified"


def _match_star_alliance_partner(page) -> bool:
    text = (page.clean or "") + " " + (page.title or "")
    return any(name in text for name in _STAR_ALLIANCE_MEMBERS)


def _match_sydney(page) -> bool:
    blob = (page.url or "").lower() + " " + (page.title or "").lower()
    return "sydney" in blob


_MATCHERS: Dict[str, Callable] = {
    "star_alliance_partner": _match_star_alliance_partner,
    "sydney": _match_sydney,
}


def is_fc_domain(url: str, cfg: Config = CONFIG) -> bool:
    """True if `url` resolves to a Flight Centre (our_brand) domain.

    Used to hard-block self-citation: cite_sources must never point back at
    the page it is citing from, or at any other FC-owned domain.
    """
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    fc_hosts = {d.lower() for d, brand in cfg.brand_domains if brand == cfg.our_brand}
    return any(host == h or host.endswith("." + h) for h in fc_hosts)


class ExternalFactTable:
    def __init__(self, facts: List[ExternalFact] | None = None,
                 cfg: Config = CONFIG):
        self.cfg = cfg
        self.facts = list(facts or [])

    @classmethod
    def load(cls, path: Path | None = None,
             cfg: Config = CONFIG) -> "ExternalFactTable":
        p = path or cfg.external_facts_file
        if not p.exists():
            return cls([], cfg)
        rows = list(csv.DictReader(p.open(encoding="utf-8")))
        facts = [
            ExternalFact(
                fact_id=(r.get("fact_id") or "").strip(),
                claim=(r.get("claim") or "").strip(),
                value=(r.get("value") or "").strip(),
                unit=(r.get("unit") or "").strip(),
                sentence=(r.get("sentence") or "").strip(),
                source_url=(r.get("source_url") or "").strip(),
                source_name=(r.get("source_name") or "").strip(),
                match_type=(r.get("match_type") or "").strip(),
                verified_by=(r.get("verified_by") or "").strip(),
                verified_on=(r.get("verified_on") or "").strip(),
                status=(r.get("status") or "candidate").strip(),
            )
            for r in rows
        ]
        return cls(facts, cfg)

    def verified(self) -> List[ExternalFact]:
        rows = [f for f in self.facts if f.is_verified]
        bad = [f for f in rows if is_fc_domain(f.source_url, self.cfg)]
        if bad:
            raise RuntimeError(
                "external_facts.csv has a verified row whose source_url is "
                f"an FC domain (self-citation is not allowed): "
                f"{[f.fact_id for f in bad]}"
            )
        return rows

    def for_page(self, page) -> List[ExternalFact]:
        """Verified external facts whose match_type predicate fires for this page."""
        out = []
        for f in self.verified():
            matcher = _MATCHERS.get(f.match_type)
            if matcher is None:
                continue
            if matcher(page):
                out.append(f)
        return out
