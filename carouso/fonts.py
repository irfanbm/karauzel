"""Font pairing catalog: font display, body, fallback stack, dan pairing rules."""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# FONT FAMILY — setiap entri punya: nama, sumber (cdn), fallback CSS stack
# ---------------------------------------------------------------------------
FONTS: dict[str, dict[str, Any]] = {
    # --- Serif display (headline) ---
    "canela": {"family": "Canela", "cdn": "https://fontshare.com/fonts/canela.css", "fallback": "Georgia, serif", "role": "display"},
    "general_sans": {"family": "General Sans", "cdn": "https://fontshare.com/fonts/general-sans.css", "fallback": "system-ui, sans-serif", "role": "body"},
    "fraunces": {"family": "Fraunces", "cdn": "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600;9..144,700&display=swap", "fallback": "Georgia, serif", "role": "display"},
    "libre_baskerville": {"family": "Libre Baskerville", "cdn": "https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap", "fallback": "Georgia, serif", "role": "body"},
    "playfair_display": {"family": "Playfair Display", "cdn": "https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&display=swap", "fallback": "Georgia, serif", "role": "display"},
    "lora": {"family": "Lora", "cdn": "https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&display=swap", "fallback": "Georgia, serif", "role": "body"},
    "merriweather": {"family": "Merriweather", "cdn": "https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&display=swap", "fallback": "Georgia, serif", "role": "body"},
    "dm_serif_display": {"family": "DM Serif Display", "cdn": "https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&display=swap", "fallback": "Georgia, serif", "role": "display"},
    "editorial_new": {"family": "Editorial New", "cdn": "https://fontshare.com/fonts/editorial-new.css", "fallback": "Georgia, serif", "role": "display"},
    # --- Sans grotesk ---
    "general_sans_display": {"family": "General Sans", "cdn": "https://fontshare.com/fonts/general-sans.css", "fallback": "system-ui, sans-serif", "role": "display"},
    "clash_display": {"family": "Clash Display", "cdn": "https://fontshare.com/fonts/clash-display.css", "fallback": "system-ui, sans-serif", "role": "display"},
    "satoshi": {"family": "Satoshi", "cdn": "https://fontshare.com/fonts/satoshi.css", "fallback": "system-ui, sans-serif", "role": "body"},
    "space_grotesk": {"family": "Space Grotesk", "cdn": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;700&display=swap", "fallback": "system-ui, sans-serif", "role": "display"},
    "inter": {"family": "Inter", "cdn": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap", "fallback": "system-ui, sans-serif", "role": "body"},
    "work_sans": {"family": "Work Sans", "cdn": "https://fonts.googleapis.com/css2?family=Work+Sans:wght@300;400;500;600&display=swap", "fallback": "system-ui, sans-serif", "role": "body"},
    "jakarta": {"family": "Plus Jakarta Sans", "cdn": "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap", "fallback": "system-ui, sans-serif", "role": "body"},
    "manrope": {"family": "Manrope", "cdn": "https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap", "fallback": "system-ui, sans-serif", "role": "body"},
    # --- Mono ---
    "jetbrains_mono": {"family": "JetBrains Mono", "cdn": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&display=swap", "fallback": "Consolas, monospace", "role": "body"},
    "ibm_plex_mono": {"family": "IBM Plex Mono", "cdn": "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap", "fallback": "Consolas, monospace", "role": "body"},
    "space_mono": {"family": "Space Mono", "cdn": "https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap", "fallback": "Consolas, monospace", "role": "body"},
    "fira_code": {"family": "Fira Code", "cdn": "https://fonts.googleapis.com/css2?family=Fira+Code:wght@300;400;500;700&display=swap", "fallback": "Consolas, monospace", "role": "body"},
}

# ---------------------------------------------------------------------------
# PAIRING — setiap entri: display_font, body_font, label, rationale
# ---------------------------------------------------------------------------
PAIRINGS: list[dict[str, Any]] = [
    {
        "id": "serif-contrast",
        "label": "Serif + Sans",
        "display": "fraunces",
        "body": "satoshi",
        "rationale": "Kontras struktur: serif memegang fokus, sans menjaga keterbacaan.",
        "weights": {"display": 600, "body": 400},
        "spacing": {"display": -0.04, "body": -0.01},
        "line_height": {"display": 0.95, "body": 1.5},
    },
    {
        "id": "grotesk-clean",
        "label": "Grotesk + Sans",
        "display": "clash_display",
        "body": "general_sans",
        "rationale": "Satu keluarga sans dengan kontras bobot dan ukuran.",
        "weights": {"display": 600, "body": 400},
        "spacing": {"display": -0.05, "body": -0.01},
        "line_height": {"display": 1.0, "body": 1.45},
    },
    {
        "id": "mono-technical",
        "label": "Mono + Sans",
        "display": "space_grotesk",
        "body": "jetbrains_mono",
        "rationale": "Kesan teknikal / terminal. Mono untuk aksen, sans untuk isi.",
        "weights": {"display": 700, "body": 400},
        "spacing": {"display": -0.06, "body": 0},
        "line_height": {"display": 1.0, "body": 1.5},
    },
    {
        "id": "serif-editorial",
        "label": "Serif + Serif",
        "display": "dm_serif_display",
        "body": "lora",
        "rationale": "Satu keluarga serif, kontras ukuran dan bobot. Nuansa majalah.",
        "weights": {"display": 400, "body": 400},
        "spacing": {"display": -0.04, "body": 0},
        "line_height": {"display": 1.05, "body": 1.6},
    },
    {
        "id": "sans-brutalist",
        "label": "Brutalist Sans",
        "display": "space_grotesk",
        "body": "work_sans",
        "rationale": "Tegas, geometris, hampir tanpa embellishment. Cocok untuk statement.",
        "weights": {"display": 700, "body": 500},
        "spacing": {"display": -0.07, "body": -0.01},
        "line_height": {"display": 0.9, "body": 1.4},
    },
    {
        "id": "serif-modern",
        "label": "Modern Serif",
        "display": "canela",
        "body": "inter",
        "rationale": "Editorial modern: serif halus dengan sans netral.",
        "weights": {"display": 400, "body": 400},
        "spacing": {"display": -0.03, "body": -0.01},
        "line_height": {"display": 1.0, "body": 1.5},
    },
    {
        "id": "sans-geometric",
        "label": "Geometric Sans",
        "display": "general_sans_display",
        "body": "jakarta",
        "rationale": "Sans geometris untuk display, sans humanis untuk body.",
        "weights": {"display": 600, "body": 400},
        "spacing": {"display": -0.05, "body": -0.01},
        "line_height": {"display": 1.0, "body": 1.45},
    },
    {
        "id": "mono-classic",
        "label": "Classic Mono",
        "display": "playfair_display",
        "body": "ibm_plex_mono",
        "rationale": "Kontras tinggi: serif elegan + mono teknikal. Nuansa editorial tech.",
        "weights": {"display": 700, "body": 400},
        "spacing": {"display": -0.04, "body": 0},
        "line_height": {"display": 1.0, "body": 1.5},
    },
]

PAIRING_BY_ID = {p["id"]: p for p in PAIRINGS}
FONT_BY_ID = {k: v for k, v in FONTS.items()}


def pairing(pair_id: str) -> dict[str, Any]:
    return PAIRING_BY_ID.get(pair_id, PAIRINGS[0])


def font_stack(font_id: str) -> str:
    f = FONT_BY_ID.get(font_id)
    if not f:
        return "system-ui, sans-serif"
    return f'"{f["family"]}", {f["fallback"]}'


def font_cdn_urls() -> list[str]:
    urls = []
    for f in FONTS.values():
        u = f.get("cdn", "")
        if u and u not in urls:
            urls.append(u)
    return urls


def font_pairing_defaults(pair_id: str) -> dict[str, Any]:
    p = pairing(pair_id)
    return {
        "pairing_id": p["id"],
        "display_font": p["display"],
        "body_font": p["body"],
        "display_weight": p["weights"]["display"],
        "body_weight": p["weights"]["body"],
        "display_spacing": p["spacing"]["display"],
        "body_spacing": p["spacing"]["body"],
        "display_line_height": p["line_height"]["display"],
        "body_line_height": p["line_height"]["body"],
        "display_font_css": font_stack(p["display"]),
        "body_font_css": font_stack(p["body"]),
        "pairing_rationale": p["rationale"],
    }
