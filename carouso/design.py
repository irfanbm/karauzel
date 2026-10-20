from __future__ import annotations

import colorsys
import html as html_lib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .provider import ProviderConfig, complete, load_config
from .fonts import PAIRINGS, pairing, font_pairing_defaults

HEX = re.compile(r"^#[0-9a-f]{6}$")

LAYOUTS = ("editorial", "split", "poster", "custom")
RATIOS = ("4:5", "1:1", "9:16")
PALETTES = {
    "paper": {"bg": "#f4efe4", "text": "#20211d", "accent": "#b8452a"},
    "clay": {"bg": "#e9dccb", "text": "#2f3a2c", "accent": "#a4563a"},
    "night": {"bg": "#1c1f1b", "text": "#f2ecdd", "accent": "#d6e05a"},
}
TYPES = ("editorial", "grotesk", "mono")
MODES = ("custom", "reference")

PAIRING_IDS = ("ai-recommendation",) + tuple(p["id"] for p in PAIRINGS)

TOKEN_CHOICES: dict[str, tuple[str, ...]] = {
    "layout": ("editorial", "split", "poster"),
    "pairing": PAIRING_IDS,
    "case": ("normal", "upper"),
    "weight": ("regular", "bold", "black"),
    "scale": ("m", "l", "xl"),
    "align": ("left", "center"),
    "density": ("airy", "balanced", "dense"),
    "decoration": ("none", "rule", "number", "frame"),
    "footer": ("none", "handle", "page", "handle-page"),
    "ratio": RATIOS,
}
TOKEN_LABELS = {
    "layout": {"editorial": "Editorial stack", "split": "Split statement", "poster": "Poster note"},
    "pairing": {p["id"]: p["label"] for p in PAIRINGS},
    "case": {"normal": "Kalimat biasa", "upper": "HURUF KAPITAL"},
    "weight": {"regular": "Regular", "bold": "Bold", "black": "Black"},
    "scale": {"m": "Sedang", "l": "Besar", "xl": "Monumental"},
    "align": {"left": "Rata kiri", "center": "Rata tengah"},
    "density": {"airy": "Lega", "balanced": "Seimbang", "dense": "Padat"},
    "decoration": {"none": "Tanpa ornamen", "rule": "Garis tipis", "number": "Angka besar", "frame": "Bingkai"},
    "footer": {"none": "Tanpa footer", "handle": "Handle saja", "page": "Nomor halaman", "handle-page": "Handle + nomor"},
    "ratio": {"4:5": "4:5 Feed", "1:1": "1:1 Square", "9:16": "9:16 Story"},
}
PATTERNS = ("cover-type", "cover-split", "statement", "numbered", "list", "quote", "split-panel", "ui-metric", "ui-feed", "ui-editorial", "cta")
SLIDE_MODES = ("base", "invert")

DESIGN_RULES = """Fundamental rules (non-negotiable):
1. Hierarchy: one dominant element per slide. Headline size stays between 1.9x and 2.4x body size so it remains readable without consuming the canvas. Never two competing focal points.
2. Grid and margin: every slide shares the same outer margin and the same footer position. Text never touches the edge.
3. Alignment: body copy is left-aligned. Center alignment only for short covers, quotes, or CTA.
4. Typography: at most two typefaces (one headline, one body). No more than three sizes per slide.
5. Color: one background, one text color, one accent. The accent marks at most one element per slide. No gradients, no glow, no emoji.
6. Contrast: body text at least 4.5:1, large text at least 3:1 against its background.
7. Rhythm: the cover and the CTA use different patterns from the middle slides. Never repeat the same pattern on two consecutive slides. Invert the color mode at most at the turning point, not randomly.
8. Honesty: no fake images, fake logos, fake stats, or decorative filler. If a slide has no real image, use typography, not a placeholder.
9. Restraint: whitespace is a design element. If unsure, remove an element instead of adding one.
10. Anti-slop filter: no generic hero stack, no repeated centered layout, no decorative grid without purpose, no fake metrics, no badge filler, no invented claims. Every visual decision must serve hierarchy, readability, or the content.
11. Canvas lock: treat the canvas as a fixed artboard. Reserve 8% to 10% horizontal safe area and 9% to 12% vertical safe area. Place UI headers in the top safe zone, never vertically center them. Keep headline and body scale within a 2.4:1 ratio."""

