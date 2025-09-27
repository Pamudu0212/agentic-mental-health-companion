# app/orchestrator.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal

# Agents
from .agents.safety import detect_crisis, detect_crisis_with_moderation
from .agents.mood import detect_mood
from .agents.encouragement import encourage, converse
from .agents.coach_agent import coach_draft  # optional, kept
from .agents.critic_agent import critic_fix
from .agents.skillcards import best_strategy_entry  # DB-backed retrieval w/ why + source

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
    strategy: str = ""           # the step text (for backward-compat)
    encouragement: str = ""
    advice_given: bool = False

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
    txt = (state.user_text or "")
    if state.crisis == "self_harm":
        return {"level": "crisis_self",  "reason": "Self-harm risk detected"}
    if state.crisis == "other_harm":
        return {"level": "crisis_others", "reason": "Risk to others detected"}
    if RE_DISTRESS.search(txt):
        return {"level": "watch", "reason": "Tense or distressed language"}
    return {"level": "safe", "reason": "No crisis indicators found"}

def validate_and_repair(state: TurnState) -> TurnState:
    # Crisis wins
    if state.crisis != "none":
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        state.advice_given = False
        return state

    # Defense-in-depth
    if _likely_unsafe(state.strategy) or _likely_unsafe(state.encouragement):
        state.crisis = "self_harm"
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        state.advice_given = False
        return state

    # If we intentionally provided advice, echo the step once inside the message (lightly)
    if (
        state.advice_given
        and state.strategy
        and state.strategy[:20].lower() not in (state.encouragement or "").lower()
    ):
        state.encouragement = (
            f"{(state.encouragement or '').rstrip()}\n\n"
            f"Why this:\n- {state.strategy}"
        )

    # If not giving advice, make sure strategy string is empty
    if not state.advice_given:
        state.strategy = ""

    return state

def _should_offer_step(user_text: str, mood: str) -> bool:
    t = (user_text or "").lower()

    if RE_ASK_NAME.search(t) or RE_SMALL.search(t):
        return False

    helpy    = bool(RE_HELP.search(t))
    q_about  = ("?" in t or bool(RE_QWORD.search(t))) and not RE_ASK_NAME.search(t)
    distress = bool(RE_DISTRESS.search(t))
    primary  = helpy or q_about or distress
    if not primary:
        return False

    if (mood or "").lower() in POSITIVE_MOODS and not helpy:
        return False

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
    state = TurnState(user_text=user_text, history=history or [])

    # These enrich the response for the UI:
    strategy_source: Optional[Dict[str, str]] = None
    strategy_why: str = ""
    strategy_label: str = ""

    # 1) Safety gate
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
            "strategy_source": strategy_source,
            "strategy_why": strategy_why,
            "strategy_label": strategy_label,
        }

    # 2) Mood
    state.mood = detect_mood(state.user_text) or "neutral"

    # 3) Decide: conversation vs advice
    if _should_offer_step(state.user_text, state.mood):
        entry = best_strategy_entry(
            user_text=state.user_text,
            mood=state.mood,
            history=state.history,
        )
        if entry:
            state.strategy = entry["step"]
            state.advice_given = True
            strategy_why = entry.get("why", "") or ""
            strategy_label = entry.get("label", "") or ""
            strategy_source = {
                "name": entry.get("source_name", "") or "",
                "url": entry.get("source_url", "") or "",
            }
            draft_msg = (
                "Based on what you shared, a tiny next step you could try is:\n\n"
                f"- {state.strategy}\n\n"
                "If that doesn’t fit, tell me what feels hard and we’ll adjust it together."
            )
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
            "strategy_why": strategy_why,
            "strategy_label": strategy_label,
        }

    # 4) Encouragement
    state.encouragement = await encourage(
        user_text=state.user_text,
        mood=state.mood,
        strategy=state.strategy,
        crisis=state.crisis,
        history=state.history,
    )

    # 5) Critic pass
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
            "strategy_why": strategy_why,
            "strategy_label": strategy_label,
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
        "strategy_why": strategy_why,
        "strategy_label": strategy_label,
    }
