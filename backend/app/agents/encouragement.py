# app/agents/encouragement.py
import os
import httpx
from ..prompts import ENCOURAGEMENT_SYSTEM

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

async def encourage(user_text: str, mood: str, strategy: str) -> str:
    """
    Produce a short, empathetic message that:
    - acknowledges the user's feelings (mood),
    - normalizes them,
    - and gently nudges the chosen strategy.
    Falls back to a template if no API key is set.
    """
    # Fallback when no key / offline
    if not OPENAI_API_KEY:
        return (
            f"Thanks for sharing. It makes sense to feel {mood} after that. "
            f"Try this: {strategy} — even one minute counts. "
            f"You're in control; take it at your pace."
        )

    user_prompt = (
        f"User said: {user_text}\n"
        f"Detected mood: {mood}\n"
        f"Chosen strategy: {strategy}\n"
        "Craft an empathetic, brief response (2–3 sentences) that acknowledges feelings, "
        "normalizes, suggests the tiny step, and reinforces autonomy. Avoid clinical language."
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": ENCOURAGEMENT_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
