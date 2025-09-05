# app/agents/encouragement.py
from __future__ import annotations
from typing import Optional, List, Dict, Literal
import random, re

from ..prompts import ENCOURAGEMENT_SYSTEM
from ..llm_router import chat_completions  # ← per-agent router

Crisis = Literal["none", "self_harm", "other_harm"]

CRISIS_MESSAGE = (
    "I’m really concerned about safety here. I can’t help with anything that could put "
    "you or others at risk. Please contact local emergency services or a crisis hotline right now. "
    "If you can, reach out to someone you trust so you’re not alone."
)

# --------- Small safe fallbacks (used if LLM call fails) ----------
FALLBACKS = [
    "Thanks for saying that. What feels most present for you right now?",
    "I’m listening. Could you say a little more about what’s hard in this moment?",
    "That makes sense. What do you notice in your body or thoughts right now?",
]

# words that imply unsolicited “advice” (avoid in conversation mode)
ADVICE_HINTS = (
    "try ", "you could", "do this", "do that", "step", "exercise", "breathing",
    "box breathing", "grounding", "timer", "stretch", "walk for", "count", "inhale",
)

def _score_candidate(text: str, user_text: str) -> int:
    """Small rubric: open question + empathy + short + mirrors user keyword + no advice."""
    t = text.lower()
    score = 0
    if "?" in t: score += 1
    if any(w in t for w in ("sounds", "seems", "makes sense", "thanks for", "i hear", "i’m here")): score += 1
    if not any(h in t for h in ADVICE_HINTS): score += 1
    if len(text.split()) <= 45: score += 1
    kws = re.findall(r"[a-zA-Z]{4,}", (user_text or "").lower())
    if kws and any(k in t for k in kws[:3]): score += 1
    return score

async def _candidate(user_text: str, mood: str, temp: float) -> str:
    sys = (
        "You are a warm, non-clinical companion. "
        "Write 1–2 short sentences. First reflect/validate what the user seems to feel; "
        "then ask ONE open, gentle question to learn more. Avoid advice/steps, lists, or emojis."
    )
    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"User: {user_text}\nMood guess: {mood or 'neutral'}\nReply:"},
    ]
    data = await chat_completions("ENCOURAGEMENT", messages, temperature=temp, top_p=0.9)
    return (data["choices"][0]["message"]["content"] or "").strip()

# ----------------------------
# Conversation-only mode
# ----------------------------
async def converse(
    *, user_text: str, mood: str, history: Optional[List[Dict[str, str]]], crisis: Crisis = "none"
) -> str:
    """
    Produce a therapist-like reply: brief reflection + ONE open, gentle question.
    No coping steps, no lists, no emojis.
    """
    if crisis != "none":
        return CRISIS_MESSAGE

    # generate a few variants and choose the best
    temps = (0.65, 0.85, 0.6)
    candidates = []
    for t in temps:
        try:
            candidates.append(await _candidate(user_text, mood, t))
        except Exception:
            continue

    if not candidates:
        return random.choice(FALLBACKS)

    best = max(candidates, key=lambda s: _score_candidate(s, user_text))
    if len(best.split()) > 60:
        best = "Thanks for sharing that. What feels most present for you right now?"
    return best

# ----------------------------
# (Optional) step-style helper (kept for compatibility)
# ----------------------------
async def encourage(
    *, user_text: str, mood: str, strategy: str, history: Optional[List[Dict[str, str]]], crisis: Crisis = "none"
) -> str:
    if crisis != "none":
        return CRISIS_MESSAGE

    prompt = (
        f"{ENCOURAGEMENT_SYSTEM}\n\n"
        f"User: {user_text}\n"
        f"Mood guess: {mood or 'neutral'}\n"
        f"Suggested tiny step (optional): {strategy or '(none)'}\n\n"
        "Write 1–2 short sentences. If a step is provided and sensible, include it in natural language."
    )
    messages = [{"role": "system", "content": ENCOURAGEMENT_SYSTEM},
                {"role": "user", "content": prompt}]
    try:
        data = await chat_completions("ENCOURAGEMENT", messages, temperature=0.5, top_p=0.9)
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        if strategy:
            return f"Thanks for sharing that. One tiny next step: {strategy}"
        return random.choice(FALLBACKS)
