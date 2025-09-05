# app/agents/encouragement.py
import os, httpx, json
from typing import List, Dict, Optional, Literal
from ..agents.safety import detect_crisis

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # or llama-3.1-70b-versatile

SYSTEM = """You are the Encouragement Agent.
Write 2–4 warm, non-clinical sentences that mirror the user’s feeling and invite exactly the given strategy.
Rules:
- Must mention the strategy verbatim once.
- Must be safe; never normalize harm; no instructions enabling harm.
- If crisis flag is not 'none', return the crisis support message instead.
Output JSON ONLY:
{"encouragement": string}
"""

CRISIS_MESSAGE = (
    "I’m really concerned about safety here. I can’t help with anything that could put "
    "you or others at risk. Please contact local emergency services or a crisis hotline right now. "
    "If you can, reach out to someone you trust so you’re not alone."
)

def _history(history: Optional[List[Dict[str, str]]]) -> str:
    if not history: return ""
    lines = []
    for m in history[-6:]:
        lines.append(f"{m['role']}: {m['content']}")
    return "\n".join(lines)

async def encourage(
    user_text: str,
    mood: str,
    strategy: str,
    crisis: Literal["none","self_harm","other_harm"],
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    if crisis != "none":
        return CRISIS_MESSAGE

    # extra guard
    if detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    user_prompt = {
        "role": "user",
        "content": (
            f"User mood: {mood}\n"
            f"User text: {user_text}\n"
            f"Strategy to invite (must include verbatim once): {strategy}\n"
            f"Crisis: {crisis}\n"
            f"History:\n{_history(history)}\n\n"
            "Return JSON only."
        ),
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            user_prompt,
        ],
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        r = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]

    try:
        obj = json.loads(text)
        reply = (obj.get("encouragement") or "").strip()
    except Exception:
        reply = (
            "I’m here with you and I hear how you’re feeling. "
            f"If it helps, you could try this small step: {strategy}"
        )

    # post-guard
    if detect_crisis(reply) != "none":
        return CRISIS_MESSAGE
    return reply
