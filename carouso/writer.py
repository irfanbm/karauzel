from __future__ import annotations

import json
import re

from .engine import CarouselPlan
from .provider import ProviderConfig, complete, load_config

BANNED = ("unlock", "delve", "game-changer", "game changer", "elevate", "unleash", "journey", "tapestry", "dive into")

PATTERN_HINTS = {
    "cover-big-type": "opening hook, bold promise",
    "cover-split": "opening hook beside an image",
    "kicker-statement": "one sharp statement",
    "stat-band": "a statistic with context",
    "big-number": "one number that matters",
    "concept-number": "a named concept, numbered",
    "quote": "a short quotable line",
    "two-cards": "two contrasting ideas",
    "image-hero": "image-led point",
    "process-steps": "a short sequence of steps",
    "myth-fact": "a common myth, then the fact",
    "takeaway": "the one thing to remember",
    "checklist": "practical do-this items",
    "comparison-table": "A versus B",
    "timeline": "progress over time",
    "testimonial": "a believable first-person experience",
    "photo-grid": "several visual examples",
    "stack-cards": "a short list of points",
    "percent-ring": "one percentage and what it means",
    "cta-follow": "closing call to follow or save",
}


def _prompt(plan: CarouselPlan) -> str:
    brief = plan.brief
    outline = "\n".join(
        f"{slide.number}. pattern={slide.pattern} ({PATTERN_HINTS.get(slide.pattern, 'content slide')})"
        for slide in plan.slides
    )
    return f"""You write copy for a social media carousel.
Topic: {brief.topic}
Audience: {brief.audience}
Language: {brief.language} (write every field in this language)
Tone/style: {brief.style}
Slides ({len(plan.slides)}), each with a fixed layout pattern:
{outline}

Rules:
- One idea per slide. The slides must read as one connected argument, not generic filler.
- headline: max 8 words. body: max 28 words. eyebrow: max 4 words, a short label.
- Be concrete and specific to the topic. No hashtags, no emojis.
- Never use these words: {", ".join(BANNED)}.
- Fit each slide to its pattern purpose.

Return ONLY JSON, no markdown:
{{"slides":[{{"number":1,"eyebrow":"...","headline":"...","body":"..."}}]}}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(text[start : end + 1])


def _clean(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def write_copy(plan: CarouselPlan, config: ProviderConfig | None = None) -> tuple[CarouselPlan, str]:
    """Fill slide copy with the configured LLM. Returns (plan, source) where source is 'llm' or 'rules: <reason>'."""
    config = config or load_config()
    if config.provider == "none" or not config.api_key:
        return plan, "rules: no provider configured"
    try:
        data = _extract_json(complete(_prompt(plan), config))
        items = {int(item["number"]): item for item in data["slides"]}
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        return plan, f"rules: {error}"
    filled = 0
    for slide in plan.slides:
        item = items.get(slide.number)
        if not item:
            continue
        headline = _clean(item.get("headline"), 90)
        body = _clean(item.get("body"), 220)
        if not headline:
            continue
        slide.headline = headline
        slide.body = body or slide.body
        slide.eyebrow = _clean(item.get("eyebrow"), 40) or slide.eyebrow
        filled += 1
    if filled == 0:
        return plan, "rules: provider returned no usable slides"
    return plan, "llm"
