# app/orchestrator.py
from __future__ import annotations
from typing import List, Dict, Optional

from .agents.mood import detect_mood
from .agents.safety import detect_crisis
from .agents.strategy import suggest_strategy
from .agents.encouragement import encourage
from .prompts import CRISIS_MESSAGE


async def run_pipeline(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,  # NEW: optional history
):
    """
    Orchestrates: safety -> mood -> strategy -> encouragement.
    `history` is a short list of prior chat turns ({role, content}), may be None.
    """

    # 1) Safety first
    if detect_crisis(user_text):
        return {
            "mood": "unknown",
            "strategy": "",
            "encouragement": CRISIS_MESSAGE,
            "crisis_detected": True,
        }

    # 2) Mood
    mood = detect_mood(user_text)

    # 3) Strategy (pass history through, even if the agent ignores it)
    strategy = await suggest_strategy(mood, user_text, history=history)

    # 4) Encouragement (pass history through)
    encouragement = await encourage(user_text, mood, strategy, history=history)

    return {
        "mood": mood,
        "strategy": strategy,
        "encouragement": encouragement,
        "crisis_detected": False,
    }
