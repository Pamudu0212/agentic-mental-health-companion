# app/agents/critic_agent.py
from __future__ import annotations
import os, re, httpx
from typing import Dict
from ..agents.safety import detect_crisis
from ..prompts import ENCOURAGEMENT_SYSTEM

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")

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
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
        body = {"model": OPENAI_MODEL, "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ], "temperature": 0.2}
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
                                  headers=headers, json=body)
            r.raise_for_status()
            fixed = (r.json()["choices"][0]["message"]["content"] or "").strip()
        return {"ok": True, "message": fixed, "reason": "rewritten"}
    return {"ok": True, "message": message, "reason": "clean"}
