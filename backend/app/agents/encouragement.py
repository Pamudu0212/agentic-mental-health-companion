# app/agents/encouragement.py
from __future__ import annotations

import os
import json
import random
import re
from typing import List, Dict, Optional, Literal

import httpx

from ..prompts import ENCOURAGEMENT_SYSTEM  # kept (even if unused by default)
from ..llm_router import chat_completions    # per-agent router for small variants
from ..agents.safety import detect_crisis

# -------------------
# Types
# -------------------
Crisis = Literal["none", "self_harm", "other_harm"]

# -------------------
# Configuration
# -------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # e.g., "llama-3.1-8b-instant" on Groq

CRISIS_MESSAGE = (
    "I’m really concerned about safety here. I can’t help with anything that could put "
    "you or others at risk. Please contact local emergency services or a crisis hotline right now. "
    "If you can, reach out to someone you trust so you’re not alone."
)

FALLBACKS = [
    "Thanks for saying that. What feels most present for you right now?",
    "I’m listening. Could you say a little more about what’s hard in this moment?",
    "That makes sense. What do you notice in your body or thoughts right now?",
]

SYSTEM = """You are the Encouragement Agent.
Write 2–4 warm, non-clinical sentences that mirror the user’s feeling and invite exactly the given strategy.
Rules:
- Mention the strategy verbatim exactly once (if provided and safe).
- Be safe; never normalize harm; no instructions enabling harm.
- If crisis flag is not 'none', return the crisis support message instead.
Output JSON ONLY:
{"encouragement": string}
"""

# Advice-like words to avoid in conversation mode
ADVICE_HINTS = (
    "try ", "you could", "do this", "do that", "step", "exercise", "breathing",
    "box breathing", "grounding", "timer", "stretch", "walk for", "count", "inhale",
)

# -------------------
# Helpers
# -------------------
def _history(history: Optional[List[Dict[str, str]]]) -> str:
    """Render recent turns for context (last 6)."""
    if not history:
        return ""
    lines = []
    for m in history[-6:]:
        role = m.get("role", "")
        content = m.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)

async def _llm_json(messages: List[Dict[str, str]], temperature: float = 0.35, timeout: float = 40.0) -> str:
    """Call the Chat Completions API with JSON response_format and return the raw text."""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

def _score_candidate(text: str, user_text: str) -> int:
    """Small rubric: open question + empathy + short + mirrors user keyword + no advice."""
    t = text.lower()
    score = 0
    if "?" in t:
        score += 1
    if any(w in t for w in ("sounds", "seems", "makes sense", "thanks for", "i hear", "i’m here")):
        score += 1
    if not any(h in t for h in ADVICE_HINTS):
        score += 1
    if len(text.split()) <= 45:
        score += 1
    kws = re.findall(r"[a-zA-Z]{4,}", (user_text or "").lower())
    if kws and any(k in t for k in kws[:3]):
        score += 1
    return score

async def _candidate(user_text: str, mood: str, temp: float) -> str:
    """Generate a single short reflective response with one open gentle question."""
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
# JSON variant used by some flows
# ----------------------------
async def encourage_json(
    *,
    user_text: str,
    mood: str,
    strategy: str,
    crisis: Crisis,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.35,
) -> str:
    """
    Produce a short supportive response that mirrors the user's feeling and naturally invites the given strategy.
    Returns plain **text** (extracted from the JSON "encouragement" field).
    """
    # Safety gates
    if crisis != "none":
        return CRISIS_MESSAGE
    if detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    user_prompt = {
        "role": "user",
        "content": (
            f"User mood: {mood or 'neutral'}\n"
            f"User text: {user_text}\n"
            f"Strategy to invite (must include verbatim once if sensible): {strategy or '(none)'}\n"
            f"Crisis: {crisis}\n"
            f"History:\n{_history(history)}\n\n"
            "Return JSON only."
        ),
    }
    messages = [
        {"role": "system", "content": SYSTEM},
        user_prompt,
    ]

    try:
        text = await _llm_json(messages, temperature=temperature)
        obj = json.loads(text)
        reply = (obj.get("encouragement") or "").strip()
    except Exception:
        if strategy:
            return (
                "I’m here with you and I hear how you’re feeling. "
                f"If it helps, you could try this small step: {strategy}"
            )
        return random.choice(FALLBACKS)

    if detect_crisis(reply) != "none":
        return CRISIS_MESSAGE

    # Keep concise
    if len(reply.split()) > 90:
        reply = "Thanks for sharing that. What feels most present for you right now?"
    return reply

# ----------------------------
# Conversation mode (no strategy; 1–2 sentences)
# ----------------------------
async def converse(
    *,
    user_text: str,
    mood: str,
    history: Optional[List[Dict[str, str]]] = None,
    crisis: Crisis = "none",
) -> str:
    """
    Produce 1–2 sentences: reflect the feeling + ask one gentle open question.
    No coping steps, no lists, no emojis.
    """
    if crisis != "none" or detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    temps = (0.65, 0.85, 0.6)
    candidates: List[str] = []
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
# Strategy-inviting helper (plain text)
# ----------------------------
async def encourage(
    *,
    user_text: str,
    mood: str,
    strategy: str,
    history: Optional[List[Dict[str, str]]] = None,
    crisis: Crisis = "none",
) -> str:
    """
    Reflect + gently invite a concrete strategy once. 1–3 sentences total.
    Uses the JSON system prompt under the hood, returns plain text.
    """
    if crisis != "none" or detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    # Prefer the JSON-governed path for exact strategy inclusion; then post-trim
    reply = await encourage_json(
        user_text=user_text,
        mood=mood,
        strategy=strategy,
        crisis=crisis,
        history=history,
        temperature=0.35,
    )

    if len(reply.split()) > 90:
        reply = "Thanks for sharing that. What feels most present for you right now?"
    return reply
