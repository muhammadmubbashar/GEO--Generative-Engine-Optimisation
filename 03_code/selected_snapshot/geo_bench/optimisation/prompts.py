"""Prompt templates for LLM-driven arms only (statistics_addition, cite_sources).

Schema, FAQ, keyword stuffing and padding are deterministic — they have no
prompts. The fact constraint below is required verbatim in every LLM prompt.
"""

FACT_CONSTRAINT = (
    "Use ONLY facts from the VERIFIED FACTS list supplied below. Do not invent any "
    "figure, statistic, price, date, quotation, review, or source. If no verified "
    "fact supports a statement, leave that statement unchanged. It is correct and "
    "expected to make no change where no verified fact applies."
)

_PATCH_RULES = """Do not echo the original HTML. Pages are too large to rewrite wholesale.

Return ONLY a JSON array (no markdown fence) of objects:
[{"old": "<exact phrase copied from VISIBLE TEXT>", "new": "<rewritten phrase>"}]

- "old" must be copied exactly from VISIBLE TEXT (10–180 characters).
- "new" may only add or specify figures that appear in VERIFIED FACTS.
- Change as little as possible. If nothing should change, return []
"""

STATISTICS_PROMPT = """You rewrite Flight Centre page wording so vague claims become
specific, using only verified facts.

{fact_constraint}

VERIFIED FACTS:
{facts}

VISIBLE TEXT:
{text}

{patch_rules}

Rules:
- Rewrite in place via the JSON patches. Do not append a new section.
- Keep length close to the original phrase.
"""

CITE_SOURCES_PROMPT = """You add attribution to Flight Centre page wording,
using only verified facts and their source URLs.

{fact_constraint}

VERIFIED FACTS:
{facts}

VISIBLE TEXT:
{text}

{patch_rules}

Rules:
- Every citation must use a source_url from the verified facts list.
- Keep length close to the original phrase.
- Do not invent sources, quotes, or figures.
"""

VISIBLE_CHAR_CAP = 6000


def _visible(text: str) -> str:
    t = (text or "").strip()
    if len(t) <= VISIBLE_CHAR_CAP:
        return t
    return t[:VISIBLE_CHAR_CAP] + "\n[...truncated...]"


def render_statistics_prompt(html: str, facts_block: str) -> str:
    return STATISTICS_PROMPT.format(
        fact_constraint=FACT_CONSTRAINT, facts=facts_block,
        text=_visible(html), patch_rules=_PATCH_RULES)


def render_cite_prompt(html: str, facts_block: str) -> str:
    return CITE_SOURCES_PROMPT.format(
        fact_constraint=FACT_CONSTRAINT, facts=facts_block,
        text=_visible(html), patch_rules=_PATCH_RULES)
