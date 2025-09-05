# app/agents/strategy.py
import os, httpx, json
from typing import List, Dict, Optional, Literal
from ..agents.safety import detect_crisis

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # or llama-3.1-70b-versatile via Groq

StrategyJSON = dict  # {"strategy": "...", "needs_clinician": bool}

SYSTEM = """You are the Strategy Agent.
Goal: produce ONE tiny, low-effort, safe action the user can do now.
Constraints:
- The action MUST be safe. If user intent is harmful, do NOT suggest any action.
- Be concrete and brief (max 2 sentences).
Output ONLY valid JSON:
{"strategy": string, "needs_clinician": boolean}
"""

def _history(history: Optional[List[Dict[str, str]]]) -> str:
    if not history: return ""
    lines = []
    for m in history[-6:]:
        lines.append(f"{m['role']}: {m['content']}")
    return "\n".join(lines)

async def suggest_strategy(
    mood: str,
    user_text: str,
    crisis: Literal["none","self_harm","other_harm"],
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    # Hard stop if crisis from gate
    if crisis != "none":
        return ""

    # Quick local guard
    if detect_crisis(user_text) != "none":
        return ""

    user_prompt = {
        "role": "user",
        "content": (
            f"User mood: {mood}\n"
            f"User text: {user_text}\n"
            f"History (last turns):\n{_history(history)}\n\n"
            "Return JSON only."
        ),
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            user_prompt,
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]

    try:
        obj: StrategyJSON = json.loads(text)
    except Exception:
        # fallback seed
        return "Take a 2-minute grounding pause: name 5 things you see, 4 touch, 3 hear, 2 smell, 1 taste."

    if obj.get("needs_clinician"):
        return ""

    return (obj.get("strategy") or "").strip()
