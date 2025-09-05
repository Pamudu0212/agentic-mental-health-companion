# app/agents/strategy.py
import os, httpx
from typing import List, Dict, Optional
from ..prompts import STRATEGY_SYSTEM, CRISIS_MESSAGE_SELF, CRISIS_MESSAGE_OTHERS
from .safety import detect_crisis  # defense-in-depth

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SAFETY_GUARD = (
    "SAFETY RULES:\n"
    "- If user shows intent to harm self or others, do NOT propose any strategy. "
    "Return a short crisis support message only.\n"
    "- Never suggest actions that could escalate risk or involve violence, weapons, or self-harm."
)

def _crisis_message(kind: str) -> str:
    return CRISIS_MESSAGE_SELF if kind == "self_harm" else CRISIS_MESSAGE_OTHERS

async def suggest_strategy(
    mood: str,
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    # Extra guard
    crisis_kind = detect_crisis(user_text)
    if crisis_kind != "none":
        return _crisis_message(crisis_kind)

    # Seed if no API
    seed = {
        "sadness": "Try a 2-minute grounding exercise: name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.",
        "anger": "Do a 60-second box-breath: inhale 4, hold 4, exhale 4, hold 4.",
        "joy": "Savor it: jot one sentence about what made you smile and share it with a friend if you want.",
        "optimism": "Set a tiny goal for the next hour and take the smallest first step.",
        "neutral": "Take a 2-minute stretch and drink a glass of water.",
    }.get(mood, "Take a 2-minute stretch and drink a glass of water.")

    if not OPENAI_API_KEY:
        return seed

    messages = [
        {"role": "system", "content": f"{STRATEGY_SYSTEM}\n\n{SAFETY_GUARD}"},
    ]
    if history:
        messages.extend(history[-6:])

    messages.append({
        "role": "user",
        "content": (
            f"User mood: {mood}\n"
            f"User message: {user_text}\n"
            f"Draft strategy: {seed}\n\n"
            "Refine into ONE safe, compassionate, low-effort action (max 2 sentences). "
            "If any harm-to-self or harm-to-others intent is present, follow SAFETY RULES."
        ),
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": OPENAI_MODEL, "messages": messages, "temperature": 0.3},
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()

    # Post-generation safety check
    out_kind = detect_crisis(text)
    if out_kind != "none":
        return _crisis_message(out_kind)

    return text
