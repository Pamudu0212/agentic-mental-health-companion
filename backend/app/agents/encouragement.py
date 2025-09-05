# app/agents/encouragement.py
from __future__ import annotations
from typing import Optional, List, Dict, Literal
import os, random, httpx

from ..prompts import ENCOURAGEMENT_SYSTEM

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

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")

async def _chat(messages: list[dict], temperature=0.6, top_p=0.9, timeout=18.0) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
    body = {"model": OPENAI_MODEL, "messages": messages, "temperature": temperature, "top_p": top_p}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                              headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

# ----------------------------
# New: conversation-only mode
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

    sys = (
        "You are a warm, non-clinical companion. Respond in 1–2 short sentences. "
        "First reflect/validate the user's feeling. Then ask ONE open, gentle question to learn more. "
        "No advice, no coping steps, no lists, no emojis."
    )
    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"User said: {user_text}\nMood guess: {mood or 'neutral'}\nWrite the reply."},
    ]
    try:
        out = await _chat(messages, temperature=0.6, top_p=0.9)
        # keep very short
        if len(out.split()) > 70:
            out = "Thanks for sharing that. What feels most present for you right now?"
        return out.strip()
    except Exception:
        return random.choice(FALLBACKS)

# ----------------------------
# (Optional) step-style helper
# ----------------------------
async def encourage(
    *, user_text: str, mood: str, strategy: str, history: Optional[List[Dict[str, str]]], crisis: Crisis = "none"
) -> str:
    """
    Legacy function for step-style encouragement (kept for compatibility).
    If you call this, include a `strategy` sentence to weave in; otherwise it's a
    short supportive line.
    """
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
        out = await _chat(messages, temperature=0.5, top_p=0.9)
        return out.strip()
    except Exception:
        if strategy:
            return f"Thanks for sharing that. One tiny next step: {strategy}"
        return random.choice(FALLBACKS)
