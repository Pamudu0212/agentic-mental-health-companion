# app/agents/coach_agent.py
from __future__ import annotations
import os, httpx, re
from typing import Optional, List, Dict
from .skillcards import retrieve_skill_cards, SKILL_CARDS
from ..prompts import ENCOURAGEMENT_SYSTEM

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")

# ───────────────────────── intent & signal patterns ─────────────────────────
RE_GREETING   = re.compile(r"\b(hi|hello|hey|yo|sup)\b", re.I)
RE_ASK_NAME   = re.compile(r"\b(what('?s| is)\s+your\s+name|who\s+are\s+you)\b", re.I)
RE_GIVE_NAME  = re.compile(r"\b(your name is|i(?:'m| am)\s+naming\s+you|i want to give you a name|i(?:'m| am)\s+going to call you)\b", re.I)
RE_SMALLTALK  = re.compile(r"\b(how are you|what'?s up|wyd)\b", re.I)

# clear help/advice cues
RE_HELP       = re.compile(r"\b(help|what should i do|advice|suggest|tip|how do i|can you help|how to)\b", re.I)

# general question cue (not just '?', include wh/aux)
RE_QWORD      = re.compile(r"\b(what|how|why|when|where|who|should|could|can|would|will|do|did|am|is|are|may|might)\b", re.I)

# distress language (non-exhaustive; keeps it simple and cheap)
RE_DISTRESS   = re.compile(
    r"\b(stress|stressed|overwhelm|overwhelmed|anxious|anxiety|panic|sad|down|depress|lonely|alone|angry|upset|worried|scared|afraid|tired|exhausted|burn(ed|t)\b|can.?t\s+(cope|focus|sleep))",
    re.I,
)

SUPPORT_MOODS = {"sadness", "distress", "anger"}          # moods that justify a step even w/o a question
POSITIVE_MOODS = {"joy", "optimism"}                      # avoid steps unless help explicitly requested

def _short_quote(text: str, max_words: int = 6) -> str:
    words = re.findall(r"\w[\w'’\-]*", text)
    return " ".join(words[:max_words])

def _intent(text: str) -> str:
    t = text.lower()
    if RE_GIVE_NAME.search(t): return "give_name"
    if RE_ASK_NAME.search(t):  return "ask_name"
    if RE_GREETING.search(t) or RE_SMALLTALK.search(t): return "smalltalk"
    if RE_HELP.search(t):      return "help_request"
    return "other"

def _is_problem_question(text: str) -> bool:
    """Question about their situation (not identity/smalltalk)."""
    t = text.lower()
    if RE_ASK_NAME.search(t) or RE_SMALLTALK.search(t):
        return False
    return "?" in t or bool(RE_QWORD.search(t))

def _has_distress(text: str) -> bool:
    return bool(RE_DISTRESS.search(text))

async def _llm(messages: list[dict], temperature=0.5, top_p=0.95, timeout=20.0) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
    body = {"model": OPENAI_MODEL, "messages": messages, "temperature": temperature, "top_p": top_p}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                              headers=headers, json=body)
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()

async def _chat_only_reply(user_text: str, mood: str) -> str:
    """Therapist-like reflection + one open question (no coping step)."""
    messages = [
        {"role": "system", "content":
         "You are a warm, non-clinical companion. Respond in 1–2 short sentences. "
         "Reflect/validate the user’s feeling, then ask ONE open, gentle question to learn more. "
         "No advice, no coping steps, no lists, no emojis."
        },
        {"role": "user", "content": f"User said: {user_text}\nMood guess: {mood or 'neutral'}\nWrite the reply."}
    ]
    return await _llm(messages, temperature=0.6, top_p=0.9)

async def _step_reply(user_text: str, mood: str, history: Optional[List[Dict[str, str]]]) -> Dict[str, str]:
    """Select skill cards and craft a brief reply that includes exactly one tiny step."""
    cards = retrieve_skill_cards(user_text, mood=mood, history=history, k=3)
    bullets = "\n".join([f"- {c['label']}: {c['step']}" for c in cards])
    quote = _short_quote(user_text)
    user_prompt = (
        f"User said (short quote): “{quote}”. Mood guess: {mood or 'neutral'}.\n"
        f"Here are a few relevant tiny, safe steps:\n{bullets}\n\n"
        "Write 2 short sentences total:\n"
        "1) Brief reflection/validation (no judging, no diagnosis).\n"
        "2) Offer exactly ONE of the steps above (choose the best fit) in a natural sentence.\n"
        "Keep it under ~45 words. Plain text only. No emojis."
    )
    messages = [
        {"role": "system", "content": ENCOURAGEMENT_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    out = await _llm(messages, temperature=0.7, top_p=0.9)

    # pick which step the model referenced; fallback to first
    chosen = ""
    out_low = out.lower()
    for c in cards:
        if c["step"].lower() in out_low or c["label"].lower() in out_low:
            chosen = c["step"]; break
    if not chosen and cards:
        chosen = cards[0]["step"]
    return {"message": out, "strategy": chosen}

async def coach_draft(
    *, user_text: str, mood: str, history: Optional[List[Dict[str, str]]]
) -> Dict[str, str]:
    """
    Policy:
      • First turn → warm welcome (no step).
      • Small talk / ask name / give name → identity or exploratory reply (no step).
      • Suggest a step ONLY if:
          - explicit help/advice request, OR
          - non-smalltalk question about their situation, OR
          - distress keywords present, OR
          - mood ∈ {sadness, distress, anger}.
        Additionally, if mood ∈ {joy, optimism}, suggest a step only on explicit help/advice.
      • Otherwise → conversational reflection + one open question (no step).
    """
    # first turn → greeting
    if not history:
        msg = ("It’s nice to meet you. I’m here to support you, not to diagnose. "
               "What’s on your mind right now—maybe just a word or two?")
        return {"message": msg, "strategy": ""}

    intent = _intent(user_text)
    is_q   = _is_problem_question(user_text)
    is_distress = _has_distress(user_text)
    mood_l = (mood or "").lower()

    # small talk / identity
    if intent in {"ask_name", "give_name", "smalltalk"}:
        if intent == "give_name":
            msg = ("I appreciate the thought. I don’t use a personal name, "
                   "but I’m here with you. What feels most present for you right now?")
        elif intent == "ask_name":
            msg = ("I’m your companion here—no personal name, just here to support you. "
                   "What’s on your mind?")
        else:
            msg = await _chat_only_reply(user_text, mood)
        return {"message": msg, "strategy": ""}

    # gating for steps
    positive = mood_l in POSITIVE_MOODS
    explicit_help = (intent == "help_request")
    allow_step = explicit_help or is_q or is_distress or (mood_l in SUPPORT_MOODS)

    # If mood is positive, only allow if they explicitly asked for help
    if positive and not explicit_help:
        allow_step = False

    if allow_step:
        return await _step_reply(user_text, mood, history)

    # default: stay conversational (no step)
    msg = await _chat_only_reply(user_text, mood)
    return {"message": msg, "strategy": ""}
