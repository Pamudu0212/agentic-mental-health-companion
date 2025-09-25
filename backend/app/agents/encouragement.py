# app/agents/encouragement.py
from __future__ import annotations

import os
import json
import random
from typing import List, Dict, Optional, Literal

import httpx
from ..agents.safety import detect_crisis

# Crisis types
Crisis = Literal["none", "self_harm", "other_harm"]

# -------------------
# Configuration
# -------------------
# Allow Groq or OpenAI envs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # e.g., "llama-3.1-8b-instant" on Groq

CRISIS_MESSAGE = (
    "I’m really concerned about safety here. I can’t help with anything that could put "
    "you or others at risk. Please contact local emergency services or a crisis hotline right now. "
    "If you can, reach out to someone you trust so you’re not alone."
)

# Small safe fallbacks if the LLM call fails
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

# -------------------
# Public API
# -------------------
async def encourage(
    *,
    user_text: str,
    mood: str,
    strategy: str,
    crisis: Crisis,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Produce a short supportive response that mirrors the user's feeling and naturally invites the given strategy.
    - If crisis != "none" OR safety guard triggers, return a crisis message.
    - Returns 1–3 sentences total.
    """
    # Hard safety gates
    if crisis != "none":
        return CRISIS_MESSAGE
    if detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    # Build user prompt
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

    # Call LLM with JSON output
    try:
        text = await _llm_json(messages, temperature=0.35)
        obj = json.loads(text)
        reply = (obj.get("encouragement") or "").strip()
    except Exception:
        # Fallbacks if the model call or JSON parsing fails
        if strategy:
            return (
                "I’m here with you and I hear how you’re feeling. "
                f"If it helps, you could try this small step: {strategy}"
            )
        return random.choice(FALLBACKS)

    # Post-guard the generated text
    if detect_crisis(reply) != "none":
        return CRISIS_MESSAGE

    # Keep it concise
    if len(reply.split()) > 90:
        reply = "Thanks for sharing that. What feels most present for you right now?"
    return reply


# Optional conversat
