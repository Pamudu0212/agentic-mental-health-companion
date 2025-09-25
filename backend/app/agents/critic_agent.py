# app/agents/critic_agent.py
from __future__ import annotations
import re
from typing import Dict
from ..agents.safety import detect_crisis
from ..prompts import ENCOURAGEMENT_SYSTEM
from ..llm_router import chat_completions  # ← per-agent router

UNSAFE_HINTS = ("suicide", "kill yourself", "hurt yourself")

def _too_long(txt: str) -> bool:
    return len(txt.split()) > 70 or txt.count("\n") > 3

def _has_bullets(txt: str) -> bool:
    return bool(re.search(r"(^|\n)\s*[-*•]\s+", txt))

async def critic_fix(message: str, strategy: str) -> Dict[str, str]:
    """
    Enforce constraints: no crisis violations, short length, one tiny step, no lists.
    If violations found, ask LLM to rewrite under strict rules.
    """
    # 1) hard safety
    if detect_crisis(message) != "none":
        return {"ok": False, "message": "", "reason": "crisis_detected"}

    if any(k in message.lower() for k in UNSAFE_HINTS) or _too_long(message) or _has_bullets(message):
        # 2) LLM rewrite with tight constraints
        sys = (
            ENCOURAGEMENT_SYSTEM +
            " Rewrite the assistant reply to obey all rules: ≤45 words, 2 short sentences max, "
            "exactly ONE safe do-now step, no lists, no emojis."
        )
        user = f"Original reply:\n{message}\n\nExtracted step:\n{strategy}\n\nRewrite now."

        data = await chat_completions("CRITIC", [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ], temperature=0.2, top_p=1.0)
        fixed = (data["choices"][0]["message"]["content"] or "").strip()
        return {"ok": True, "message": fixed, "reason": "rewritten"}

    return {"ok": True, "message": message, "reason": "clean"}
