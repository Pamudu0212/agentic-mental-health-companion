# app/agents/strategy.py
from __future__ import annotations
import os, httpx, json, random
from typing import List, Dict, Optional, Literal
from ..agents.safety import detect_crisis

Crisis = Literal["none", "self_harm", "other_harm"]

# -----------------------------------------------------------------------------
# Config for LLM backend
# -----------------------------------------------------------------------------
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY") or ""
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM = """You are the Strategy Agent.
Goal: produce ONE tiny, low-effort, safe action the user can do now.
Constraints:
- The action MUST be safe. If user intent is harmful, do NOT suggest any action.
- Be concrete and brief (max 2 sentences).
Output ONLY valid JSON:
{"strategy": string, "needs_clinician": boolean}
"""

# -----------------------------------------------------------------------------
# Fallback static library of micro-steps
# -----------------------------------------------------------------------------
MOOD_STEPS: Dict[str, List[str]] = {
    "joy": [
        "Notice one thing you appreciate right now",
        "Send a kind message to someone who helped you recently",
        "Jot down a small win from today",
    ],
    "optimism": [
        "Write one doable task you can finish in 10 minutes",
        "Visualize the next tiny milestone and set a 20-minute timer",
        "Note one resource or person that can help your next step",
    ],
    "sadness": [
        "Drink a glass of water and take 3 slow breaths",
        "Stand up and stretch your shoulders for 60 seconds",
        "Play a gentle song and sway for one minute",
    ],
    "anger": [
        "Drop your shoulders and unclench your jaw for 30 seconds",
        "Do 10 slow exhales—longer out-breath than in-breath",
        "Walk away from the screen for 2 minutes and look out a window",
    ],
    "distress": [
        "Place your hand on your chest and breathe slowly for 30 seconds",
        "Look around and name 5 things you can see right now",
        "Rinse your face with cool water and notice the sensation",
    ],
    "neutral": [
        "Take 3 slow breaths and notice your feet on the floor",
        "Write one sentence about how you’re feeling",
        "Do a 60-second tidy-up of your desk",
    ],
}

def _pick_non_repeating(candidates: List[str], history: Optional[List[Dict[str, str]]]) -> str:
    if not candidates:
        return ""
    last_assistant = ""
    if history:
        for m in reversed(history):
            if m.get("role") == "assistant":
                last_assistant = m.get("content", "")
                break
    pool = [s for s in candidates if s[:30].lower() not in last_assistant.lower()]
    if not pool:
        pool = candidates
    return random.choice(pool)

def _history(history: Optional[List[Dict[str, str]]]) -> str:
    if not history: 
        return ""
    lines = []
    for m in history[-6:]:
        lines.append(f"{m['role']}: {m['content']}")
    return "\n".join(lines)

# -----------------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------------
async def suggest_strategy(
    *,
    mood: str,
    user_text: str,
    crisis: Crisis,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Return a tiny, safe next step. Uses LLM if configured, else local library."""
    # Hard stop if crisis flagged
    if crisis != "none":
        return ""

    # Local guard: if input text itself is unsafe
    if detect_crisis(user_text) != "none":
        return ""

    # If no API key → fallback to static library
    if not OPENAI_API_KEY:
        key = (mood or "neutral").lower()
        steps = MOOD_STEPS.get(key) or MOOD_STEPS["neutral"]
        return _pick_non_repeating(steps, history)

    # Otherwise → call LLM Strategy Agent
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

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            obj = json.loads(text)
            if obj.get("needs_clinician"):
                return ""
            return (obj.get("strategy") or "").strip()
    except Exception:
        # fallback if API fails
        key = (mood or "neutral").lower()
        steps = MOOD_STEPS.get(key) or MOOD_STEPS["neutral"]
        return _pick_non_repeating(steps, history)
