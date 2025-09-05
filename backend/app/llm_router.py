# app/llm_router.py
from __future__ import annotations
import os, httpx
from typing import List, Dict, Any

def _env(agent: str, key: str, default: str = "") -> str:
    # Per-agent overrides (ENCOURAGEMENT_*, COACH_*, CRITIC_*, MODERATION_*)
    # fall back to global OPENAI_* if not set.
    return (
        os.getenv(f"{agent.upper()}_{key}") or
        os.getenv(f"OPENAI_{key}") or
        default
    )

async def chat_completions(
    agent: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    top_p: float = 0.9,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    base = _env(agent, "BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    model = _env(agent, "MODEL", "llama-3.3-70b-versatile")
    key   = _env(agent, "API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    body = {"model": model, "messages": messages, "temperature": temperature, "top_p": top_p}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{base}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        # helpful debug
        print(f"[LLM] agent={agent} model={data.get('model')} usage={data.get('usage')}")
        return data
