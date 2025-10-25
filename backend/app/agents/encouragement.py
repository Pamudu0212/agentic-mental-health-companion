# app/agents/encouragement.py
from __future__ import annotations

import os
import json
import random
import re
import time
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass

import httpx

from ..prompts import ENCOURAGEMENT_SYSTEM  # kept (even if unused by default)
from ..llm_router import chat_completions  # per-agent router
from ..agents.safety import detect_crisis

# -------------------
# Types
# -------------------
Crisis = Literal["none", "self_harm", "other_harm"]


# -------------------
# Memory Classes
# -------------------
@dataclass
class ConversationTurn:
    user_message: str
    agent_response: str
    mood: str
    timestamp: float
    crisis_level: str = "none"


class ConversationMemory:
    def __init__(self, session_id: str, max_turns: int = 20):
        self.session_id = session_id
        self.max_turns = max_turns
        self.turns: List[ConversationTurn] = []
        self.persistent_themes: List[str] = []

    def add_turn(self, user_message: str, agent_response: str, mood: str, crisis_level: str = "none"):
        """Add a conversation turn to memory"""
        turn = ConversationTurn(
            user_message=user_message,
            agent_response=agent_response,
            mood=mood,
            timestamp=time.time(),
            crisis_level=crisis_level
        )
        self.turns.append(turn)

        # Keep only recent turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

        self._update_persistent_themes()

    def _update_persistent_themes(self):
        """Detect recurring themes/moods across conversation"""
        recent_moods = [turn.mood for turn in self.turns[-8:] if turn.mood]
        if len(recent_moods) >= 3:
            mood_counts = {}
            for mood in recent_moods:
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

            # If same mood appears in 60%+ of recent turns, it's persistent
            total_turns = len(recent_moods)
            self.persistent_themes = [
                mood for mood, count in mood_counts.items()
                if count / total_turns >= 0.6
            ]

    def get_recent_history(self, last_n: int = 6) -> List[Dict[str, str]]:
        """Get recent conversation history in message format"""
        history = []
        for turn in self.turns[-last_n:]:
            history.extend([
                {"role": "user", "content": turn.user_message},
                {"role": "assistant", "content": turn.agent_response}
            ])
        return history

    def get_mood_trend(self) -> Dict[str, any]:
        """Analyze mood patterns over time"""
        if not self.turns:
            return {"trend": "stable", "persistent_moods": [], "recent_crisis": False}

        return {
            "trend": self._calculate_mood_trend(),
            "persistent_moods": self.persistent_themes,
            "recent_crisis": any(turn.crisis_level != "none" for turn in self.turns[-3:])
        }

    def _calculate_mood_trend(self) -> str:
        """Simple trend analysis based on mood patterns"""
        moods = [turn.mood for turn in self.turns if turn.mood]
        if len(moods) < 3:
            return "stable"

        # Simple trend detection (you can enhance this)
        negative_moods = {"sad", "angry", "anxious", "stressed", "overwhelmed"}
        recent_negative = sum(1 for mood in moods[-3:] if mood in negative_moods)

        if recent_negative >= 2:
            return "deteriorating"
        elif recent_negative == 0:
            return "improving"
        else:
            return "stable"


# Session memory storage (in production, use Redis or database)
_session_memories: Dict[str, ConversationMemory] = {}


def get_session_memory(session_id: str) -> ConversationMemory:
    """Get or create conversation memory for session"""
    if session_id not in _session_memories:
        _session_memories[session_id] = ConversationMemory(session_id)
    return _session_memories[session_id]


