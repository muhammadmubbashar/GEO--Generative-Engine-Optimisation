"""keyword_stuffing — negative control.

Insert ceil(rate * baseline_words) additional words: the client queries this
URL serves, lowercased and space-joined, repeated in one visible <p> at the
end of <body>. Never hidden.
"""
from __future__ import annotations

import csv
import hashlib
import html as htmlmod
import math

from ...config import CONFIG
from ..base import Arm, FrozenPage, OptimisedPage
from ..facts import FactTable
from ...retrieval.cleaner import clean_html


def _queries_for(page: FrozenPage) -> str:
    qmap = {
        r["id"]: r["query"]
        for r in csv.DictReader(CONFIG.queries_file.open(encoding="utf-8"))
    }
    parts = []
    for qid in page.queries_served:
        q = qmap.get(qid)
        if q:
            parts.append(q.lower())
    return " ".join(parts).strip()


class KeywordStuffingArm(Arm):
    name = "keyword_stuffing"
    needs_verified_facts = False
    uses_llm = False
    preserves_length = False

    def optimise(self, page: FrozenPage, facts: FactTable) -> OptimisedPage:
        blob = _queries_for(page)
        if not blob:
            raise RuntimeError(
                f"keyword_stuffing: no client queries for {page.url}")
        kw_words = blob.split()
        target = max(1, math.ceil(CONFIG.keyword_stuffing_rate * page.words))
        n_copies = max(1, math.ceil(target / max(len(kw_words), 1)))
        stuffed = " ".join([blob] * n_copies)
        added = stuffed.split()
        if len(added) > target + len(kw_words):
            stuffed = " ".join(added[:target])
        para = (
            f'\n<p class="geo-keyword-stuffing">{htmlmod.escape(stuffed)}</p>\n'
        )
        html = page.html
        low = html.lower()
        idx = low.rfind("</body>")
        if idx >= 0:
            html = html[:idx] + para + html[idx:]
        else:
            html = html + para
        body, jsonld = clean_html(html)
        clean = (body + " " + jsonld).strip()
        digest = hashlib.sha256(
            html.encode("utf-8", errors="replace")).hexdigest()
        return OptimisedPage(
            url=page.url, arm=self.name, html=html, clean=clean,
            content_hash=digest, baseline_sha256=page.sha256,
            baseline_words=page.words, optimised_words=len(clean.split()),
            page_type=page.page_type,
            notes={
                "preserves_length": False,
                "keyword_words_added": len(stuffed.split()),
                "keyword_copies": n_copies,
            },
        )
