# app/agents/encouragement.py
import os, httpx
from typing import List, Dict, Optional
from ..prompts import ENCOURAGEMENT_SYSTEM, CRISIS_MESSAGE_SELF, CRISIS_MESSAGE_OTHERS
from .safety import detect_crisis  # defense-in-depth check

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SAFETY_GUARD = (
    "SAFETY RULES:\n"
    "- If the user expresses intent to harm themselves or others (even implicitly), "
    "do NOT encourage or normalize it. Do NOT provide instructions. "
    "Respond ONLY with a brief crisis support message urging immediate professional help. "
    "- Avoid praise or positive framing for harmful or violent content."
)

def _crisis_message(kind: str) -> str:
    return CRISIS_MESSAGE_SELF if kind == "self_harm" else CRISIS_MESSAGE_OTHERS

async def encourage(
    user_text: str,
    mood: str,
    strategy: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Safe encouragement generator. If anything looks dangerous, we return a crisis message.
    """
    # Extra guard in case orchestrator missed something
    crisis_kind = detect_crisis(user_text)
    if crisis_kind != "none":
        return _crisis_message(crisis_kind)

    if not OPENAI_API_KEY:
        # Very safe fallback
        return (
            f"I’m here with you. Since you’re feeling {mood}, a small, gentle next step could be:\n\n{strategy}\n\n"
            "Only do what feels safe and manageable right now."
        )

    # Build messages with a strict safety system
    messages = [
        {"role": "system", "content": f"{ENCOURAGEMENT_SYSTEM}\n\n{SAFETY_GUARD}"},
    ]
    if history:
        messages.extend(history[-6:])  # short context

    messages.append({
        "role": "user",
        "content": (
            f"User mood: {mood}\n"
            f"User message: {user_text}\n"
            f"Suggested small step: {strategy}\n\n"
            "Write a short (2–4 sentences), warm, non-clinical reply that mirrors the user's feeling "
            "and invites the suggested step. Be gentle and concrete. "
            "If any harm-to-self or harm-to-others is present, follow SAFETY RULES."
        ),
    })

    async with httpx.AsyncClient(timeout=40.0) as client:
        r = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": OPENAI_MODEL, "messages": messages, "temperature": 0.4},
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()

    # Post-generation safety check (defense-in-depth)
    out_kind = detect_crisis(text)
    if out_kind != "none":
        return _crisis_message(out_kind)

    return text
