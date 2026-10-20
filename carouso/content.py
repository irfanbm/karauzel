from __future__ import annotations

import json
import re
from typing import Any

from .projects import new_slide
from .provider import ProviderConfig, complete, load_config
from .structures import CTA_TYPES, ROLES, STRUCTURES, outline

BANNED = ("unlock", "delve", "game-changer", "game changer", "elevate", "unleash", "tapestry", "dive into", "revolutionize")
HEADLINE_WORDS = 8
BODY_WORDS = 30


class GenerationError(RuntimeError):
    pass


def _brief_block(brief: dict[str, Any]) -> str:
    cta = CTA_TYPES.get(brief.get("cta_type", "save"), "Save this post")
    detail = brief.get("cta_detail") or ""
    lines = [
        f"Topic: {brief['topic']}",
        f"Goal: {brief.get('goal', 'educate')}",
        f"Audience: {brief.get('audience') or 'general audience'}",
        f"Language: {brief.get('language', 'English')} (write every field in this language)",
        f"Tone: {brief.get('tone', 'friendly')}",
        f"Call to action: {cta}{f' ({detail})' if detail else ''}",
    ]
    if brief.get("handle"):
        lines.append(f"Account handle: {brief['handle']}")
    source = (brief.get("source") or "").strip()
    if source:
        lines.append("Source material (base the content on this; do not contradict it):\n<<<\n" + source + "\n>>>")
    return "\n".join(lines)


RULES = f"""Rules:
- One idea per slide. The slides read as one connected argument, in order.
- headline: max {HEADLINE_WORDS} words, sentence case: first letter capital, the rest lowercase except names (not Title Case). body: max {BODY_WORDS} words.
- bullets: optional, 0 to 4 short items (max 7 words each). Use them only where a list helps.
- Write EVERY field, including the call to action, in the requested language. Do not leave English phrases like "Save this post" in a non-English carousel.
- If the hook mentions a count ("5 ways", "tiga langkah"), it must equal the number of content slides stated below. Safer: do not put a number in the hook.
- Be concrete and specific to the topic and audience. No hashtags, no emojis.
- Never use these words: {", ".join(BANNED)}.
- notes: only when a slide states a specific statistic, study, or factual claim that does NOT appear in the source material, write "Cek: <the claim>". Claims taken from the source material are already verified: leave notes "". Otherwise "".
- The last slide (role cta) must ask for the given call to action."""


LIST_ROLES = ("point", "step", "myth", "solution")


def _outline_block(slides: list[dict[str, Any]]) -> str:
    lines = [
        f"{index}. role={slide['role']} ({ROLES.get(slide['role'], ROLES['point'])['hint']})"
        for index, slide in enumerate(slides, 1)
    ]
    counts = {role: sum(1 for slide in slides if slide["role"] == role) for role in LIST_ROLES}
    listed = [f"{count} {role} slides" for role, count in counts.items() if count]
    if listed:
        lines.append(f"Content slides: {', '.join(listed)}. Any count promised in the hook must match this.")
    return "\n".join(lines)


NUMBER_WORDS = {
    "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
COUNT_NOUNS = r"(cara|tips?|langkah|mitos|kebiasaan|kesalahan|hal|alasan|trik|rahasia|ways?|steps?|tips|myths?|habits?|mistakes?|things?|reasons?|tricks?|secrets?)"


def promised_count(headline: str) -> int | None:
    text = headline.lower()
    match = re.search(rf"\b(\d{{1,2}}|{'|'.join(NUMBER_WORDS)})\s+(\w+\s+)?{COUNT_NOUNS}\b", text)
    if not match:
        return None
    token = match.group(1)
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def _sentence_case(text: str) -> str:
    return text[:1].upper() + text[1:] if text and text[0].islower() else text


def _extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if start == -1 or end == -1:
        raise GenerationError("Jawaban AI tidak terbaca. Coba lagi.")
    try:
        return json.loads(text[start : end + 1])
    except ValueError as error:
        raise GenerationError("Jawaban AI tidak lengkap. Coba lagi.") from error


def _text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit].rstrip()