ROLE_PATTERN = {
    "hook": "cover-type",
    "problem": "statement",
    "why": "statement",
    "myth": "statement",
    "before": "statement",
    "turn": "statement",
    "solution": "numbered",
    "point": "numbered",
    "step": "numbered",
    "after": "quote",
    "lesson": "quote",
    "proof": "quote",
    "story": "statement",
    "recap": "list",
    "cta": "cta",
}
ALTERNATE = {"numbered": "split-panel", "split-panel": "numbered", "statement": "quote", "quote": "statement", "list": "numbered"}
PIVOT_ROLES = ("solution", "turn", "lesson")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        text = "#" + "".join(char * 2 for char in text[1:])
    return text if HEX.match(text) else fallback


def _rgb(value: str) -> tuple[int, int, int]:
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(channel))):02x}" for channel in rgb)


def luminance(value: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(value)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def mix(a: str, b: str, amount: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _to_hex(tuple(x + (y - x) * amount for x, y in zip(ra, rb)))


def _choice(value: Any, key: str, fallback: str | None = None) -> str:
    options = TOKEN_CHOICES[key]
    return value if value in options else (fallback if fallback in options else options[0])


def _clean_points(value: Any) -> list[dict[str, Any]]:
    points = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", ""))
        kind = item.get("kind")
        point = {
            "key": key,
            "group": str(item.get("group", ""))[:40],
            "label": str(item.get("label", ""))[:60],
            "kind": kind,
            "why": str(item.get("why", ""))[:160],
            "use": item.get("use") is not False,
        }
        if kind == "color" and key in ("bg", "text", "accent"):
            point["value"] = _hex(item.get("value"), "#000000")
        elif kind == "choice" and key in TOKEN_CHOICES:
            point["value"] = _choice(item.get("value"), key)
            point["options"] = [{"value": option, "label": TOKEN_LABELS[key][option]} for option in TOKEN_CHOICES[key]]
        elif kind == "text" and key == "footer_text":
            point["value"] = str(item.get("value", ""))[:60]
        else:
            continue
        points.append(point)
    return points[:24]


def _clean_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("tokens"), dict):
        return None
    tokens = value["tokens"]
    clean_tokens = {key: _choice(tokens.get(key), key) for key in TOKEN_CHOICES}
    clean_tokens.update(font_pairing_defaults(clean_tokens["pairing"]))
    for key, fallback in (("bg", "#f4efe4"), ("text", "#20211d"), ("accent", "#b8452a"), ("muted", "#5f635c"), ("on_accent", "#ffffff")):
        clean_tokens[key] = _hex(tokens.get(key), fallback)
    clean_tokens["footer_text"] = str(tokens.get("footer_text", ""))[:60]
    slides = []
    for item in value.get("slides") or []:
        if isinstance(item, dict) and re.fullmatch(r"[a-f0-9]{8}", str(item.get("id", ""))):
            slides.append({
                "id": item["id"],
                "pattern": item.get("pattern") if item.get("pattern") in PATTERNS else "statement",
                "mode": item.get("mode") if item.get("mode") in SLIDE_MODES else "base",
            })
    return {
        "generated": str(value.get("generated", ""))[:30],
        "source": "ai" if value.get("source") == "ai" else "rules",
        "mode": value.get("mode") if value.get("mode") in MODES else "custom",
        "tokens": clean_tokens,
        "slides": slides[:12],
        "notes": [str(note)[:200] for note in (value.get("notes") or []) if str(note).strip()][:8],
    }


CHROME_DEFAULTS = {"page_indicator": True, "indicator_location": "footer", "indicator_type": "number", "first_header": True, "first_footer": True, "header_category": True, "header_divider": True, "header_title": True, "footer_brand": True}


def clean_chrome(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {key: (value.get(key) if isinstance(value.get(key), bool) else default) if isinstance(default, bool) else value.get(key) if value.get(key) in (("header", "footer") if key == "indicator_location" else ("number", "dot", "line", "bar")) else default for key, default in CHROME_DEFAULTS.items()}


def clean_design(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    custom = data.get("palette_custom") if isinstance(data.get("palette_custom"), dict) else {}
    design: dict[str, Any] = {
        "mode": data.get("mode") if data.get("mode") in MODES else "custom",
        "layout": data.get("layout") if data.get("layout") in LAYOUTS else "editorial",
        "layout_custom": str(data.get("layout_custom", ""))[:500],
        "body_template": data.get("body_template") if data.get("body_template") in ("auto", "hero", "editorial", "closing") else "auto",
        "pairing": data.get("pairing") if data.get("pairing") in PAIRING_IDS else "serif-contrast",
        "ratio": data.get("ratio") if data.get("ratio") in RATIOS else "4:5",
        "palette": data.get("palette") if data.get("palette") in (*PALETTES, "custom") else "paper",
        "palette_custom": {key: _hex(custom.get(key), PALETTES["paper"][key]) for key in ("bg", "text", "accent")},
    }
    references = []
    for item in data.get("references") or []:
        if not isinstance(item, dict):
            continue
        kind, ref = item.get("type"), str(item.get("value", "")).strip()
        if kind == "link" and re.fullmatch(r"https?://\S{1,2000}", ref):
            references.append({"type": "link", "value": ref})
        elif kind == "image" and re.fullmatch(r"[a-z0-9-]+\.(?:jpg|png|gif|webp)", ref):
            references.append({"type": "image", "value": ref})
    design["chrome"] = clean_chrome(data.get("chrome"))
    design["references"] = references[:6]
    design["reference_points"] = _clean_points(data.get("reference_points"))
    design["reference_summary"] = str(data.get("reference_summary", ""))[:400]
    result = _clean_result(data.get("result"))
    if result:
        design["result"] = result
    return design


KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("rata kiri", "kiri", "left"), "align", "left"),
    (("tengah", "center", "centered", "simetris"), "align", "center"),
    (("monumental", "raksasa", "huge", "giant", "sangat besar"), "scale", "xl"),
    (("besar", "big", "bold headline", "dominan"), "scale", "l"),
    (("kecil", "small", "subtle", "halus"), "scale", "m"),
    (("lega", "minimal", "minimalis", "airy", "whitespace", "ruang kosong", "bersih", "clean"), "density", "airy"),
    (("padat", "dense", "rapat", "informatif"), "density", "dense"),
    (("garis", "line", "rule", "divider"), "decoration", "rule"),
    (("angka", "nomor", "number", "numbered"), "decoration", "number"),
    (("bingkai", "frame", "border", "kotak"), "decoration", "frame"),
    (("kapital", "uppercase", "caps", "huruf besar semua"), "case", "upper"),
    (("tebal", "heavy", "black", "berat"), "weight", "black"),
    (("tipis", "light", "elegan", "elegant"), "weight", "regular"),
    (("split", "dua kolom", "terbagi", "kolom", "foto"), "layout", "split"),
    (("poster", "satu pesan", "impact", "statement besar"), "layout", "poster"),
    (("majalah", "editorial", "magazine"), "layout", "editorial"),
    (("serif", "klasik", "majalah", "elegan"), "pairing", "serif-contrast"),
    (("grotesk", "sans", "modern", "tegas"), "pairing", "grotesk-clean"),
    (("mono", "kode", "teknikal", "terminal", "code"), "pairing", "mono-technical"),
]


def _keyword_tokens(text: str) -> dict[str, str]:
    lowered = text.lower()
    found: dict[str, str] = {}
    for words, key, value in KEYWORDS:
        if key not in found and any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):
            found[key] = value
    return found


