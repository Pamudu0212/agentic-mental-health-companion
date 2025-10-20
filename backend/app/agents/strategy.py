# app/agents/strategy.py
from __future__ import annotations

import json
import random
import re
from typing import List, Dict, Optional, Literal, Iterable, Set

from ..agents.safety import detect_crisis
from .resources import CATALOG, SYNONYMS, Resource
from .skillcards import retrieve_skill_cards  # <-- use IR retriever

Crisis = Literal["none", "self_harm", "other_harm"]

# Government crisis resource (Sri Lanka – NIMH 1926)
SRI_LANKA_CRISIS_URL = "https://nimh.health.gov.lk/en/1926-national-mental-health-helpline/"

# ----------------- tiny util -----------------
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

# ----------------- text utilities (for external resources) -----------------
STOPWORDS = set(
    (
        "a an and the of to in for with on at by from up down over under into out about around as "
        "is are was were be been being i you he she they we it this that these those my your his "
        "her their our me him them us"
    ).split()
)

def _tokens(text: str) -> List[str]:
    toks = re.findall(r"[a-zA-Z][a-zA-Z'-]{1,}", (text or "").lower())
    return [t for t in toks if t not in STOPWORDS]

def _bigrams(tokens: List[str]) -> List[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]

def _expand_synonyms(words: Iterable[str]) -> Set[str]:
    out: Set[str] = set(words)
    for w in list(words):
        for k, syns in SYNONYMS.items():
            if w == k or w in syns:
                out.add(k)
                out.update(syns)
    return out

def _kw_weights(item: Resource) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for raw in (item.get("keywords") or []):
        s = raw.lower().strip()
        if ":" in s:
            term, w = s.split(":", 1)
            try:
                out[term.strip()] = float(w.strip())
            except Exception:
                out[term.strip()] = 1.0
        else:
            out[s] = 1.0
    return out

def _light_fuzzy_hit(q: str, k: str) -> bool:
    if k in q or q in k:
        return True
    if len(q) >= 5 and len(k) >= 5 and abs(len(q) - len(k)) <= 1:
        mismatches = sum(1 for a, b in zip(q, k) if a != b) + abs(len(q) - len(k))
        return mismatches <= 1
    return False

# ----------------- scoring + diversification for external resources -----------------
def _match_score(item: Resource, mood: str, user_text: str) -> float:
    score = 0.0
    mood = (mood or "neutral").lower()

    if mood in set(item.get("moods") or []):
        score += 2.0

    toks = _tokens(user_text)
    grams = _bigrams(toks)
    q_terms = set(toks + grams)
    q_terms |= _expand_synonyms(q_terms)

    title_terms = set(_tokens(item.get("title", "")))
    kws = _kw_weights(item)
    kw_terms = set(kws.keys())

    for term in (q_terms & kw_terms):
        score += 0.9 * kws.get(term, 1.0)

    for big in [g for g in q_terms if " " in g]:
        if big in kw_terms:
            score += 0.6 * kws.get(big, 1.0)

    for qt in q_terms:
        if any(_light_fuzzy_hit(qt, kt) for kt in kw_terms) or any(
            _light_fuzzy_hit(qt, tt) for tt in title_terms
        ):
            score += 0.15
            break

    t = item.get("type")
    if t == "video":
        score += 0.35
    elif t == "article":
        score += 0.15

    return score

def _diversify(top_items: List[Resource], k: int = 3, exclude_ids: Set[str] | None = None) -> List[Resource]:
    want_types = ["video", "article", "book"]
    out: List[Resource] = []
    seen = set(exclude_ids or [])

    for t in want_types:
        for it in top_items:
            if it["id"] in seen:
                continue
            if it.get("type") == t:
                out.append(it)
                seen.add(it["id"])
                break

    for it in top_items:
        if len(out) >= k:
            break
        if it["id"] not in seen:
            out.append(it)
            seen.add(it["id"])
    return out[:k]

# ----------------- public APIs -----------------
async def suggest_resources(
    *,
    mood: str,
    user_text: str,
    crisis: Crisis,
    history: Optional[List[Dict[str, str]]] = None,
    k: int = 3,
    exclude_ids: Optional[List[str]] = None,
) -> str:
    """Return 1–k curated external resource options as JSON string."""
    # crisis → return ONLY the gov link (no options)
    if crisis != "none" or detect_crisis(user_text) != "none":
        return json.dumps(
            {"options": [], "needs_clinician": True, "crisis_link": SRI_LANKA_CRISIS_URL}
        )

    m = (mood or "neutral").lower()
    scored = [(_match_score(it, m, user_text), it) for it in CATALOG]
    scored.sort(key=lambda x: x[0], reverse=True)

    top_items = [it for s, it in scored if s > 0.9][:18]
    if not top_items:
        return json.dumps({"options": [], "needs_clinician": False})

    options = _diversify(top_items, k=max(3, min(k, 5)), exclude_ids=set(exclude_ids or []))

    return json.dumps(
        {
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
                }
                for it in options
            ],
            "needs_clinician": False,
        }
    )

async def suggest_strategy(
    *,
    mood: str,
    user_text: str,
    crisis: Crisis,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Return one micro-step string selected from SKILL_CARDS (via retrieve_skill_cards),
    avoiding immediate repetition. Suppress output in crisis.
    """
    if crisis != "none" or detect_crisis(user_text) != "none":
        return ""

    cards = retrieve_skill_cards(user_text=user_text, mood=mood, history=history, k=3)
    steps = [c.get("step", "").strip() for c in cards if c.get("step")]
    return _pick_non_repeating(steps, history)
