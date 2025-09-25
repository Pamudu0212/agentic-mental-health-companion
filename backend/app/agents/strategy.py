# app/agents/strategy.py
from __future__ import annotations
import json, random, re
from typing import List, Dict, Optional, Literal, Iterable

from ..agents.safety import detect_crisis
from .resources import CATALOG, SYNONYMS, Resource

Crisis = Literal["none", "self_harm", "other_harm"]

# ----------------- micro-steps (kept) -----------------
MOOD_STEPS: Dict[str, List[str]] = {
    "joy": [
        "Notice one thing you appreciate right now",
        "Send a kind message to someone who helped you recently",
    ],
    "sadness": [
        "Drink a glass of water and take 3 slow breaths",
        "Play a gentle song and sway for one minute",
    ],
    "anger": [
        "Drop your shoulders and unclench your jaw for 30 seconds",
        "Walk away from the screen for 2 minutes and look out a window",
    ],
    "distress": [
        "Place your hand on your chest and breathe slowly for 30 seconds",
        "Look around and name 5 things you can see right now",
    ],
    "neutral": [
        "Take 3 slow breaths and notice your feet on the floor",
        "Do a 60-second tidy-up of your desk",
    ],
}

def _pick_non_repeating(
    candidates: List[str], history: Optional[List[Dict[str, str]]]
) -> str:
    if not candidates:
        return ""
    last_assistant = ""
    if history:
        for m in reversed(history):
            if m.get("role") == "assistant":
                last_assistant = (m.get("content") or "")
                break
    pool = [s for s in candidates if s[:30].lower() not in last_assistant.lower()]
    if not pool:
        pool = candidates
    return random.choice(pool)

# ----------------- text utilities -----------------
STOPWORDS = set("""
a an and the of to in for with on at by from up down over under into out about around as is are was were be been being
I you he she they we it this that these those my your his her their our me him them us
""".split())

def _tokens(text: str) -> List[str]:
    toks = re.findall(r"[a-zA-Z][a-zA-Z'-]{1,}", (text or "").lower())
    return [t for t in toks if t not in STOPWORDS]

def _bigrams(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]

def _expand_synonyms(words: Iterable[str]) -> List[str]:
    out = set(words)
    for w in list(words):
        for k, syns in SYNONYMS.items():
            if w == k or w in syns:
                out.add(k)
                out.update(syns)
    return list(out)

# ----------------- scoring -----------------
def _match_score(item: Resource, mood: str, user_text: str) -> float:
    """
    Many-words scoring:
    - mood match (2 pts)
    - keyword overlap (token/bigram) with phrase boost
    - small boost for short content (video/article)
    """
    score = 0.0
    mood = (mood or "neutral").lower()

    # mood match
    moods = set((item.get("moods") or []))
    if mood in moods:
        score += 2.0

    # user words (tokens + bigrams) + synonyms
    toks = _tokens(user_text)
    grams = set(toks + _bigrams(toks))
    expanded = set(_expand_synonyms(grams))

    # item keywords
    kws = set([k.lower() for k in (item.get("keywords") or [])])

    # overlaps
    overlap = expanded & kws
    score += len(overlap) * 0.9  # heavier weight

    # phrase bonus (bigrams)
    phrase_hits = [g for g in grams if " " in g and g in kws]
    score += len(phrase_hits) * 0.6

    # light length/type boost
    t = item.get("type")
    if t == "video":
        score += 0.4
    elif t == "article":
        score += 0.15

    return score

def _diversify(top_items: List[Resource], k: int = 3) -> List[Resource]:
    want_types = ["video", "article", "book"]
    out: List[Resource] = []
    seen = set()
    # first pass: one of each
    for t in want_types:
        for it in top_items:
            if it.get("type") == t and it["id"] not in seen:
                out.append(it); seen.add(it["id"]); break
    # second: fill remaining
    for it in top_items:
        if len(out) >= k: break
        if it["id"] not in seen:
            out.append(it); seen.add(it["id"])
    return out[:k]

# ----------------- public APIs -----------------
async def suggest_resources(
    *, mood: str, user_text: str, crisis: Crisis, history: Optional[List[Dict[str, str]]] = None,
    k: int = 3
) -> str:
    """Return 1–k curated resource options as JSON string."""
    if crisis != "none":
        return json.dumps({"options": [], "needs_clinician": True})
    if detect_crisis(user_text) != "none":
        return json.dumps({"options": [], "needs_clinician": True})

    m = (mood or "neutral").lower()
    scored = [(_match_score(it, m, user_text), it) for it in CATALOG]
    scored.sort(key=lambda x: x[0], reverse=True)

    # require some minimal relevance
    top_items = [it for s, it in scored if s > 0.9][:12]
    if not top_items:
        return json.dumps({"options": [], "needs_clinician": False})

    options = _diversify(top_items, k=max(3, min(k, 5)))
    return json.dumps({
        "options": [
            {
                "id": it["id"],
                "type": it["type"],
                "title": it["title"],
                "url": it["url"],
                "duration": it.get("duration", ""),
                "why": it.get("why", ""),
                "cautions": it.get("cautions", ""),
                "source": it.get("source", ""),
            } for it in options
        ],
        "needs_clinician": False
    })

async def suggest_strategy(
    *, mood: str, user_text: str, crisis: Crisis, history: Optional[List[Dict[str, str]]] = None
) -> str:
    """Return a tiny micro-step string."""
    if crisis != "none": return ""
    if detect_crisis(user_text) != "none": return ""
    key = (mood or "neutral").lower()
    steps = MOOD_STEPS.get(key) or MOOD_STEPS["neutral"]
    return _pick_non_repeating(steps, history)
