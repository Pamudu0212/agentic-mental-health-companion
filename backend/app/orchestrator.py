# app/orchestrator.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal

# Agents
from .agents.safety import detect_crisis, detect_crisis_with_moderation
from .agents.mood import detect_mood
from .agents.encouragement import encourage, converse
from .agents.coach_agent import coach_draft  # kept (not required now, but harmless)
from .agents.critic_agent import critic_fix
from .agents.skillcards import best_strategy_entry  # NEW: DB-backed retrieval with source

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
    advice_given: bool = False   # tells the UI whether we intentionally gave a step

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

# Advice gating regexes
RE_HELP     = re.compile(r"\b(help|what should i do|advice|suggest|tip|how do i|can you help|how to)\b", re.I)
RE_QWORD    = re.compile(r"\b(what|how|why|when|where|who|should|could|can|would|will|do|did|am|is|are|may|might)\b", re.I)
RE_ASK_NAME = re.compile(r"\b(what('?s| is)\s+your\s+name|who\s+are\s+you)\b", re.I)
RE_SMALL    = re.compile(r"\b(how are you|what'?s up|wyd)\b", re.I)
RE_DISTRESS = re.compile(
    r"\b(stress|stressed|overwhelm|overwhelmed|anxious|anxiety|panic|sad|down|depress|lonely|alone|angry|upset|worried|scared|afraid|tired|exhausted|burn(?:ed|t)\b|can.?t\s+(cope|focus|sleep))",
    re.I,
)

SUPPORT_MOODS  = {"sadness", "distress", "anger"}
POSITIVE_MOODS = {"joy", "optimism"}

def _safety_summary(state: TurnState) -> dict:
    """Simple label: 'watch' if message shows distress language or moderation flagged crisis."""
    txt = (state.user_text or "")
    if state.crisis == "self_harm":
        return {"level": "crisis_self",  "reason": "Self-harm risk detected"}
    if state.crisis == "other_harm":
        return {"level": "crisis_others", "reason": "Risk to others detected"}
    if RE_DISTRESS.search(txt):
        return {"level": "watch", "reason": "Tense or distressed language"}
    return {"level": "safe", "reason": "No crisis indicators found"}

def validate_and_repair(state: TurnState) -> TurnState:
    """
    Enforce final invariants:
      - If crisis appears anywhere → crisis mode wins.
      - Encouragement should align with strategy if we intentionally offered a step.
    """
    # Crisis wins
    if state.crisis != "none":
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        state.advice_given = False
        return state

    # Post-safety scan of generated text (defense-in-depth)
    if _likely_unsafe(state.strategy) or _likely_unsafe(state.encouragement):
        state.crisis = "self_harm"  # generic fallback
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        state.advice_given = False
        return state

    # If we intentionally provided advice, ensure the strategy is echoed once
    if (
        state.advice_given
        and state.strategy
        and state.strategy[:20].lower() not in (state.encouragement or "").lower()
    ):
        state.encouragement = (
            f"{(state.encouragement or '').rstrip()}\n\n"
            f"Why this:\n- {state.strategy}"
        )

    # If we did NOT intend to give advice, ensure strategy is empty
    if not state.advice_given:
        state.strategy = ""

    return state

def _should_offer_step(user_text: str, mood: str) -> bool:
    """
    Gate: suggest a step ONLY when at least one primary trigger is true:
      - explicit help/advice request
      - a real problem question (not name/smalltalk)
      - distress keywords in the message

    Positive moods require explicit help to offer steps.
    Very short messages don’t trigger steps.
    """
    t = (user_text or "").lower()

    # Ignore smalltalk/identity
    if RE_ASK_NAME.search(t) or RE_SMALL.search(t):
        return False

    helpy    = bool(RE_HELP.search(t))
    q_about  = ("?" in t or bool(RE_QWORD.search(t))) and not RE_ASK_NAME.search(t)
    distress = bool(RE_DISTRESS.search(t))
    primary  = helpy or q_about or distress

    if not primary:
        return False

    mood_l = (mood or "").lower()
    if mood_l in POSITIVE_MOODS and not helpy:
        return False

    # Avoid triggering on very short / low-content turns
    if len(t.split()) < 5:
        return False

    return True

