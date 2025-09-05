from __future__ import annotations
from typing import List, Dict, Optional

from .agents.mood import detect_mood
from .agents.safety import detect_crisis, detect_ambiguous_risk
from .agents.strategy import suggest_strategy
from .agents.encouragement import encourage
from .prompts import CRISIS_MESSAGE_SELF, CRISIS_MESSAGE_OTHERS


async def run_pipeline(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
):
    """
    Orchestrates: safety -> mood -> strategy -> encouragement.

    Behavior:
      1) If a *confirmed crisis* (self-harm / harm-to-others) is detected,
         immediately return a short crisis-safe message.
      2) If NOT a crisis but the language indicates *ambiguous risk*
         (e.g., “danger / dangerous / threat” with no target),
         return a clarifying, safeguarding response (not upbeat).
      3) Otherwise run the normal mood/strategy/encouragement pipeline.
    """
    # 1) Confirmed crisis
    crisis_type = detect_crisis(user_text)
    if crisis_type != "none":
        crisis_message = (
            CRISIS_MESSAGE_SELF if crisis_type == "self_harm" else CRISIS_MESSAGE_OTHERS
        )
        return {
            "mood": "unknown",
            "strategy": "",
            "encouragement": crisis_message,
            "crisis_detected": True,
        }

    # 2) Ambiguous risk (new path)
    if detect_ambiguous_risk(user_text):
        clarification = (
            "I noticed you mentioned “danger”. Are you worried about your own safety or "
            "someone else’s? If you’re in immediate danger, please contact local emergency "
            "services right away. I want to make sure I understand and can respond safely."
        )
        return {
            "mood": "unknown",
            "strategy": "",
            "encouragement": clarification,
            "crisis_detected": False,  # not a confirmed crisis, but not 'safe & upbeat' either
        }

    # 3) Normal path
    mood = detect_mood(user_text)
    strategy = await suggest_strategy(mood, user_text, history=history)
    encouragement = await encourage(user_text, mood, strategy, history=history)

    return {
        "mood": mood,
        "strategy": strategy,
        "encouragement": encouragement,
        "crisis_detected": False,
    }
