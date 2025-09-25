# app/orchestrator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal

# Agents
from .agents.safety import detect_crisis, detect_crisis_with_moderation
from .agents.mood import detect_mood

from .agents.strategy import suggest_strategy
from .agents.encouragement import encourage

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
    history: Optional[List[Dict[str, str]]]  # [{role, content}]
    crisis: Crisis = "none"
    mood: str = "neutral"        # anger|joy|optimism|sadness|neutral|unknown
    strategy: str = ""
    encouragement: str = ""
    advice_given: bool = False  # tells the UI whether we intentionally gave a step


# -----------------------
# Validation / Reconcile
# -----------------------
UNSAFE_HINTS = (
    "kill", "suicide", "stab", "shoot", "harm", "hurt", "explode", "bomb",
    "attack", "poison", "unalive",
)

# ---------- Safety & heuristics ----------
UNSAFE_HINTS = ("kill","suicide","stab","shoot","harm","hurt","explode","bomb","attack","poison","unalive")


def _likely_unsafe(s: str) -> bool:
    t = (s or "").lower()
    return any(k in t for k in UNSAFE_HINTS)

def validate_and_repair(state: TurnState) -> TurnState:
    """
    Enforce final invariants:
      - If any sign of crisis appears in outputs → crisis mode wins.
      - Encouragement must mention/align with strategy if we’re not in crisis.
    """

# Advice gating regexes
RE_HELP     = re.compile(r"\b(help|what should i do|advice|suggest|tip|how do i|can you help|how to)\b", re.I)
RE_QWORD    = re.compile(r"\b(what|how|why|when|where|who|should|could|can|would|will|do|did|am|is|are|may|might)\b", re.I)
RE_ASK_NAME = re.compile(r"\b(what('?s| is)\s+your\s+name|who\s+are\s+you)\b", re.I)
RE_SMALL    = re.compile(r"\b(how are you|what'?s up|wyd)\b", re.I)
RE_DISTRESS = re.compile(
    r"\b(stress|stressed|overwhelm|overwhelmed|anxious|anxiety|panic|sad|down|depress|lonely|alone|angry|upset|worried|scared|afraid|tired|exhausted|burn(?:ed|t)\b|can.?t\s+(cope|focus|sleep))",
    re.I,
)

SUPPORT_MOODS  = {"sadness","distress","anger"}
POSITIVE_MOODS = {"joy","optimism"}

def _safety_summary(state: TurnState) -> dict:
    """Calmer label: 'watch' only if the *message* shows distress language or moderation flagged crisis."""
    txt = (state.user_text or "")
    if state.crisis == "self_harm":  return {"level": "crisis_self",  "reason": "Self-harm risk detected"}
    if state.crisis == "other_harm": return {"level": "crisis_others","reason": "Risk to others detected"}
    if RE_DISTRESS.search(txt):      return {"level": "watch",       "reason": "Tense or distressed language"}
    return {"level": "safe", "reason": "No crisis indicators found"}

def validate_and_repair(state: TurnState) -> TurnState:
    # Crisis wins

    if state.crisis != "none":
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        state.advice_given = False
        return state

    # post-safety scan of generated text (defense-in-depth)

    # Defense-in-depth

    if _likely_unsafe(state.strategy) or _likely_unsafe(state.encouragement):
        state.crisis = "self_harm"  # generic fallback
        state.mood = "unknown"
        state.strategy = ""
        state.encouragement = CRISIS_MESSAGE
        state.advice_given = False
        return state


    # If reply forgot to include the strategy, patch softly
    if state.strategy and state.strategy[:20].lower() not in state.encouragement.lower():

    # If we intentionally provided advice, ensure the strategy is echoed
    if state.advice_given and state.strategy and state.strategy[:20].lower() not in state.encouragement.lower():

        state.encouragement = (
            f"{state.encouragement.rstrip()}\n\n"
            f"One tiny, safe step you could try now: {state.strategy}"
        )


    return state

    # If we did NOT intend to give advice, make sure strategy is empty
    if not state.advice_given:
        state.strategy = ""

    return state

def _should_offer_step(user_text: str, mood: str) -> bool:
    """
    Stricter gate: suggest a step ONLY when at least one primary trigger is true:
      - explicit help/advice request
      - a real problem question (not name/smalltalk)
      - distress keywords in the message
    Mood can *support* the decision, but mood alone is not enough.
    Positive moods require explicit help to offer steps.
    Short/low-content messages don't trigger steps.
    """
    t = user_text.lower()

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


    # 1) Safety gate (rules first, LLM moderation if enabled)

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

    # 3) Decide: conversation (Encouragement) vs advice (Coach)
    if _should_offer_step(state.user_text, state.mood):
        draft = await coach_draft(user_text=state.user_text, mood=state.mood, history=state.history)
        state.strategy = draft.get("strategy") or ""
        draft_msg = draft.get("message") or ""
        state.advice_given = True
    else:
        draft_msg = await converse(user_text=state.user_text, mood=state.mood, history=state.history, crisis=state.crisis)
        state.strategy = ""
        state.advice_given = False


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

            "safety": _safety_summary(state),
            "advice_given": state.advice_given,
        }

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
        }

    state.encouragement = crit["message"]

    # 5) Final reconciliation + safety labeling

    state = validate_and_repair(state)

    return {
        "mood": state.mood,
        "strategy": state.strategy,
        "encouragement": state.encouragement,
        "crisis_detected": state.crisis != "none",


        "safety": _safety_summary(state),
        "advice_given": state.advice_given,

    }