# -------------------
# Configuration
# -------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY") or ""
OPENAI_BASE_URL = (os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # e.g., "llama-3.1-8b-instant" on Groq

CRISIS_MESSAGE = (
    "I'm really concerned about safety here. I can't help with anything that could put "
    "you or others at risk. Please contact local emergency services or a crisis hotline right now. "
    "If you can, reach out to someone you trust so you're not alone."
)

FALLBACKS = [
    "Thanks for saying that. What feels most present for you right now?",
    "I'm listening. Could you say a little more about what's hard in this moment?",
    "That makes sense. What do you notice in your body or thoughts right now?",
]

SYSTEM = """You are the Encouragement Agent.
Write 2–4 warm, non-clinical sentences that mirror the user's feeling and invite exactly the given strategy.
Rules:
- Mention the strategy verbatim exactly once (if provided and safe).
- Be safe; never normalize harm; no instructions enabling harm.
- If crisis flag is not 'none', return the crisis support message instead.
Output JSON ONLY:
{"encouragement": string}
"""

# Advice-like words to avoid in conversation mode
ADVICE_HINTS = (
    "try ", "you could", "do this", "do that", "step", "exercise", "breathing",
    "box breathing", "grounding", "timer", "stretch", "walk for", "count", "inhale",
)


# -------------------
# Helpers
# -------------------
def _history(history: Optional[List[Dict[str, str]]]) -> str:
    """Render recent turns for context (last 6)."""
    if not history:
        return ""
    lines = []
    for m in history[-6:]:
        role = m.get("role", "")
        content = m.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def _llm_json(messages: List[Dict[str, str]], temperature: float = 0.35, timeout: float = 40.0) -> str:
    """Call the Chat Completions API with JSON response_format and return the raw text."""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()


def _score_candidate(text: str, user_text: str) -> int:
    """Small rubric: open question + empathy + short + mirrors user keyword + no advice."""
    t = text.lower()
    score = 0
    if "?" in t:
        score += 1
    if any(w in t for w in ("sounds", "seems", "makes sense", "thanks for", "i hear", "i'm here")):
        score += 1
    if not any(h in t for h in ADVICE_HINTS):
        score += 1
    if len(text.split()) <= 45:
        score += 1
    kws = re.findall(r"[a-zA-Z]{4,}", (user_text or "").lower())
    if kws and any(k in t for k in kws[:3]):
        score += 1
    return score


async def _candidate(user_text: str, mood: str, temp: float) -> str:
    """Generate a single short reflective response with one open gentle question."""
    sys = (
        "You are a warm, non-clinical companion. "
        "Write 1–2 short sentences. First reflect/validate what the user seems to feel; "
        "then ask ONE open, gentle question to learn more. Avoid advice/steps, lists, or emojis."
    )
    messages = [
        {"role": "system", "content": sys},
        {"role": "user", "content": f"User: {user_text}\nMood guess: {mood or 'neutral'}\nReply:"},
    ]
    data = await chat_completions("ENCOURAGEMENT", messages, temperature=temp, top_p=0.9)
    return (data["choices"][0]["message"]["content"] or "").strip()


def _get_adaptive_system_prompt(mood_trend: Dict[str, any], persistent_themes: List[str]) -> str:
    """Adapt system prompt based on conversation patterns"""
    base_prompt = (
        "You are a warm, non-clinical companion. "
        "Write 1–2 short sentences. First reflect/validate what the user seems to feel; "
        "then ask ONE open, gentle question to learn more. Avoid advice/steps, lists, or emojis."
    )

    adaptations = []

    if mood_trend.get("trend") == "deteriorating":
        adaptations.append("The user's mood seems to be getting worse. Be especially gentle and validating.")

    if mood_trend.get("recent_crisis"):
        adaptations.append("The user recently discussed serious concerns. Be extra careful and supportive.")

    if persistent_themes:
        themes_str = ", ".join(persistent_themes)
        adaptations.append(
            f"The user keeps returning to these themes: {themes_str}. Acknowledge this persistence gently.")

    if adaptations:
        return base_prompt + " " + " ".join(adaptations)

    return base_prompt


def _adapt_strategy_to_history(strategy: str, mood_trend: Dict[str, any], turns: List[ConversationTurn]) -> str:
    """Adapt recommended strategies based on conversation history"""
    if not strategy:
        return strategy

    # If mood is deteriorating, suggest simpler strategies
    if mood_trend.get("trend") == "deteriorating" and "complex" in strategy.lower():
        # Replace complex strategies with simpler alternatives
        if "journal" in strategy.lower():
            return "just writing one sentence about how you feel"
        elif "meditation" in strategy.lower():
            return "taking one deep breath"

    # Check if we've suggested similar strategies recently
    recent_strategies = []
    for turn in turns[-4:]:
        # Extract strategy mentions from previous responses
        if "try" in turn.agent_response.lower() or "suggest" in turn.agent_response.lower():
            recent_strategies.append(turn.agent_response)

    # If strategy seems repetitive, modify it slightly
    if any(strategy.lower() in resp.lower() for resp in recent_strategies[-2:]):
        return f"another approach: {strategy}"

    return strategy


# ----------------------------
# Memory-Enhanced Functions
# ----------------------------
async def encourage_with_memory(
        *,
        user_text: str,
        mood: str,
        strategy: str,
        session_id: str,
        crisis: Crisis = "none",
) -> str:
    """
    Enhanced version with memory awareness
    """
    memory = get_session_memory(session_id)
    mood_trend = memory.get_mood_trend()
    history = memory.get_recent_history()

    # Adaptive strategy based on conversation history
    adapted_strategy = _adapt_strategy_to_history(strategy, mood_trend, memory.turns)

    # Generate response with history context
    response = await encourage(
        user_text=user_text,
        mood=mood,
        strategy=adapted_strategy,
        history=history,
        crisis=crisis
    )

    # Store in memory
    memory.add_turn(user_text, response, mood, crisis)

    return response


async def converse_with_memory(
        *,
        user_text: str,
        mood: str,
        session_id: str,
        crisis: Crisis = "none",
) -> str:
    """
    Enhanced conversation with memory
    """
    memory = get_session_memory(session_id)
    history = memory.get_recent_history()
    mood_trend = memory.get_mood_trend()

    # Adaptive responses based on history
    response = await _converse_adaptive(
        user_text=user_text,
        mood=mood,
        history=history,
        crisis=crisis,
        mood_trend=mood_trend,
        persistent_themes=memory.persistent_themes
    )

    memory.add_turn(user_text, response, mood, crisis)
    return response


async def _converse_adaptive(
        *,
        user_text: str,
        mood: str,
        history: List[Dict[str, str]],
        crisis: Crisis,
        mood_trend: Dict[str, any],
        persistent_themes: List[str],
) -> str:
    """
    Adaptive conversation that considers history patterns
    """
    if crisis != "none" or detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    # Adjust system prompt based on conversation history
    system_prompt = _get_adaptive_system_prompt(mood_trend, persistent_themes)

    messages = [
        {"role": "system", "content": system_prompt},
        *history[-6:],  # Include recent history
        {"role": "user", "content": f"Current message: {user_text}\nCurrent mood: {mood}"}
    ]

    try:
        response = await chat_completions(
            "ENCOURAGEMENT",
            messages,
            temperature=0.7,
            top_p=0.9
        )
        return (response["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return random.choice(FALLBACKS)


# ----------------------------
# JSON variant used by some flows
# ----------------------------
async def encourage_json(
        *,
        user_text: str,
        mood: str,
        strategy: str,
        crisis: Crisis,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.35,
) -> str:
    """
    Produce a short supportive response that mirrors the user's feeling and naturally invites the given strategy.
    Returns plain **text** (extracted from the JSON "encouragement" field).
    """
    # Safety gates
    if crisis != "none":
        return CRISIS_MESSAGE
    if detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    user_prompt = {
        "role": "user",
        "content": (
            f"User mood: {mood or 'neutral'}\n"
            f"User text: {user_text}\n"
            f"Strategy to invite (must include verbatim once if sensible): {strategy or '(none)'}\n"
            f"Crisis: {crisis}\n"
            f"History:\n{_history(history)}\n\n"
            "Return JSON only."
        ),
    }
    messages = [
        {"role": "system", "content": SYSTEM},
        user_prompt,
    ]

    try:
        text = await _llm_json(messages, temperature=temperature)
        obj = json.loads(text)
        reply = (obj.get("encouragement") or "").strip()
    except Exception:
        if strategy:
            return (
                "I'm here with you and I hear how you're feeling. "
                f"If it helps, you could try this small step: {strategy}"
            )
        return random.choice(FALLBACKS)

    if detect_crisis(reply) != "none":
        return CRISIS_MESSAGE

    # Keep concise
    if len(reply.split()) > 90:
        reply = "Thanks for sharing that. What feels most present for you right now?"
    return reply


# ----------------------------
# Conversation mode (no strategy; 1–2 sentences)
# ----------------------------
async def converse(
        *,
        user_text: str,
        mood: str,
        history: Optional[List[Dict[str, str]]] = None,
        crisis: Crisis = "none",
) -> str:
    """
    Produce 1–2 sentences: reflect the feeling + ask one gentle open question.
    No coping steps, no lists, no emojis.
    """
    if crisis != "none" or detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    temps = (0.65, 0.85, 0.6)
    candidates: List[str] = []
    for t in temps:
        try:
            candidates.append(await _candidate(user_text, mood, t))
        except Exception:
            continue

    if not candidates:
        return random.choice(FALLBACKS)

    best = max(candidates, key=lambda s: _score_candidate(s, user_text))
    if len(best.split()) > 60:
        best = "Thanks for sharing that. What feels most present for you right now?"
    return best


# ----------------------------
# Strategy-inviting helper (plain text)
# ----------------------------
async def encourage(
        *,
        user_text: str,
        mood: str,
        strategy: str,
        history: Optional[List[Dict[str, str]]] = None,
        crisis: Crisis = "none",
) -> str:
    """
    Reflect + gently invite a concrete strategy once. 1–3 sentences total.
    Uses the JSON system prompt under the hood, returns plain text.
    """
    if crisis != "none" or detect_crisis(user_text) != "none":
        return CRISIS_MESSAGE

    # Prefer the JSON-governed path for exact strategy inclusion; then post-trim
    reply = await encourage_json(
        user_text=user_text,
        mood=mood,
        strategy=strategy,
        crisis=crisis,
        history=history,
        temperature=0.35,
    )

    if len(reply.split()) > 90:
        reply = "Thanks for sharing that. What feels most present for you right now?"
    return reply