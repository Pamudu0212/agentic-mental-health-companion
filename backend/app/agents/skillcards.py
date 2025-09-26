# app/agents/skillcards.py
from __future__ import annotations
import math
import re
from typing import List, Dict, Optional

# ------------------------------------------------------------------
# Fallback content (used only if DB is empty/unavailable)
# ------------------------------------------------------------------
FALLBACK_CARDS: List[Dict[str, str]] = [
    {"tag": "breathing", "label": "Box Breathing (1 min)",
     "step": "Inhale 4, hold 4, exhale 4, hold 4 — repeat 4 times."},
    {"tag": "grounding", "label": "5–4–3–2–1 Grounding",
     "step": "Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste."},
    {"tag": "hydrate", "label": "Hydration reset",
     "step": "Drink a glass of water and notice the temperature for a few sips."},
    {"tag": "stretch", "label": "Shoulder release",
     "step": "Unclench your jaw and roll your shoulders slowly for 60 seconds."},
    {"tag": "microtask", "label": "2-minute start",
     "step": "Pick a 2-minute task and start it badly—momentum matters."},
    {"tag": "exam", "label": "10-minute focus",
     "step": "Set a 10-minute timer and review just one small section."},
    {"tag": "relationship", "label": "Soften & pause",
     "step": "Step away for 2 minutes, breathe, then write one need in one sentence."},
    {"tag": "sleep", "label": "Dim & breathe",
     "step": "Dim your screen and take 5 slow breaths before the next step."},
    {"tag": "walk", "label": "Window / step away",
     "step": "Look out a window or walk for 2 minutes and notice 3 details."},
]

# ------------------------------------------------------------------
# Category routing (regex → preferred tags)
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# DB access
# ------------------------------------------------------------------
from sqlalchemy.orm import Session
from ..db import engine
from ..models import Strategy

def _fetch_db_cards() -> List[Dict[str, str]]:
    """
    Read strategies from mh_strategies and normalize fields.
    Returns [{tag,label,step,why,keywords[],moods[],source_name,source_url}, ...]
    """
    try:
        with Session(engine) as session:
            rows = session.query(
                Strategy.tag,
                Strategy.label,
                Strategy.step,
                Strategy.why,
                Strategy.keywords,
                Strategy.moods,
                Strategy.language,
                Strategy.source_name,
                Strategy.source_url,
            ).all()

        out: List[Dict[str, str]] = []
        for tag, label, step, why, keywords, moods, lang, source_name, source_url in rows:
            if lang and lang.lower() not in ("", "en"):
                continue
            out.append({
                "tag": (tag or "").strip().lower(),
                "label": (label or "").strip(),
                "step": (step or "").strip(),
                "why": (why or "").strip(),
                "keywords": [t.strip().lower() for t in (keywords or "").split(",") if t.strip()],
                "moods": [t.strip().lower() for t in (moods or "").split(",") if t.strip()],
                "source_name": (source_name or "").strip(),
                "source_url": (source_url or "").strip(),
            })
        return out
    except Exception:
        # If DB is unavailable for any reason, we’ll fall back gracefully.
        return []

# ------------------------------------------------------------------
# IR primitives (BM25-lite + keywords + mood + category mix)
# ------------------------------------------------------------------
_WORD = re.compile(r"[a-zA-Z][a-zA-Z'-]{1,}")
def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _WORD.findall(text or "")]

_INDEX: List[Dict] = []          # per-card doc with precomputed fields
_VOCAB_DF: Dict[str, int] = {}
_N_DOCS = 0
_DB_SNAPSHOT: List[Dict] | None = None  # cached DB rows used to build the index

def _add_df(terms: set[str]):
    for t in terms:
        _VOCAB_DF[t] = _VOCAB_DF.get(t, 0) + 1

def _idf(term: str) -> float:
    df = _VOCAB_DF.get(term, 0) or 1
    return math.log(1 + (_N_DOCS - df + 0.5) / (df + 0.5))

def _ensure_index_built():
    """
    Build index from DB rows if available; otherwise from FALLBACK_CARDS.
    """
    global _INDEX, _VOCAB_DF, _N_DOCS, _DB_SNAPSHOT
    if _INDEX:
        return

    # Load DB
    _DB_SNAPSHOT = _fetch_db_cards()
    source = _DB_SNAPSHOT if _DB_SNAPSHOT else FALLBACK_CARDS

    # Provide light defaults when DB rows lack keywords/moods
    DEFAULTS = {
        "breathing": (["anxiety","panic","breath","inhale","exhale","calm"], ["distress","anger","sadness","neutral"]),
        "grounding": (["ground","present","overthink","panic","dissociate"], ["distress","sadness","neutral"]),
        "hydrate":   (["hydrate","water","tired","headache"], ["sadness","neutral"]),
        "stretch":   (["tense","tight","jaw","shoulder","anger"], ["anger","distress","neutral"]),
        "microtask": (["stuck","procrastinate","motivation","start","avoid"], ["neutral","sadness","joy"]),
        "exam":      (["exam","study","assignment","test","deadline"], ["neutral","optimism","sadness"]),
        "relationship": (["relationship","argument","fight","partner","breakup"], ["anger","distress","sadness"]),
        "sleep":     (["sleep","insomnia","tired","exhausted"], ["sadness","neutral"]),
        "walk":      (["walk","outside","window","restless","stuck"], ["anger","sadness","neutral","joy"]),
    }

    _INDEX, _VOCAB_DF, _N_DOCS = [], {}, 0
    for c in source:
        tag = c.get("tag", "")
        label = c.get("label", "")
        step = c.get("step", "")
        why = c.get("why", "") or ""
        kws = c.get("keywords") or DEFAULTS.get(tag, ([], []))[0]
        moods = c.get("moods") or DEFAULTS.get(tag, ([], []))[1]
        source_name = c.get("source_name", "")
        source_url = c.get("source_url", "")

        text = " ".join([label, step, why, " ".join(kws)])
        terms = set(_tokens(text))
        _add_df(terms)

        _INDEX.append({
            "tag": tag,
            "label": label,
            "step": step,
            "why": why,
            "keywords": [k.lower() for k in kws],
            "moods": [m.lower() for m in moods],
            "text_terms": terms,
            "source_name": source_name,
            "source_url": source_url,
        })
    _N_DOCS = len(_INDEX)

