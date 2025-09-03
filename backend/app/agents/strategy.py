import os
import httpx
from ..prompts import STRATEGY_SYSTEM

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

async def suggest_strategy(mood: str, user_text: str) -> str:
    # Hybrid: quick rules + LLM refinement
    seed = {
        "sadness": "Try a 2-minute grounding exercise: name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.",
        "anger": "Do a 60-second box-breath: inhale 4, hold 4, exhale 4, hold 4.",
        "joy": "Savor it: write one sentence about what made you smile, then share it with a friend if you want.",
        "optimism": "Set a tiny goal for the next hour and take the smallest step toward it.",
        "neutral": "Take a 2-minute stretch break and drink a glass of water.",
    }.get(mood, "Take a 2-minute stretch break and drink a glass of water.")

    if not OPENAI_API_KEY:
        return seed

    prompt_user = (
        f"User mood: {mood}.\n"
        f"User message: {user_text}\n"
        f"Draft strategy: {seed}\n"
        "Refine this into one concise, specific, low-effort action (max 2 sentences)."
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": STRATEGY_SYSTEM},
                    {"role": "user", "content": prompt_user},
                ],
                "temperature": 0.5,
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