def _apply(slide: dict[str, Any], item: dict[str, Any]) -> bool:
    headline = _text(item.get("headline"), 200)
    if not headline:
        return False
    slide["headline"] = _sentence_case(headline)
    options = item.get("headline_options") or []
    slide["headline_options"] = [_sentence_case(_text(option, 200)) for option in options if _text(option, 200)][:3] if isinstance(options, list) else []
    slide["body"] = _sentence_case(_text(item.get("body"), 600))
    bullets = item.get("bullets") or []
    slide["bullets"] = [_text(b, 160) for b in bullets if _text(b, 160)][:4] if isinstance(bullets, list) else []
    slide["notes"] = _text(item.get("notes"), 300)
    return True


def _call(prompt: str, config: ProviderConfig) -> Any:
    try:
        return _extract_json(complete(prompt, config))
    except RuntimeError as error:
        raise GenerationError(str(error)) from error


def _ready(config: ProviderConfig) -> None:
    if config.provider == "none" or not config.api_key or not config.base_url or not config.model:
        raise GenerationError("AI belum diatur. Buka Pengaturan AI dan isi API key, atau tulis slide secara manual.")


def _auto_outline(brief: dict[str, Any], config: ProviderConfig) -> list[str]:
    roles = ", ".join(key for key in ROLES)
    prompt = f"""Plan the slide flow for a social media carousel.
{_brief_block(brief)}
Total slides: {brief['slides']}
Available roles: {roles}
The first slide must be "hook" and the last must be "cta".
Return ONLY JSON: {{"roles": ["hook", "...", "cta"]}} with exactly {brief['slides']} items."""
    try:
        data = _call(prompt, config)
        planned = [str(role) for role in data["roles"] if str(role) in ROLES]
    except (GenerationError, KeyError, TypeError):
        return outline("listicle", brief["slides"])
    if len(planned) != brief["slides"] or planned[0] != "hook" or planned[-1] != "cta":
        return outline("listicle", brief["slides"])
    return planned


def generate_all(project: dict[str, Any], config: ProviderConfig | None = None) -> dict[str, Any]:
    """Fill every unlocked slide. Rebuilds the outline when the slide count or structure no longer matches."""
    config = config or load_config()
    _ready(config)
    brief = project["brief"]
    if not brief.get("topic"):
        raise GenerationError("Isi topik dulu.")
    slides = project["slides"]
    locked = [slide for slide in slides if slide.get("locked")]
    if not locked and (len(slides) != brief["slides"] or not any(slide["headline"] for slide in slides)):
        roles = _auto_outline(brief, config) if brief["structure"] == "auto" else outline(brief["structure"], brief["slides"])
        slides = [new_slide(role) for role in roles]
    kept = "\n".join(
        f"- slide {index} (locked, keep consistent with it): {slide['headline']} / {slide['body']}"
        for index, slide in enumerate(slides, 1)
        if slide.get("locked") and slide["headline"]
    )
    prompt = f"""You write the content for a social media carousel.
{_brief_block(brief)}
Structure: {STRUCTURES[brief['structure']]['label']}
Slides ({len(slides)}), in order:
{_outline_block(slides)}
{kept}
{RULES}

Return ONLY JSON, no markdown:
{{"slides":[{{"number":1,"headline":"...","headline_options":["alternative 1","alternative 2"],"body":"...","bullets":[],"notes":""}}]}}
Only slide 1 uses headline_options. Provide exactly 2 alternatives for slide 1; for other slides use an empty array."""
    data = _call(prompt, config)
    try:
        items = {int(item["number"]): item for item in data["slides"]}
    except (KeyError, TypeError, ValueError) as error:
        raise GenerationError("Format jawaban AI tidak sesuai. Coba lagi.") from error
    filled = 0
    for index, slide in enumerate(slides, 1):
        if slide.get("locked") or index not in items:
            continue
        filled += _apply(slide, items[index])
    if filled == 0:
        raise GenerationError("AI tidak menghasilkan isi slide. Coba lagi.")
    project["slides"] = slides
    hook = slides[0] if slides and slides[0]["role"] == "hook" else None
    if hook and not hook.get("locked") and count_mismatch(slides):
        try:
            generate_one(project, hook["id"], config, fix=f"The hook promised a number that does not match: there are {list_count(slides)} content slides. Either use exactly that number or no number.")
        except GenerationError:
            pass
    return project