def _score(doc: Dict, mood: str, q_terms: List[str], category_tags: List[str]) -> float:
    score = 0.0
    # mood boost
    if mood and mood in doc["moods"]:
        score += 2.0
    # category routing
    if doc["tag"] in set(category_tags):
        score += 1.2
    # author keywords
    kw = set(doc["keywords"])
    for t in q_terms:
        if t in kw:
            score += 0.9
    # BM25-lite overlap
    for t in q_terms:
        if t in doc["text_terms"]:
            score += 0.5 * _idf(t)
    return score

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _last_tag_from_history(history: Optional[List[Dict[str, str]]]) -> Optional[str]:
    if not history:
        return None
    for m in reversed(history):
        if m.get("role") != "assistant":
            continue
        content = (m.get("content") or "").lower()
        for d in _INDEX:
            if d["step"].lower() in content:
                return d["tag"]
    return None

# ------------------------------------------------------------------
# Public API (DB-backed)
# ------------------------------------------------------------------
def rank_strategies_from_db(
    *,
    user_text: str,
    mood: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    k: int = 3,
) -> List[Dict[str, str]]:
    """
    Rank strategies (DB first, fallback if needed) by:
    mood boost + category routing + author keywords + BM25-lite.
    Avoids immediate repetition from history. Returns up to k items:
    [{tag, label, step, why}]
    """
    _ensure_index_built()

    t = (user_text or "").lower()
    q_terms = _tokens(t)
    mood = (mood or "neutral").lower()

    # Category routing
    hits = [cat for cat, pat in CATEGORY_PATTERNS.items() if re.search(pat, t)]
    category_tags: List[str] = []
    for h in hits:
        category_tags += CATEGORY_TO_TAGS.get(h, [])

    ranked = sorted(
        _INDEX,
        key=lambda d: _score(d, mood, q_terms, category_tags),
        reverse=True,
    )

    last_tag = _last_tag_from_history(history)
    out: List[Dict[str, str]] = []
    seen = set()
    for d in ranked:
        if d["tag"] == last_tag:
            continue
        if d["tag"] in seen:
            continue
        out.append({
            "tag": d["tag"],
            "label": d["label"],
            "step": d["step"],
            "why": d.get("why", ""),
        })
        seen.add(d["tag"])
        if len(out) >= k:
            break

    if len(out) < k and last_tag:
        for d in ranked:
            if d["tag"] == last_tag and d["tag"] not in seen:
                out.append({"tag": d["tag"], "label": d["label"], "step": d["step"], "why": d.get("why", "")})
                break

    if len(out) < k:
        for c in FALLBACK_CARDS:
            if c["tag"] not in seen:
                out.append({"tag": c["tag"], "label": c["label"], "step": c["step"], "why": ""})
                seen.add(c["tag"])
                if len(out) >= k:
                    break
    return out

def best_strategy_step(
    *,
    user_text: str,
    mood: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Convenience helper: return only the step text of the top strategy,
    or "" if nothing ranked.
    """
    ranked = rank_strategies_from_db(user_text=user_text, mood=mood, history=history, k=1)
    return ranked[0]["step"] if ranked else ""

def best_strategy_entry(
    *,
    user_text: str,
    mood: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> Optional[Dict[str, str]]:
    """
    Return the best single entry with source metadata:
    {tag,label,step,source_name,source_url}
    """
    _ensure_index_built()
    ranked = rank_strategies_from_db(user_text=user_text, mood=mood, history=history, k=1)
    if not ranked:
        return None

    # Find full record (for source fields)
    tag = ranked[0]["tag"]
    label = ranked[0]["label"]
    for d in _INDEX:
        if d["tag"] == tag and d["label"] == label:
            return {
                "tag": d["tag"],
                "label": d["label"],
                "step": d["step"],
                "source_name": d.get("source_name", ""),
                "source_url": d.get("source_url", ""),
            }

    # Fallback without source (unlikely)
    r = ranked[0]
    return {"tag": r["tag"], "label": r["label"], "step": r["step"], "source_name": "", "source_url": ""}

# ------------------------------------------------------------------
# Backwards-compat shim (kept for older call sites)
# ------------------------------------------------------------------
def retrieve_skill_cards(
    user_text: str,
    mood: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    k: int = 3,
) -> List[Dict[str, str]]:
    """Alias to DB-backed ranker."""
    return rank_strategies_from_db(user_text=user_text, mood=mood, history=history, k=k)
