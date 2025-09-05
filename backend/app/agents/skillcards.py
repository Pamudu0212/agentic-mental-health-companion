# app/agents/skillcards.py
from __future__ import annotations
import re
from typing import List, Dict, Optional

SKILL_CARDS: List[Dict[str, str]] = [
    {"tag": "breathing",     "label": "Box Breathing (1 min)",
     "step": "Inhale 4, hold 4, exhale 4, hold 4 — repeat 4 times."},
    {"tag": "grounding",     "label": "5–4–3–2–1 Grounding",
     "step": "Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste."},
    {"tag": "hydrate",       "label": "Hydration reset",
     "step": "Drink a glass of water and notice the temperature for a few sips."},
    {"tag": "stretch",       "label": "Shoulder release",
     "step": "Unclench your jaw and roll your shoulders slowly for 60 seconds."},
    {"tag": "microtask",     "label": "2-minute start",
     "step": "Pick a 2-minute task and start it badly—momentum matters."},
    {"tag": "exam",          "label": "10-minute focus",
     "step": "Set a 10-minute timer and review just one small section."},
    {"tag": "relationship",  "label": "Soften & pause",
     "step": "Step away for 2 minutes, breathe, then write one need in one sentence."},
    {"tag": "sleep",         "label": "Dim & breathe",
     "step": "Dim your screen and take 5 slow breaths before the next step."},
    {"tag": "walk",          "label": "Window / step away",
     "step": "Look out a window or walk for 2 minutes and notice 3 details."},
]

CATEGORY_PATTERNS = {
    "exam": r"\b(exam|midterm|final|study|assignment|test)\b",
    "relationship": r"\b(gf|bf|partner|boyfriend|girlfriend|relationship|break ?up|argu(?:e|ment))\b",
    "anxiety": r"\b(panic|anxious|anxiety|racing|tight|overwhelm)\b",
    "lonely": r"\b(lonely|alone|isolat|flat|numb|empty)\b",
    "sleep": r"\b(sleep|insomnia|tired|exhausted)\b",
    "motivation": r"\b(procrastinat|motivat|putting off|can.?t start)\b",
    "anger": r"\b(angry|furious|rage|pissed|mad)\b",
}

CATEGORY_TO_TAGS = {
    "exam": ["exam", "hydrate", "stretch"],
    "relationship": ["relationship", "breathing", "walk"],
    "anxiety": ["breathing", "grounding", "walk"],
    "lonely": ["walk", "hydrate", "microtask"],
    "sleep": ["sleep", "breathing"],
    "motivation": ["microtask", "hydrate"],
    "anger": ["stretch", "walk", "breathing"],
}

MOOD_TO_TAGS = {
    "sadness": ["grounding", "walk"],
    "distress": ["breathing", "grounding"],
    "anger": ["stretch", "walk"],
    "joy": ["microtask", "walk"],
    "optimism": ["microtask", "exam"],
    "neutral": ["grounding", "microtask"],
}

def _last_tag_from_history(history: Optional[List[Dict[str, str]]]) -> Optional[str]:
    """Try to infer which card tag we suggested last, by matching known steps."""
    if not history:
        return None
    for m in reversed(history):
        if m.get("role") != "assistant":
            continue
        content = (m.get("content") or "").lower()
        for c in SKILL_CARDS:
            if c["step"].lower() in content:
                return c["tag"]
    return None

def retrieve_skill_cards(
    user_text: str,
    mood: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    k: int = 3,
) -> List[Dict[str, str]]:
    """Choose up to k skill cards based on category + mood, avoiding the last tag."""
    t = user_text.lower()
    hits = [cat for cat, pat in CATEGORY_PATTERNS.items() if re.search(pat, t)]
    tags: List[str] = []

    # category-based first
    for h in hits:
        tags += CATEGORY_TO_TAGS.get(h, [])

    # then mood-based preferences
    if mood:
        tags += MOOD_TO_TAGS.get(mood.lower(), [])

    # default pool if nothing matched
    if not tags:
        tags = ["grounding", "microtask", "walk", "hydrate", "stretch", "breathing"]

    # avoid immediate repetition of last suggestion
    last_tag = _last_tag_from_history(history)
    if last_tag in tags:
        tags = [tg for tg in tags if tg != last_tag] + [last_tag]  # push last to end

    # materialize into cards in order, dedup by tag
    seen, cards = set(), []
    for tag in tags:
        for c in SKILL_CARDS:
            if c["tag"] == tag and c["tag"] not in seen:
                cards.append(c)
                seen.add(c["tag"])
                if len(cards) >= k:
                    return cards

    # pad if needed
    for c in SKILL_CARDS:
        if c["tag"] not in seen:
            cards.append(c)
            seen.add(c["tag"])
            if len(cards) >= k:
                break
    return cards
