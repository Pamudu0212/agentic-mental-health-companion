from __future__ import annotations
from typing import Optional, List, Dict
from ..llm_router import chat_completions
from .skillcards import retrieve_skill_cards
from .intent import classify_intent

SUPPORT_MOODS = {"sadness", "distress", "anger"}
POSITIVE_MOODS = {"joy", "optimism"}

async def _llm(messages: List[Dict[str, str]], temperature=0.6, top_p=0.9) -> str:
    data = await chat_completions("COACH", messages, temperature=temperature, top_p=top_p)
    return (data["choices"][0]["message"]["content"] or "").strip()

async def _chat_only(user_text: str, mood: str) -> str:
    """Therapist-like reflection + one open question, no advice."""
    sys = (
        "You are a warm, non-clinical companion. "
        "Respond in 1–2 short sentences. Reflect/validate the user’s feeling, "
        "then ask ONE open, gentle question to learn more. "
        "You do NOT have a personal name and should NOT propose one. "
        "Do not give advice or steps. No lists, no emojis."
    )
    return await _llm(
        [{"role": "system", "content": sys},
         {"role": "user", "content": f"User: {user_text}\nMood guess: {mood or 'neutral'}\nReply:"}],
        temperature=0.6, top_p=0.9
    )

async def _identity_reply(user_text: str, mood: str) -> str:
    """Direct, neutral identity response (no name, no nickname)."""
    sys = (
        "You are a warm, non-clinical companion. The user asked about your identity/name. "
        "You do NOT have a personal name and must NOT propose or suggest any. "
        "Answer plainly that you don't use a personal name, then continue the conversation with ONE open, gentle question. "
        "Keep it to 1–2 short sentences. No advice, no steps, no emojis."
    )
    return await _llm(
        [{"role": "system", "content": sys},
         {"role": "user", "content": f"User: {user_text}\nMood guess: {mood or 'neutral'}\nWrite the reply now:"}],
        temperature=0.3, top_p=1.0
    )

async def _step_reply(user_text: str, mood: str, history: Optional[List[Dict[str, str]]]) -> Dict[str, str]:
    """Choose exactly one tiny, safe step and mention it naturally."""
    cards = retrieve_skill_cards(user_text, mood=mood, history=history, k=3)
    bullets = "\n".join([f"- {c['label']}: {c['step']}" for c in cards]) or "- grounding: Take 3 slow breaths"
    user = (
        f"User said: {user_text}\nMood guess: {mood or 'neutral'}\n"
        f"Choose ONE tiny, safe step from:\n{bullets}\n\n"
        "Write 2 short sentences: (1) brief reflection (no diagnosis), "
        "(2) one tiny step in a natural sentence. Under 45 words. No emojis."
    )
    out = await _llm(
        [{"role": "system", "content": "You are a supportive, practical coach. Keep advice tiny and safe."},
         {"role": "user", "content": user}],
        temperature=0.7, top_p=0.9
    )
    # best-effort capture of which step was used
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
    Routing by LLM intent:
      - identity / smalltalk / venting / crisis_risk / other → conversation only (no steps).
      - help_request / problem_question → step.
    Positive moods require explicit help to get steps.
    """
    intent = await classify_intent(user_text)
    mood_l = (mood or "").lower()

    convo_only = intent in {"identity","smalltalk","venting","crisis_risk","other"}
    wants_step = intent in {"help_request","problem_question"}

    # If mood is positive, only give steps on explicit help requests
    if mood_l in POSITIVE_MOODS and intent != "help_request":
        wants_step = False

    # Identity gets a direct, neutral answer (no name suggested)
    if intent == "identity":
        msg = await _identity_reply(user_text, mood)
        return {"message": msg, "strategy": ""}

    if convo_only:
        msg = await _chat_only(user_text, mood)
        return {"message": msg, "strategy": ""}

    if wants_step or mood_l in SUPPORT_MOODS:
        return await _step_reply(user_text, mood, history)

    # Default: conversation-only
    msg = await _chat_only(user_text, mood)
    return {"message": msg, "strategy": ""}