def list_count(slides: list[dict[str, Any]]) -> int:
    return sum(1 for slide in slides if slide["role"] in LIST_ROLES)


def count_mismatch(slides: list[dict[str, Any]]) -> bool:
    if not slides:
        return False
    promised = promised_count(slides[0]["headline"]) or promised_count(slides[0]["body"])
    actual = list_count(slides)
    return promised is not None and actual > 0 and promised != actual


def generate_one(project: dict[str, Any], slide_id: str, config: ProviderConfig | None = None, fix: str = "") -> dict[str, Any]:
    config = config or load_config()
    _ready(config)
    slides = project["slides"]
    index = next((i for i, slide in enumerate(slides) if slide["id"] == slide_id), None)
    if index is None:
        raise GenerationError("Slide tidak ditemukan.")
    target = slides[index]
    context = "\n".join(
        f"{i}. role={slide['role']}: {slide['headline'] or '(empty)'} / {slide['body']}"
        for i, slide in enumerate(slides, 1)
        if i != index + 1
    )
    current = f'Current version (write a clearly different one): "{target["headline"]}" / {target["body"]}' if target["headline"] else ""
    prompt = f"""Rewrite ONE slide of a social media carousel.
{_brief_block(project['brief'])}
The other slides, for context:
{context}

Write slide {index + 1}, role={target['role']} ({ROLES.get(target['role'], ROLES['point'])['hint']}).
It must fit its position: if the other slides use ordinals or numbers ("Pertama", "Step 2", "3."), use the one that belongs to this position. Do not repeat what another slide already says.
{_outline_block(slides).splitlines()[-1] if any(s["role"] in LIST_ROLES for s in slides) else ""}
{current}
{fix}
{RULES}

Return ONLY JSON: {{"headline":"...","body":"...","bullets":[],"notes":""}}"""
    data = _call(prompt, config)
    if isinstance(data, dict) and "slides" in data and data["slides"]:
        data = data["slides"][0]
    if not isinstance(data, dict) or not _apply(target, data):
        raise GenerationError("AI tidak menghasilkan isi slide. Coba lagi.")
    return project


def check(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Problems that block moving on (level=error) or deserve a look (level=warn)."""
    issues: list[dict[str, Any]] = []
    brief = project["brief"]
    if not brief.get("topic"):
        issues.append({"level": "error", "slide": None, "field": "topic", "message": "Topik masih kosong."})
    if len(project["slides"]) < 3:
        issues.append({"level": "error", "slide": None, "field": "slides", "message": "Carousel butuh minimal 3 slide."})
    if count_mismatch(project["slides"]):
        promised = promised_count(project["slides"][0]["headline"]) or promised_count(project["slides"][0]["body"])
        issues.append({"level": "warn", "slide": 1, "field": "headline",
                       "message": f"Slide 1 menjanjikan {promised} poin, tapi ada {list_count(project['slides'])} slide isi."})
    for index, slide in enumerate(project["slides"], 1):
        headline_words = len(slide["headline"].split())
        body_words = len(slide["body"].split())
        if not slide["headline"].strip():
            issues.append({"level": "error", "slide": index, "field": "headline", "message": f"Slide {index} belum punya judul."})
        elif headline_words > HEADLINE_WORDS + 4:
            issues.append({"level": "warn", "slide": index, "field": "headline", "message": f"Judul slide {index} {headline_words} kata, mungkin tidak muat."})
        if body_words > BODY_WORDS + 15:
            issues.append({"level": "warn", "slide": index, "field": "body", "message": f"Isi slide {index} {body_words} kata, mungkin tidak muat."})
        if slide.get("notes", "").lower().startswith(("cek", "verify")):
            issues.append({"level": "warn", "slide": index, "field": "notes", "message": f"Slide {index}: {slide['notes']}"})
    return issues
