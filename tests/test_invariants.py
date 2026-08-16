"""Fast invariant checks — no network, no API keys.

Run:  python -m pytest tests/ -q
"""
import math

import pytest

from geo_bench.config import CONFIG
from geo_bench.evaluation.judge import (
    mask_brands, response_quality, verify_masking,
)
from geo_bench.evaluation.metrics import position_adjusted_word_count
from geo_bench.evaluation.statistics import _holm, rank_biserial
from geo_bench.experiment.selection import _parse_selection
from geo_bench.generation.generator import shuffle_passages, prompt_char_budget
from geo_bench.generation.prompts import build_prompt, prompt_sha256
from geo_bench.api.base import Passage
from geo_bench.search.live_retriever import page_source


def _p(i: str, brand: str = "flightcentre", text: str = "word " * 300):
    return Passage(id=i, brand=brand, text=text, file=f"http://x/{i}")


# ---- PAWC ---------------------------------------------------------------

def test_pawc_zero_without_citation():
    assert position_adjusted_word_count("No citations here.", {1: "flightcentre"},
                                        "flightcentre") == 0.0


def test_pawc_single_sentence_full_credit():
    # One sentence, cites [1] only: score = words*exp(-1/1)/words = e^-1.
    got = position_adjusted_word_count("Book with us [1].", {1: "flightcentre"},
                                       "flightcentre")
    assert got == pytest.approx(math.exp(-1))


def test_pawc_splits_co_citations():
    one = position_adjusted_word_count("Fly cheap [1].", {1: "fc", 2: "sky"}, "fc")
    both = position_adjusted_word_count("Fly cheap [1][2].", {1: "fc", 2: "sky"}, "fc")
    assert both == pytest.approx(one / 2)


def test_pawc_ignores_out_of_range_citations():
    got = position_adjusted_word_count("Fly cheap [7].", {1: "fc"}, "fc")
    assert got == 0.0


# ---- statistics ---------------------------------------------------------

def test_rank_biserial_extremes_and_symmetry():
    assert rank_biserial([1.0, 2.0, 0.5]) == 1.0
    assert rank_biserial([-1.0, -2.0]) == -1.0
    assert rank_biserial([1.0, -1.0]) == 0.0
    assert math.isnan(rank_biserial([0.0, 0.0]))


def test_holm_adjusted_never_below_raw_and_monotone():
    raw = [0.01, 0.04, 0.03, 0.20]
    adj = _holm(raw)
    assert all(a >= r for a, r in zip(adj, raw))
    order = sorted(range(4), key=lambda i: raw[i])
    assert all(adj[order[i]] <= adj[order[i + 1]] + 1e-12 for i in range(3))


# ---- judge masking ------------------------------------------------------

def test_mask_covers_study_brands_and_extras():
    text = ("Flight Centre's deals beat Skyscanner, webjet.com.au, Expedia "
            "and Booking.com; TripAdvisor agrees.")
    masked = mask_brands(text, CONFIG)
    assert not verify_masking(text, CONFIG)
    assert verify_masking(masked, CONFIG)
    assert "Brand A" in masked


def test_response_quality_weights():
    assert response_quality(2, 2, 2, 2) == 10.0
    assert response_quality(0, 0, 0, 0) == 0.0
    # accuracy carries 40%
    assert response_quality(2, 0, 0, 0) == pytest.approx(4.0)


# ---- generation determinism --------------------------------------------

def test_shuffle_deterministic_per_seed():
    ps = [_p(f"p{i}") for i in range(5)]
    a = [p.id for p in shuffle_passages(ps, 12345)]
    b = [p.id for p in shuffle_passages(ps, 12345)]
    c = [p.id for p in shuffle_passages(ps, 54321)]
    assert a == b
    assert a != c


def test_prompt_budget_truncates_and_is_configurable():
    ps = [_p("p1", text="x" * 5000)]
    short = build_prompt("q", ps, max_chars=100)
    full = build_prompt("q", ps, max_chars=2600)
    assert "x" * 100 in short and "x" * 101 not in short
    assert "x" * 2600 in full


def test_prompt_budget_splits_fixed_page_vs_reindexed_chunk():
    assert prompt_char_budget("fixed", CONFIG) == CONFIG.page_prompt_chars
    assert prompt_char_budget("reindexed", CONFIG) == CONFIG.passage_prompt_chars
    assert CONFIG.fixed_source_unit == "full_page"
    assert CONFIG.page_prompt_chars > CONFIG.passage_prompt_chars


def test_page_source_keeps_full_text_not_a_slice():
    body = ("flights to melbourne. " * 400).strip()  # well over 350 words
    assert page_source(body, "snippet only") == body
    assert len(page_source(body).split()) > 350
    assert page_source("", "fallback snippet here") == "fallback snippet here"[:500]


def test_prompt_sha_stable():
    assert prompt_sha256() == prompt_sha256()
    assert len(prompt_sha256()) == 64


# ---- selection parsing --------------------------------------------------

def test_selection_parse_dedup_bounds_and_cap():
    valid = set(range(1, 21))
    assert _parse_selection("[3, 1, 3, 99, 7, 2, 5, 4]", valid, 5) == [3, 1, 7, 2, 5]
    assert _parse_selection("```json\n[2]\n```", valid, 5) == [2]
    with pytest.raises(RuntimeError):
        _parse_selection("no numbers", valid, 5)
    with pytest.raises(RuntimeError):
        _parse_selection("[99]", valid, 5)