# -----------------------
# Orchestration
# -----------------------
async def run_pipeline(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
):
    # Shared state
    state = TurnState(user_text=user_text, history=history or [])
    strategy_source: Optional[Dict[str, str]] = None  # NEW

    # 1) Safety gate (rules + LLM moderation)
    state.crisis = await detect_crisis_with_moderation(state.user_text)
    if state.crisis != "none":
        state = validate_and_repair(state)
        return {
            "mood": state.mood,
            "strategy": state.strategy,
            "encouragement": state.encouragement,
            "crisis_detected": True,
            "safety": _safety_summary(state),
            "advice_given": state.advice_given,
            "strategy_source": strategy_source,  # None in crisis path
        }

    # 2) Mood
    state.mood = detect_mood(state.user_text) or "neutral"

    # 3) Decide: conversation vs advice
    if _should_offer_step(state.user_text, state.mood):
        # NEW: DB-backed retrieval of a concrete, clinician-reviewed micro-step (with source)
        entry = best_strategy_entry(
            user_text=state.user_text,
            mood=state.mood,
            history=state.history,
        )

        if entry:
            state.strategy = entry["step"]
            state.advice_given = True
            strategy_source = {
                "name": entry.get("source_name", "") or "",
                "url": entry.get("source_url", "") or "",
            }
            # Provide a lightweight draft so the critic can review wording
            draft_msg = (
                "Based on what you shared, a tiny next step you could try is:\n\n"
                f"- {state.strategy}\n\n"
                "If that doesn’t fit, tell me what feels hard and we’ll adjust it together."
            )
        else:
            # No good step ranked → fall back to supportive conversation
            draft_msg = await converse(
                user_text=state.user_text,
                mood=state.mood,
                history=state.history,
                crisis=state.crisis,
            )
            state.strategy = ""
            state.advice_given = False
            strategy_source = None
    else:
        draft_msg = await converse(
            user_text=state.user_text,
            mood=state.mood,
            history=state.history,
            crisis=state.crisis,
        )
        state.strategy = ""
        state.advice_given = False
        strategy_source = None

    # Defense: if strategy itself looks unsafe
    if detect_crisis(state.strategy) != "none":
        state.crisis = "self_harm"
        state = validate_and_repair(state)
        return {
            "mood": state.mood,
            "strategy": state.strategy,
            "encouragement": state.encouragement,
            "crisis_detected": True,
            "safety": _safety_summary(state),
            "advice_given": state.advice_given,
            "strategy_source": strategy_source,
        }

    # 4) Encouragement (LLM-based supportive message)
    state.encouragement = await encourage(
        user_text=state.user_text,
        mood=state.mood,
        strategy=state.strategy,
        crisis=state.crisis,
        history=state.history,
    )

    # 5) Critic pass (safety/style/clarity on the drafted message)
    crit = await critic_fix(draft_msg, state.strategy if state.advice_given else "")
    if not crit.get("ok"):
        state.crisis = "self_harm"
        state = validate_and_repair(state)
        return {
            "mood": state.mood,
            "strategy": state.strategy,
            "encouragement": state.encouragement,
            "crisis_detected": True,
            "safety": _safety_summary(state),
            "advice_given": state.advice_given,
            "strategy_source": strategy_source,
        }

    state.encouragement = crit["message"]

    # 6) Final reconciliation + safety labeling
    state = validate_and_repair(state)
    return {
        "mood": state.mood,
        "strategy": state.strategy,
        "encouragement": state.encouragement,
        "crisis_detected": state.crisis != "none",
        "safety": _safety_summary(state),
        "advice_given": state.advice_given,
        "strategy_source": strategy_source,
    }
