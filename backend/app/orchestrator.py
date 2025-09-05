# app/orchestrator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal
import re

from .agents.safety import detect_crisis, detect_crisis_with_moderation
from .agents.mood import detect_mood

# conversational & advice agents
from .agents.encouragement import converse
from .agents.coach_agent import coach_draft
from .agents.critic_agent import critic_fix

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
    history: Optional[List[Dict[str, str]]]
    crisis: Crisis = "none"
    mood: str = "neutral"
    strategy: str = ""
    encouragement: str = ""

# ---------- Safety labeling for the UI ----------
UNSAFE_HINTS = ("kill","suicide","stab","shoot","harm","hurt","explode","bomb","attack","poison","unalive")

def _likely_unsafe(s: str) -> bool:
    t = (s or "").lower()
    return any(k in t for k in UNSAFE_HINTS)

def _safety_summary(state: TurnState) -> dict:
    if state.crisis == "self_harm":
        return {"level": "crisis_self", "reason": "Self-harm risk detected"}
    if state.crisis == "other_harm":
        return {"level": "crisis_others", "reason": "Risk to others detected"}
    if (state.mood or "").lower() in {"sadness","anger","distress"} or _likely_unsafe(state.user_text):
        return {"level": "watch", "reason": "Tense or distressed language"}
    return {"level": "safe", "reason": "No crisis indicators found"}

def validate_and_repair(state: TurnState) -> TurnState:
    if state.crisis != "none":
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        return state
    if _likely_unsafe(state.strategy) or _likely_unsafe(state.encouragement):
        state.crisis = "self_harm"
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        return state
    # If we *did* suggest a step, ensure it’s mentioned
    if state.strategy and state.strategy[:20].lower() not in state.encouragement.lower():
        state.encouragement = (
            f"{state.encouragement.rstrip()}\n\n"
            f"One tiny, safe step you could try now: {state.strategy}"
        )
    return state

# ---------- Advice gating rules ----------
RE_HELP     = re.compile(r"\b(help|what should i do|advice|suggest|tip|how do i|can you help|how to)\b", re.I)
RE_QWORD    = re.compile(r"\b(what|how|why|when|where|who|should|could|can|would|will|do|did|am|is|are|may|might)\b", re.I)
RE_ASK_NAME = re.compile(r"\b(what('?s| is)\s+your\s+name|who\s+are\s+you)\b", re.I)
RE_SMALL    = re.compile(r"\b(how are you|what'?s up|wyd)\b", re.I)
RE_DISTRESS = re.compile(
    r"\b(stress|stressed|overwhelm|overwhelmed|anxious|anxiety|panic|sad|down|depress|lonely|alone|angry|upset|worried|scared|afraid|tired|exhausted|burn(ed|t)\b|can.?t\s+(cope|focus|sleep))",
    re.I,
)
SUPPORT_MOODS = {"sadness","distress","anger"}
POSITIVE_MOODS = {"joy","optimism"}

def _should_offer_step(user_text: str, mood: str) -> bool:
    t = user_text.lower()
    if RE_ASK_NAME.search(t) or RE_SMALL.search(t):
        return False
    helpy   = bool(RE_HELP.search(t))
    q_about = ("?" in t or bool(RE_QWORD.search(t))) and not RE_ASK_NAME.search(t)
    distress= bool(RE_DISTRESS.search(t))
    mood_l  = (mood or "").lower()
    allow   = helpy or q_about or distress or (mood_l in SUPPORT_MOODS)
    if mood_l in POSITIVE_MOODS and not helpy:
        return False
    return allow

# -----------------------
# Orchestration
# -----------------------
async def run_pipeline(user_text: str, history: Optional[List[Dict[str, str]]] = None):
    state = TurnState(user_text=user_text, history=history or [])

    # 1) Safety gate
    state.crisis = await detect_crisis_with_moderation(state.user_text)
    if state.crisis != "none":
        state = validate_and_repair(state)
        return {
            "mood": state.mood, "strategy": state.strategy, "encouragement": state.encouragement,
            "crisis_detected": True, "safety": _safety_summary(state),
        }

    # 2) Mood
    state.mood = detect_mood(state.user_text) or "neutral"

    # 3) Decide: conversation (encouragement) vs advice (coach)
    if _should_offer_step(state.user_text, state.mood):
        # Advice/step path (CoachAgent)
        draft = await coach_draft(user_text=state.user_text, mood=state.mood, history=state.history)
        state.strategy = draft.get("strategy") or ""
        draft_msg = draft.get("message") or ""
    else:
        # Conversation path (EncouragementAgent → converse; no steps)
        draft_msg = await converse(user_text=state.user_text, mood=state.mood, history=state.history, crisis=state.crisis)
        state.strategy = ""

    # 4) Defense-in-depth and polish
    if detect_crisis(draft_msg) != "none":
        state.crisis = "self_harm"
        state = validate_and_repair(state)
        return {
            "mood": state.mood, "strategy": state.strategy, "encouragement": state.encouragement,
            "crisis_detected": True, "safety": _safety_summary(state),
        }

    crit = await critic_fix(draft_msg, state.strategy)
    if not crit.get("ok"):
        state.crisis = "self_harm"
        state = validate_and_repair(state)
        return {
            "mood": state.mood, "strategy": state.strategy, "encouragement": state.encouragement,
            "crisis_detected": True, "safety": _safety_summary(state),
        }

    state.encouragement = crit["message"]
    state = validate_and_repair(state)

    return {
        "mood": state.mood,
        "strategy": state.strategy,
        "encouragement": state.encouragement,
        "crisis_detected": state.crisis != "none",
        "safety": _safety_summary(state),
    }
