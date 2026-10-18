"""Structured schema markup with real values, mirrored visibly.

Ports two lessons from this project's own history rather than repeating
either mistake:

1. The legacy geo_bench `schema_markup` arm once carried real
   Organization/Offer price values in JSON-LD and showed real reindexed
   movement (+63.2% PAWC, matched-pairs r=0.60, not significant at n=40,
   2026-09-07 decisions_log entry) -- but as of this session's inspection
   its code now explicitly excludes JSON-LD from the evaluated text
   (`geo_bench/optimisation/arms/schema_markup.py`: `clean = page.clean`,
   `notes.jsonld_excluded_from_text_evaluation=True`), reasoning that raw
   JSON tokens as BM25/embedding input tests keyword injection, not
   structured data. That objection is legitimate on its own terms, and this
   file appears to have been changed by other work on this repository
   between 2026-09-07 and now -- the earlier reported effect is not
   reproducible under the current code and should not be cited as current.
2. V3's own `schema_page_identity` avoids that objection by construction --
   it asserts the visible body is unchanged -- but as a direct consequence
   adds a mean of only +4.4 words (identity metadata only: @id, url, name
   already present in the H1), close to a no-op, which is the explanation
   already logged for its flat/negative result on both layers.

This module resolves the tension instead of picking a side: real,
per-page-verified values go into JSON-LD (Organization + Offer, price from
this exact page's own verified fact -- reuses `evidence()`, the same
grounding mechanism `structured_product_facts`/`page_grounded_faq` already
use, so nothing here is invented or query-derived) AND the identical
verified quote is separately mirrored as one small, genuinely visible
sentence in the body. The measurement therefore tests real visible content
(legitimate, like every other content arm) while the JSON-LD payload also
carries real values (legitimate structured data) -- rather than testing
raw-JSON-as-text or an empty identity stub.
"""
from __future__ import annotations

import html as htmlmod
import json
import re

from bs4 import BeautifulSoup

from .arms import Source, append_body, cleaned, evidence, sha, validate_evidence
from geo_bench.search.live_retriever import normalise_url

ARM = 'schema_structured_markup'


def _grounded_name(source: Source) -> str:
    soup = BeautifulSoup(source.html, 'html.parser')
    canonical = soup.find('link', rel='canonical')
    headings = soup.find_all('h1')
    if (canonical and normalise_url(canonical.get('href', '')) == normalise_url(source.url)
            and len(headings) == 1):
        h = headings[0]
        if not (h.has_attr('hidden') or h.get('aria-hidden') == 'true'
                or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', h.get('style', ''), re.I)):
            name = h.get_text(' ', strip=True)
            name = re.split(r'\s+(?:AU|A|US|NZ)?\$|\s+AUD\s', name, maxsplit=1)[0].strip()
            if name and name in source.clean and len(name) <= 250:
                return name
    return 'Flight Centre'


def structured_schema(source: Source, facts: list, exclude_fact_ids: frozenset = frozenset(),
                       exclude_quotes: frozenset = frozenset()) -> dict:
    priced = [e for e in evidence(source, facts)
              if e.claim_type == 'price' and e.fact_id not in exclude_fact_ids
              and e.quote not in exclude_quotes]
    chosen = priced[0] if priced else None
    name = _grounded_name(source)

    nodes = [
        {'@type': 'WebPage', '@id': source.url + '#geo-webpage', 'url': source.url, 'name': name},
        {'@type': 'Organization', 'name': 'Flight Centre', 'url': source.url},
    ]
    if chosen is not None:
        nodes.append({
            '@type': 'Offer', 'url': source.url, 'price': chosen.value,
            'priceCurrency': chosen.unit or 'AUD', 'name': name,
        })
    payload = {'@context': 'https://schema.org', '@graph': nodes}
    block = ('<script id="geo-v3-schema-structured" type="application/ld+json">'
              + json.dumps(payload, ensure_ascii=False) + '</script>\n')
    lower = source.html.lower()
    idx = lower.rfind('</head>')
    raw = source.html[:idx] + block + source.html[idx:] if idx >= 0 else source.html

    used = []
    if chosen is not None:
        raw = append_body(
            raw, '\n<p id="geo-v3-schema-visible">' + htmlmod.escape(chosen.quote) + '</p>\n')
        used = [chosen]

    text = cleaned(raw)
    ledger = [
        {'fact_id': e.fact_id, 'source_url': e.source_url, 'source_sha256': e.source_sha256,
         'start': e.start, 'end': e.end, 'quote': e.quote, 'value': e.value,
         'claim_type': e.claim_type, 'unit': e.unit}
        for e in used
    ]
    if used:
        validate_evidence(source, ledger, facts)

    return {
        'arm': ARM, 'url': source.url, 'html': raw, 'clean': text,
        'source_sha256': sha(source.clean), 'raw_sha256': sha(raw),
        'clean_sha256': sha(text), 'evidence': ledger,
        'notes': {
            'schema_price_included': chosen is not None,
            'visible_mirror_added': bool(used),
            'unchanged_reason': '' if used else 'no_verified_price_for_this_page',
            'interpretation': (
                'real Organization/Offer JSON-LD values mirrored as one '
                'visible verified sentence; unlike schema_page_identity this '
                'is not a near-no-op, and unlike raw-JSON-as-text this does '
                'not feed markup tokens through the retriever'
            ),
        },
    }
