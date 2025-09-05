# app/orchestrator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal

from .agents.safety import detect_crisis, detect_crisis_with_moderation
from .agents.mood import detect_mood
from .agents.strategy import suggest_strategy
from .agents.encouragement import encourage

# Crisis types
Crisis = Literal["none", "self_harm", "other_harm"]

CRISIS_MESSAGE = (
    "I’m really concerned about safety here. I can’t help with anything that could put "
    "you or others at risk. Please contact local emergency services or a crisis hotline right now. "
    "If you can, reach out to someone you trust so you’re not alone."
)

@dataclass
class TurnState:
    user_text: str
    history: Optional[List[Dict[str, str]]]  # [{role, content}]
    crisis: Crisis = "none"
    mood: str = "neutral"        # anger|joy|optimism|sadness|neutral|unknown
    strategy: str = ""
    encouragement: str = ""

# -----------------------
# Validation / Reconcile
# -----------------------
UNSAFE_HINTS = (
    "kill", "suicide", "stab", "shoot", "harm", "hurt", "explode", "bomb",
    "attack", "poison", "unalive",
)

def _likely_unsafe(s: str) -> bool:
    t = (s or "").lower()
    return any(k in t for k in UNSAFE_HINTS)

def validate_and_repair(state: TurnState) -> TurnState:
    """
    Enforce final invariants:
      - If any sign of crisis appears in outputs → crisis mode wins.
      - Encouragement must mention/align with strategy if we’re not in crisis.
    """
    if state.crisis != "none":
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        return state

    # post-safety scan of generated text (defense-in-depth)
    if _likely_unsafe(state.strategy) or _likely_unsafe(state.encouragement):
        state.crisis = "self_harm"  # generic fallback
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        return state

    # If reply forgot to include the strategy, patch softly
    if state.strategy and state.strategy[:20].lower() not in state.encouragement.lower():
        state.encouragement = (
            f"{state.encouragement.rstrip()}\n\n"
            f"One tiny, safe step you could try now: {state.strategy}"
        )

    return state

# -----------------------
# Orchestration
# -----------------------
async def run_pipeline(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
):
    # Shared state
    state = TurnState(user_text=user_text, history=history or [])

    # 1) Safety gate (rules first, LLM moderation if enabled)
    state.crisis = await detect_crisis_with_moderation(state.user_text)

    if state.crisis != "none":
        state = validate_and_repair(state)
        return {
            "mood": state.mood,
            "strategy": state.strategy,
            "encouragement": state.encouragement,
            "crisis_detected": True,
        }

    # 2) Mood
    state.mood = detect_mood(state.user_text) or "neutral"

    # 3) Strategy
    state.strategy = await suggest_strategy(
        user_text=state.user_text,
        mood=state.mood,
        crisis=state.crisis,
        history=state.history,
    )

    # Defense: if strategy itself looks unsafe
    if detect_crisis(state.strategy) != "none":
        state.crisis = "self_harm"
        state = validate_and_repair(state)
        return {
            "mood": state.mood,
            "strategy": state.strategy,
            "encouragement": state.encouragement,
            "crisis_detected": True,
        }

    # 4) Encouragement
    state.encouragement = await encourage(
        user_text=state.user_text,
        mood=state.mood,
        strategy=state.strategy,
        crisis=state.crisis,
        history=state.history,
    )

    # Final reconciliation
    state = validate_and_repair(state)

    return {
        "mood": state.mood,
        "strategy": state.strategy,
        "encouragement": state.encouragement,
        "crisis_detected": state.crisis != "none",
    }