def recommend_pairing(project: dict[str, Any]) -> tuple[str, str]:
    brief = project.get("brief") or {}
    text = " ".join([str(brief.get(key, "")) for key in ("topic", "goal", "audience", "tone", "source")])
    text += " " + " ".join(str(slide.get(field, "")) for slide in project.get("slides") or [] for field in ("headline", "body"))
    lowered = text.lower()
    if any(word in lowered for word in ("kode", "data", "teknologi", "ai", "software", "sistem", "teknikal")):
        return "mono-technical", "Konten teknikal membutuhkan kontras sans display dan mono untuk rasa sistematis."
    if any(word in lowered for word in ("fashion", "seni", "budaya", "cerita", "kreatif", "brand", "majalah", "desain")):
        return "serif-modern", "Konten editorial/kreatif membutuhkan serif display yang berkarakter dan sans netral untuk isi."
    if any(word in lowered for word in ("langkah", "tips", "cara", "panduan", "belajar", "edukasi", "strategi")):
        return "grotesk-clean", "Konten instruksional membutuhkan grotesk yang tegas dan body sans yang stabil."
    return "serif-contrast", "Kontras serif display dan sans body memberi hirarki kuat tanpa mengorbankan keterbacaan."


def _layout_defaults(layout: str) -> dict[str, str]:
    base = {
        "editorial": {"align": "left", "scale": "l", "density": "airy", "decoration": "rule", "case": "normal", "weight": "bold"},
        "split": {"align": "left", "scale": "l", "density": "balanced", "decoration": "number", "case": "normal", "weight": "bold"},
        "poster": {"align": "center", "scale": "xl", "density": "airy", "decoration": "none", "case": "upper", "weight": "black"},
    }
    return {"layout": layout, **base.get(layout, base["editorial"])}


