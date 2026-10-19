from __future__ import annotations

import hashlib
import html
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Any

PATTERNS = (
    "cover-big-type",
    "cover-split",
    "kicker-statement",
    "stat-band",
    "big-number",
    "concept-number",
    "quote",
    "two-cards",
    "image-hero",
    "process-steps",
    "myth-fact",
    "takeaway",
    "checklist",
    "comparison-table",
    "timeline",
    "testimonial",
    "photo-grid",
    "stack-cards",
    "percent-ring",
    "cta-follow",
)

@dataclass
class Brief:
    topic: str
    audience: str = "general audience"
    language: str = "English"
    slides: int = 6
    style: str = "clean and minimal"
    variation: str = "balanced"
    seed: str | None = None
    images: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Brief":
        topic = str(data.get("topic", "")).strip()
        if not topic:
            raise ValueError("topic is required")
        slides = max(3, min(12, int(data.get("slides", 6))))
        return cls(
            topic=topic,
            audience=str(data.get("audience", cls.audience)).strip() or cls.audience,
            language=str(data.get("language", cls.language)).strip() or cls.language,
            slides=slides,
            style=str(data.get("style", cls.style)).strip() or cls.style,
            variation=str(data.get("variation", cls.variation)).strip() or cls.variation,
            seed=str(data["seed"]) if data.get("seed") is not None else None,
            images=[str(item) for item in data.get("images", []) if str(item).strip()],
        )

@dataclass
class SlidePlan:
    number: int
    pattern: str
    eyebrow: str
    headline: str
    body: str
    mode: str
    image: str | None = None

@dataclass
class CarouselPlan:
    brief: Brief
    slides: list[SlidePlan]
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {"brief": asdict(self.brief), "slides": [asdict(slide) for slide in self.slides], "signature": self.signature}

def _seed(brief: Brief) -> int:
    value = brief.seed or f"{brief.topic}|{brief.style}|{brief.slides}"
    return int(hashlib.sha256(value.encode()).hexdigest()[:16], 16)

def compose(brief: Brief) -> CarouselPlan:
    rng = random.Random(_seed(brief))
    available = list(PATTERNS)
    cover = rng.choice(("cover-big-type", "cover-split"))
    body = [pattern for pattern in available if pattern not in {"cover-big-type", "cover-split", "takeaway", "cta-follow"}]
    rng.shuffle(body)
    choices = [cover]
    while len(choices) < brief.slides - 1:
        candidate = next(pattern for pattern in body if pattern != choices[-1] and pattern not in choices)
        choices.append(candidate)
    choices.append(rng.choice(("takeaway", "cta-follow")))
    choices = choices[:brief.slides]
    modes = ["light" if index % 2 == 0 else "dark" for index in range(len(choices))]
    slides = []
    for index, (pattern, mode) in enumerate(zip(choices, modes), 1):
        image = brief.images[(index - 1) % len(brief.images)] if brief.images else None
        slides.append(SlidePlan(index, pattern, f"{brief.topic} / {brief.style}", _headline(brief.topic, index, len(choices)), _body(brief.topic, index, len(choices)), mode, image))
    signature = hashlib.sha256("|".join(choices).encode()).hexdigest()[:12]
    return CarouselPlan(brief, slides, signature)

def _headline(topic: str, index: int, total: int) -> str:
    if index == 1:
        return topic
    if index == total:
        return "Make the next move"
    return ["Start with the part that matters", "A simpler way to see it", "Use this as your filter", "The detail most people miss", "Turn the idea into action"][index % 5]

def _body(topic: str, index: int, total: int) -> str:
    if index == 1:
        return f"A practical carousel about {topic.lower()}."
    if index == total:
        return "Save this for the next time you need a clear starting point."
    return f"Connect this idea back to {topic.lower()}, then choose one small action you can repeat."

def render_html(plan: CarouselPlan, title: str = "Carouso draft") -> str:
    slides = []
    for slide in plan.slides:
        image = f'<img src="{html.escape(slide.image, quote=True)}" alt="" loading="eager">' if slide.image else ""
        slides.append(f'''<section class="slide mode-{slide.mode}" data-pattern="{html.escape(slide.pattern, quote=True)}" data-slide="{slide.number}">
  <div class="eyebrow">{html.escape(slide.eyebrow)}</div>
  <div class="content"><h1>{html.escape(slide.headline)}</h1><p>{html.escape(slide.body)}</p>{image}</div>
  <div class="footer"><span>{slide.number:02d} / {len(plan.slides):02d}</span><span>{html.escape(plan.brief.style)}</span></div>
</section>''')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="design-system/system.css"></head><body><main class="carousel">{"".join(slides)}</main></body></html>'''
