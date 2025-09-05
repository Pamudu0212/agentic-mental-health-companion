from __future__ import annotations
from typing import Optional, List, Dict, Literal
import random

Crisis = Literal["none", "self_harm", "other_harm"]

# Mood → micro-step library (short, actionable, low-risk).
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

async def suggest_strategy(
    *, mood: str, user_text: str, history: Optional[List[Dict[str, str]]], crisis: Crisis = "none"
) -> str:
    """Return a tiny, safe next step. Empty string if in crisis."""
    if crisis != "none":
        return ""
    key = (mood or "neutral").lower()
    steps = MOOD_STEPS.get(key) or MOOD_STEPS["neutral"]
    return _pick_non_repeating(steps, history)
