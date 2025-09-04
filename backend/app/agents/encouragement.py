# app/agents/encouragement.py
import os
import httpx
from typing import List, Dict, Optional
from ..prompts import ENCOURAGEMENT_SYSTEM


def _env():
    return (
        os.getenv("OPENAI_API_KEY"),
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )


async def encourage(
    user_text: str,
    mood: str,
    strategy: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL = _env()

    # Plain fallback when no API key
    if not OPENAI_API_KEY:
        return (
            f"I hear you. Based on your mood ({mood}), here's something small to try:\n\n{strategy}"
        )

    messages = [{"role": "system", "content": ENCOURAGEMENT_SYSTEM}]
    if history:
        messages.extend(history[-6:])
    messages.append(
        {
            "role": "user",
            "content": (
                f"User mood: {mood}\n"
                f"User message: {user_text}\n"
                f"Suggested small step: {strategy}\n\n"
                "Write a short, warm, non-clinical reply (2–4 sentences) that mirrors the user's feeling and invites the suggested step."
            ),
        }
    )

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            r = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": OPENAI_MODEL, "messages": messages, "temperature": 0.7},
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        # Critical: log the actual server response so you see the cause in the backend console
        try:
            # r may not exist if the request failed before making it
            print("⚠️ OpenAI encourage() failed:", e)
            if "r" in locals():
                print("Response text:", r.text)
        except Exception:
            pass
        # Gentle fallback so the API still responds 200 instead of 500
        return (
            f"I might be having trouble connecting right now. "
            f"Still, based on how you’re feeling ({mood}), here’s a small step to try:\n\n{strategy}"
        )
