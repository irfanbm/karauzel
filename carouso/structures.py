from __future__ import annotations

ROLES: dict[str, dict[str, str]] = {
    "hook": {"label": "Hook", "hint": "Cover. Stop the scroll with a specific promise or tension."},
    "problem": {"label": "Problem", "hint": "Name the pain the audience already feels."},
    "why": {"label": "Why it happens", "hint": "Explain the cause in plain words."},
    "solution": {"label": "Solution", "hint": "The core answer, stated directly."},
    "point": {"label": "Point", "hint": "One idea from the list. Specific, with a concrete example."},
    "step": {"label": "Step", "hint": "One action, in order. Start with a verb."},
    "myth": {"label": "Myth vs fact", "hint": "A common belief, then what is actually true."},
    "before": {"label": "Before", "hint": "The situation before the change."},
    "turn": {"label": "Turning point", "hint": "What changed and why."},
    "after": {"label": "After", "hint": "The result after the change, concrete."},
    "story": {"label": "Story beat", "hint": "Move the story forward one beat."},
    "lesson": {"label": "Lesson", "hint": "What the story teaches."},
    "proof": {"label": "Proof", "hint": "Evidence, a number, or an example that backs the claim."},
    "recap": {"label": "Recap", "hint": "Summarise the carousel in one glance."},
    "cta": {"label": "Call to action", "hint": "Closing slide. Tell the reader exactly what to do next."},
}

STRUCTURES: dict[str, dict[str, object]] = {
    "auto": {
        "label": "Let AI decide",
        "description": "AI picks the flow that fits the topic.",
        "start": ["hook"],
        "repeat": ["point"],
        "end": ["cta"],
    },
    "problem-solution": {
        "label": "Problem, then solution",
        "description": "Hook, the pain, why it happens, the fix, proof, CTA.",
        "start": ["hook", "problem", "why"],
        "repeat": ["solution"],
        "end": ["proof", "cta"],
    },
    "listicle": {
        "label": "List",
        "description": "Hook, one point per slide, CTA.",
        "start": ["hook"],
        "repeat": ["point"],
        "end": ["cta"],
    },
    "how-to": {
        "label": "Step by step",
        "description": "Hook, why it matters, ordered steps, CTA.",
        "start": ["hook", "why"],
        "repeat": ["step"],
        "end": ["cta"],
    },
    "myth-fact": {
        "label": "Myth vs fact",
        "description": "Hook, myths corrected one by one, CTA.",
        "start": ["hook"],
        "repeat": ["myth"],
        "end": ["recap", "cta"],
    },
    "before-after": {
        "label": "Before and after",
        "description": "Hook, before, the turning point, after, how, CTA.",
        "start": ["hook", "before", "turn", "after"],
        "repeat": ["step"],
        "end": ["cta"],
    },
    "story": {
        "label": "Story",
        "description": "Hook, story beats, the lesson, CTA.",
        "start": ["hook"],
        "repeat": ["story"],
        "end": ["lesson", "cta"],
    },
}

CTA_TYPES: dict[str, str] = {
    "save": "Save this post",
    "share": "Share with someone",
    "follow": "Follow the account",
    "comment": "Comment an answer",
    "dm": "Send a DM",
    "link": "Visit a link",
}

GOALS = ("educate", "sell", "awareness", "personal-brand", "engagement")
TONES = ("friendly", "professional", "bold", "playful", "calm")

MIN_SLIDES = 3
MAX_SLIDES = 12


def outline(structure: str, count: int) -> list[str]:
    spec = STRUCTURES.get(structure, STRUCTURES["auto"])
    count = max(MIN_SLIDES, min(MAX_SLIDES, int(count)))
    start = list(spec["start"])  # type: ignore[arg-type]
    repeat = list(spec["repeat"])  # type: ignore[arg-type]
    end = list(spec["end"])  # type: ignore[arg-type]
    while len(start) + len(end) > count and len(start) > 1:
        start.pop()
    while len(start) + len(end) > count and len(end) > 1:
        end.pop(0)
    middle = count - len(start) - len(end)
    return start + [repeat[i % len(repeat)] for i in range(middle)] + end


def catalog() -> dict[str, object]:
    return {
        "roles": ROLES,
        "structures": {key: {k: v for k, v in value.items()} for key, value in STRUCTURES.items()},
        "cta_types": CTA_TYPES,
        "goals": GOALS,
        "tones": TONES,
        "min_slides": MIN_SLIDES,
        "max_slides": MAX_SLIDES,
    }