def base_tokens(project: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    design = clean_design(project.get("design"))
    brief = project.get("brief") or {}
    notes: list[str] = []
    if design["pairing"] == "ai-recommendation":
        recommended, rationale = recommend_pairing(project)
        design["pairing"] = recommended
        notes.append(f"AI rekomendasi tipografi: {TOKEN_LABELS['pairing'][recommended]}. {rationale}")
    handle = str(brief.get("handle", "")).strip()
    footer_text = handle if not handle or handle.startswith("@") else f"@{handle}"
    if design["mode"] == "reference" and design["reference_points"]:
        tokens: dict[str, Any] = {**_layout_defaults("editorial"), "pairing": "serif-contrast", **font_pairing_defaults("serif-contrast"), "ratio": design["ratio"], "footer": "handle-page" if footer_text else "page", "footer_text": footer_text, **PALETTES["paper"]}
        for point in design["reference_points"]:
            if point["use"]:
                tokens[point["key"]] = point["value"]
        notes.append("Token diambil dari analisa referensi yang Anda pilih.")
    else:
        layout = design["layout"] if design["layout"] != "custom" else "editorial"
        pairing_id = design["pairing"] if design["pairing"] != "ai-recommendation" else "serif-contrast"
        tokens = {**_layout_defaults(layout), "pairing": pairing_id, **font_pairing_defaults(pairing_id), "ratio": design["ratio"], "footer": "handle-page" if footer_text else "page", "footer_text": footer_text}
        if design["layout"] == "custom" and design["layout_custom"].strip():
            parsed = _keyword_tokens(design["layout_custom"])
            if "layout" in parsed:
                tokens.update(_layout_defaults(parsed["layout"]))
            tokens.update(parsed)
        palette = design["palette_custom"] if design["palette"] == "custom" else PALETTES[design["palette"]]
        tokens.update(palette)
    return tokens, notes


def enforce(tokens: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    clean = {key: _choice(tokens.get(key), key) for key in TOKEN_CHOICES}
    clean.update(font_pairing_defaults(clean["pairing"]))
    bg = _hex(tokens.get("bg"), "#f4efe4")
    text = _hex(tokens.get("text"), "#20211d")
    accent = _hex(tokens.get("accent"), "#b8452a")
    if contrast(bg, text) < 4.5:
        fixed = "#111111" if luminance(bg) > 0.4 else "#f5f2ea"
        notes.append(f"Kontras teks {contrast(bg, text)}:1 di bawah 4.5:1, warna teks dikoreksi ke {fixed}.")
        text = fixed
    if contrast(bg, accent) < 3:
        for amount in (0.25, 0.4, 0.55, 0.7):
            candidate = mix(accent, text, amount)
            if contrast(bg, candidate) >= 3:
                notes.append(f"Aksen terlalu pucat di atas latar ({contrast(bg, accent)}:1), digelapkan agar terbaca.")
                accent = candidate
                break
    muted = text
    for amount in (0.42, 0.34, 0.26, 0.18, 0.1):
        candidate = mix(text, bg, amount)
        if contrast(bg, candidate) >= 4.5:
            muted = candidate
            break
    on_accent = bg if contrast(accent, bg) >= contrast(accent, text) else text
    if clean["case"] == "upper" and clean["scale"] == "xl" and clean["density"] == "dense":
        clean["scale"] = "l"
        notes.append("Kapital + monumental + padat membuat slide sesak, skala diturunkan ke Besar.")
    if clean["align"] == "center" and clean["density"] == "dense":
        clean["align"] = "left"
        notes.append("Teks padat dibuat rata kiri agar mudah dibaca.")
    clean.update({"bg": bg, "text": text, "accent": accent, "muted": muted, "on_accent": on_accent, "footer_text": str(tokens.get("footer_text", ""))[:60]})
    return clean


def plan_slides(project: dict[str, Any], tokens: dict[str, Any], hints: dict[str, dict[str, str]] | None = None) -> list[dict[str, str]]:
    slides = [slide for slide in project.get("slides") or [] if slide.get("headline") or slide.get("body")]
    hints = hints or {}
    plan: list[dict[str, str]] = []
    pivot_used = False
    for index, slide in enumerate(slides):
        first, last = index == 0, index == len(slides) - 1 and len(slides) > 1
        role = slide.get("role", "point")
        hint = hints.get(slide.get("id", ""), {})
        if first:
            pattern = "cover-split" if tokens["layout"] == "split" and slide.get("images") else "cover-type"
        elif last:
            pattern = "cta"
        else:
            requested = hint.get("pattern")
            if requested in ("ui-metric", "ui-feed", "ui-editorial"):
                pattern = requested
            elif slide.get("bullets"):
                pattern = "ui-feed" if len(slide.get("bullets") or []) >= 3 else "ui-editorial"
            elif slide.get("images") and index % 3 == 1:
                pattern = "split-panel"
            elif index % 3 == 1:
                pattern = "ui-metric"
            else:
                pattern = "ui-editorial"
            if requested in ("ui-metric", "ui-feed", "ui-editorial"):
                pattern = requested
        if plan and plan[-1]["pattern"] == pattern and not first and not (last and role == "cta"):
            pattern = {"ui-metric": "ui-editorial", "ui-editorial": "ui-feed", "ui-feed": "ui-metric"}.get(pattern, ALTERNATE.get(pattern, "statement"))
        mode = "base"
        if last and role == "cta":
            mode = "invert"
        elif not first and not pivot_used and (hint.get("mode") == "invert" or role in PIVOT_ROLES):
            mode = "invert"
            pivot_used = True
        if tokens["layout"] == "poster" and first:
            mode = "invert"
        headline_len = len(str(slide.get("headline", "")))
        body_len = len(str(slide.get("body", "")))
        bullet_count = len(slide.get("bullets") or [])
        load = headline_len + body_len * 0.42 + bullet_count * 18
        if pattern in ("cover-type", "cover-split"):
            base = 0.82 if load < 110 else 0.70 if load < 180 else 0.58
        elif pattern == "cta":
            base = 0.74 if load < 130 else 0.62
        else:
            base = 0.68 if load < 150 else 0.58 if load < 240 else 0.48
        plan.append({"id": slide["id"], "pattern": pattern, "mode": mode, "fit": f"{base:.2f}", "load": f"{load:.0f}"})
    if len(plan) > 1 and plan[0]["mode"] == "invert" and plan[-1]["mode"] == "invert":
        for item in plan[1:-1]:
            item["mode"] = "base"
    return plan


def _parse_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no json")
    return json.loads(match.group(0))


def _ai_tokens(project: dict[str, Any], tokens: dict[str, Any], config: ProviderConfig) -> tuple[dict[str, Any], dict[str, dict[str, str]], list[str]]:
    design = clean_design(project.get("design"))
    slides = [slide for slide in project.get("slides") or [] if slide.get("headline") or slide.get("body")]
    canvas = {"4:5": {"width": 1080, "height": 1350}, "1:1": {"width": 1080, "height": 1080}, "9:16": {"width": 1080, "height": 1920}}[design["ratio"]]
    summary = [{"id": s["id"], "role": s.get("role"), "headline": s.get("headline", "")[:120], "headline_words": len(str(s.get("headline", "")).split()), "body_words": len(str(s.get("body", "")).split()), "bullets": len(s.get("bullets") or []), "has_image": bool(s.get("images"))} for s in slides]
    choices = {key: list(options) for key, options in TOKEN_CHOICES.items() if key not in ("ratio", "footer")}
    custom = design["layout_custom"].strip() if design["mode"] == "custom" and design["layout"] == "custom" else ""
    prompt = f"""You are a senior editorial art director designing an Instagram carousel. Return only JSON.

{DESIGN_RULES}

Canvas: {canvas['width']} x {canvas['height']} px. Treat this as a fixed mobile UI artboard, not an infinite desktop canvas. Text must fit inside safe margins; use a smaller type scale for 9:16 and never let a headline occupy more than 5 lines or body more than 7 lines.

Current tokens (already chosen by the user, keep them unless the user's free-text direction asks otherwise): {json.dumps({k: tokens[k] for k in choices}, ensure_ascii=False)}
User free-text layout direction (Indonesian or English, may be empty): {json.dumps(custom, ensure_ascii=False)}
Allowed token values: {json.dumps(choices)}
Allowed slide patterns: {json.dumps([p for p in PATTERNS])}. cover-type/cover-split only for slide 1, cta only for the final CTA slide. split-panel and cover-split only make sense when has_image is true or as a solid typographic panel.
Slides: {json.dumps(summary, ensure_ascii=False)}

Return:
{{"tokens": {{"layout": "...", "pairing": "...", "case": "...", "weight": "...", "scale": "...", "align": "...", "density": "...", "decoration": "..."}},
 "slides": [{{"id": "<id>", "pattern": "...", "mode": "base|invert"}}],
 "notes": ["max 3 short notes in Indonesian explaining the design decisions"]}}"""
    data = _parse_json(complete(prompt, config))
    raw = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    updated = dict(tokens)
    for key in choices:
        if raw.get(key) in TOKEN_CHOICES[key]:
            updated[key] = raw[key]
    hints = {}
    for item in data.get("slides") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            hints[item["id"]] = {"pattern": str(item.get("pattern", "")), "mode": str(item.get("mode", ""))}
    notes = [str(note)[:200] for note in (data.get("notes") or []) if isinstance(note, str) and note.strip()][:3]
    return updated, hints, notes


def generate(project: dict[str, Any], config: ProviderConfig | None = None) -> dict[str, Any]:
    slides = [slide for slide in project.get("slides") or [] if slide.get("headline") or slide.get("body")]
    if not slides:
        raise ValueError("Belum ada isi slide. Buat dulu di Brief.")
    design = clean_design(project.get("design"))
    tokens, notes = base_tokens(project)
    hints: dict[str, dict[str, str]] = {}
    source = "rules"
    config = config or load_config()
    if config.api_key and config.base_url and config.model:
        try:
            tokens, hints, ai_notes = _ai_tokens(project, tokens, config)
            notes = ai_notes + notes
            source = "ai"
        except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as error:
            notes.append(f"AI tidak bisa dipakai ({str(error)[:80]}), desain disusun dengan aturan sistem.")
    else:
        notes.append("AI belum diatur, desain disusun dengan aturan sistem.")
    final = enforce(tokens, notes)
    design["result"] = {"generated": _now(), "source": source, "mode": design["mode"], "tokens": final, "slides": plan_slides(project, final, hints), "notes": notes[:8]}
    project["design"] = design
    return project


def _fetch(url: str, limit: int) -> tuple[bytes, str]:
    from .projects import _public_host
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("URL harus diawali http:// atau https://")
    _public_host(parsed.hostname)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Carouso reference analyzer)", "Accept": "text/html,text/css,image/*;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read(limit), response.headers.get("Content-Type", "")
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise ValueError(f"Referensi tidak bisa dibuka: {error}") from error


def _saturation(value: str) -> float:
    r, g, b = (channel / 255 for channel in _rgb(value))
    return colorsys.rgb_to_hls(r, g, b)[2]


def _image_signals(data: bytes) -> dict[str, Any]:
    from PIL import Image, ImageFilter, ImageStat
    image = Image.open(io.BytesIO(data)).convert("RGB")
    width, height = image.size
    image.thumbnail((220, 220))
    quant = image.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quant.getpalette() or []
    counts = sorted(quant.getcolors() or [], reverse=True)
    colors = []
    total = sum(count for count, _ in counts) or 1
    for count, index in counts:
        rgb = tuple(palette[index * 3:index * 3 + 3])
        if len(rgb) == 3:
            colors.append({"hex": _to_hex(rgb), "share": round(count / total, 3)})
    edges = ImageStat.Stat(image.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    return {"colors": colors, "ratio": width / height if height else 1, "edges": edges}


CSS_COLOR = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)


def _page_signals(url: str) -> dict[str, Any]:
    data, kind = _fetch(url, 1_500_000)
    if kind.startswith("image/"):
        return {"image": _image_signals(data)}
    text = data.decode("utf-8", "ignore")
    css = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I)) + " " + " ".join(re.findall(r'style="([^"]*)"', text, re.I))
    for href in re.findall(r'<link[^>]+rel=["\']?stylesheet["\']?[^>]*href=["\']([^"\']+)', text, re.I)[:2]:
        try:
            sheet, _ = _fetch(urllib.parse.urljoin(url, html_lib.unescape(href)), 600_000)
            css += " " + sheet.decode("utf-8", "ignore")
        except ValueError:
            continue
    frequency: dict[str, int] = {}
    for found in CSS_COLOR.findall(css):
        color = _hex(found.lower(), "")
        if color:
            frequency[color] = frequency.get(color, 0) + 1
    fonts: dict[str, int] = {}
    for found in FONT_FAMILY.findall(css):
        family = found.split(",")[0].strip().strip("'\"").strip()
        if family and not family.startswith("var(") and family.lower() not in ("inherit", "initial", "unset"):
            fonts[family] = fonts.get(family, 0) + 1
    theme = re.search(r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\']([^"\']+)', text, re.I)
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', text, re.I)
    signals: dict[str, Any] = {
        "title": html_lib.unescape(title.group(1).strip())[:120] if title else "",
        "theme": _hex(theme.group(1), "") if theme else "",
        "css_colors": [color for color, _ in sorted(frequency.items(), key=lambda item: -item[1])[:12]],
        "fonts": [font for font, _ in sorted(fonts.items(), key=lambda item: -item[1])[:5]],
    }
    if og:
        try:
            image_data, image_kind = _fetch(urllib.parse.urljoin(url, html_lib.unescape(og.group(1))), 8_000_000)
            if image_kind.startswith("image/") or image_data[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb", b"RIFF"):
                signals["image"] = _image_signals(image_data)
        except (ValueError, OSError):
            pass
    return signals


def _font_type(fonts: list[str]) -> str | None:
    for font in fonts:
        lowered = font.lower()
        if any(word in lowered for word in ("mono", "code", "courier", "consol", "jetbrains")):
            return "mono"
        if any(word in lowered for word in ("serif", "georgia", "times", "playfair", "garamond", "lora", "merriweather", "fraunces", "dm serif", "libre baskerville")) and "sans" not in lowered:
            return "editorial"
        if lowered not in ("system-ui", "-apple-system", "blinkmacsystemfont"):
            return "grotesk"
    return None


def _pick_palette(colors: list[str]) -> dict[str, str]:
    colors = [color for color in colors if HEX.match(color)]
    if not colors:
        return {}
    bg = colors[0]
    text = max(colors + ["#111111", "#f5f2ea"], key=lambda color: contrast(bg, color))
    pool = [color for color in colors if color not in (bg, text) and contrast(bg, color) >= 1.8]
    accent = max(pool, key=_saturation) if pool else mix(text, bg, 0.35)
    return {"bg": bg, "text": text, "accent": accent}


def analyze(project: dict[str, Any], config: ProviderConfig | None = None) -> dict[str, Any]:
    from .projects import image_path
    design = clean_design(project.get("design"))
    refs = design["references"]
    if not refs:
        raise ValueError("Tambahkan minimal satu link atau gambar referensi.")
    colors: list[str] = []
    fonts: list[str] = []
    ratios: list[float] = []
    edges: list[float] = []
    sources: list[str] = []
    errors: list[str] = []
    for ref in refs:
        try:
            if ref["type"] == "image":
                path = image_path(project["id"], ref["value"])
                signals = {"image": _image_signals(path.read_bytes())}
                sources.append("gambar")
            else:
                signals = _page_signals(ref["value"])
                sources.append(urllib.parse.urlparse(ref["value"]).hostname or "link")
        except (ValueError, OSError) as error:
            errors.append(str(error)[:120])
            continue
        image = signals.get("image")
        if image:
            colors += [item["hex"] for item in image["colors"] if item["share"] >= 0.03]
            ratios.append(image["ratio"])
            edges.append(image["edges"])
        if signals.get("theme"):
            colors.insert(0, signals["theme"])
        colors += signals.get("css_colors", [])
        fonts += signals.get("fonts", [])
    if not sources:
        raise ValueError("Semua referensi gagal dianalisa. " + " ".join(errors[:2]))
    palette = _pick_palette(list(dict.fromkeys(colors)))
    type_guess = _font_type(fonts)
    density = "balanced"
    if edges:
        avg = sum(edges) / len(edges)
        density = "airy" if avg < 14 else "dense" if avg > 30 else "balanced"
    ratio = None
    if ratios:
        avg_ratio = sum(ratios) / len(ratios)
        ratio = min(RATIOS, key=lambda item: abs(avg_ratio - int(item.split(":")[0]) / int(item.split(":")[1])))
    dark = bool(palette) and luminance(palette["bg"]) < 0.2
    guess: dict[str, str] = {
        "layout": "poster" if density == "airy" and dark else "split" if density == "dense" else "editorial",
        "pairing": "serif-contrast" if type_guess == "editorial" else "mono-technical" if type_guess == "mono" else "grotesk-clean",
        "case": "upper" if dark and density != "dense" else "normal",
        "weight": "black" if dark else "bold",
        "scale": "xl" if density == "airy" else "l",
        "align": "center" if density == "airy" and dark else "left",
        "density": density,
        "decoration": "rule" if type_guess == "editorial" else "number" if density == "dense" else "none",
        "footer": "handle-page",
    }
    if ratio:
        guess["ratio"] = ratio
    summary = ""
    config = config or load_config()
    source = "rules"
    if config.api_key and config.base_url and config.model:
        try:
            prompt = f"""You are an art director reading the visual style of reference material for an Instagram carousel. Return only JSON.

{DESIGN_RULES}

Extracted signals:
- dominant colors (most frequent first): {json.dumps(list(dict.fromkeys(colors))[:12])}
- font families found: {json.dumps(fonts[:6])}
- visual density from edge analysis: {density}
- proposed palette: {json.dumps(palette)}
Allowed values: {json.dumps({k: list(v) for k, v in TOKEN_CHOICES.items() if k not in ('ratio',)})}

Return {{"palette": {{"bg": "#hex", "text": "#hex", "accent": "#hex"}}, "tokens": {{"layout": "...", "pairing": "...", "case": "...", "weight": "...", "scale": "...", "align": "...", "density": "...", "decoration": "...", "footer": "..."}}, "summary": "one or two Indonesian sentences describing the reference style"}}. Choose colors only from the dominant colors when possible."""
            data = _parse_json(complete(prompt, config))
            ai_palette = data.get("palette") if isinstance(data.get("palette"), dict) else {}
            for key in ("bg", "text", "accent"):
                value = _hex(ai_palette.get(key), "")
                if value:
                    palette[key] = value
            for key, value in (data.get("tokens") or {}).items():
                if key in TOKEN_CHOICES and value in TOKEN_CHOICES[key]:
                    guess[key] = value
            summary = str(data.get("summary", ""))[:400]
            source = "ai"
        except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
            pass
    if not summary:
        tone = "gelap" if dark else "terang"
        summary = f"Referensi bernuansa {tone} dengan kepadatan {TOKEN_LABELS['density'][density].lower()}" + (f" dan tipografi {TOKEN_LABELS['type'][guess['type']].lower()}." if type_guess else ".")
    why_color = "warna dominan referensi"
    points: list[dict[str, Any]] = []
    for key, label in (("bg", "Latar"), ("text", "Teks"), ("accent", "Aksen")):
        if palette.get(key):
            points.append({"key": key, "group": "Warna", "label": label, "kind": "color", "value": palette[key], "why": why_color, "use": True})
    groups = (
        ("Teks header", (("pairing", "Font pairing"), ("weight", "Ketebalan"), ("case", "Gaya huruf"), ("scale", "Ukuran"))),
        ("Body", (("align", "Perataan"), ("density", "Kepadatan"))),
        ("Komposisi", (("layout", "Gaya layout"), ("decoration", "Ornamen"), ("ratio", "Ukuran kanvas"))),
        ("Footer", (("footer", "Isi footer"),)),
    )
    for group, items in groups:
        for key, label in items:
            if key not in guess:
                continue
            why = "font di referensi" if key == "pairing" and type_guess else "kepadatan visual referensi" if key in ("density", "layout", "scale") else "turunan gaya referensi"
            points.append({"key": key, "group": group, "label": label, "kind": "choice", "value": guess[key], "why": why, "use": True})
    handle = str((project.get("brief") or {}).get("handle", "")).strip()
    points.append({"key": "footer_text", "group": "Footer", "label": "Teks footer", "kind": "text", "value": handle if not handle or handle.startswith("@") else f"@{handle}", "why": "handle dari Brief", "use": True})
    design["reference_points"] = _clean_points(points)
    design["reference_summary"] = summary + (f" ({len(errors)} referensi gagal dibuka.)" if errors else "")
    project["design"] = design
    return {"points": design["reference_points"], "summary": design["reference_summary"], "source": source}
