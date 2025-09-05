# app/agents/safety.py
from __future__ import annotations
import os
import re
import unicodedata
from typing import Literal, Optional

import httpx

Crisis = Literal["none", "self_harm", "other_harm"]

# ---------------------------
# Normalization & slang map
# ---------------------------
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def _normalize(s: str) -> str:
    s = s.lower()
    s = unicodedata.normalize("NFKC", s)
    s = _strip_accents(s)
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)              # cooool -> cool
    s = re.sub(r"[_\u200b\u200c\u200d]", " ", s)      # zero-width etc.
    s = re.sub(r"\s+", " ", s).strip()
    return s

SLANG_MAP = {
    "kms": "kill myself",
    "k m s": "kill myself",
    "k*m*s": "kill myself",
    "k/ms": "kill myself",
    "s/h": "self harm",
    "unalive": "suicide",
    "end it": "end my life",
    "end myself": "end my life",
    "off myself": "kill myself",
    "i cant go on": "end my life",
    "take my life": "end my life",
}

def _expand_slang(s: str) -> str:
    text = f" {s} "
    for k, v in SLANG_MAP.items():
        if "*" in k or "/" in k or " " in k:
            pattern = re.escape(k).replace("\\*", r"\W*").replace("\\/", r"\W*")
            text = re.sub(rf"\b{pattern}\b", f" {v} ", text)
        else:
            text = re.sub(rf"\b{k}\b", f" {v} ", text)
    return re.sub(r"\s+", " ", text).strip()

# ---------------------------
# Rule patterns
# ---------------------------
SELF_HARM_PATTERNS = [
    r"\bkill\s+myself\b",
    r"\bend\s+my\s+life\b",
    r"\btake\s+my\s+life\b",
    r"\b(hurt|cut)\s+myself\b",
    r"\bsuicide\b",
    r"\bself[-\s]*harm\b",
    r"\b(i\s+want\s+to|im\s+going\s+to|gonna)\s*(die|end\s*(it|everything)|kill\s*myself)\b",
]
OTHER_HARM_PATTERNS = [
    r"\bkill\s+(him|her|them|you|people)\b",
    r"\bstab\s+(him|her|them|you)\b",
    r"\bshoot\s+(him|her|them|you)\b",
    r"\bhurt\s+(him|her|them|you)\b",
    r"\b(i\s+want\s+to|im\s+going\s+to|gonna)\s*(hurt|kill|stab|shoot)\b",
]
_self_harm_re = re.compile("|".join(SELF_HARM_PATTERNS), re.I)
_other_harm_re = re.compile("|".join(OTHER_HARM_PATTERNS), re.I)

# ---------------------------
# Groq (OpenAI-compatible) LLM second opinion via chat/completions
# ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ENABLE_OPENAI_MODERATION = os.getenv("ENABLE_OPENAI_MODERATION", "0").lower() in {"1", "true", "yes"}

async def _moderation_label_llm(text: str) -> Optional[Crisis]:
    """
    Use chat/completions to classify into: self_harm | other_harm | none.
    Works on Groq's OpenAI-compatible endpoint.
    """
    if not (ENABLE_OPENAI_MODERATION and OPENAI_API_KEY):
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a strict safety classifier. "
                                "Read the user's message and output ONLY one label:\n"
                                "self_harm = intent/ideation/instruction to harm self\n"
                                "other_harm = intent/ideation/instruction to harm others\n"
                                "none = neither applies\n"
                                "Return exactly one token: self_harm, other_harm, or none."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0,
                },
            )
            r.raise_for_status()
            out = (r.json()["choices"][0]["message"]["content"] or "").strip().lower()
            if "self_harm" in out or out == "selfharm":
                return "self_harm"
            if "other_harm" in out or out in {"harm_others", "violence", "violent"}:
                return "other_harm"
            if out == "none":
                return "none"
    except Exception:
        # Fail open to None so rules still apply
        return None
    return None

# ---------------------------
# Public API
# ---------------------------
def detect_crisis(user_text: str) -> Crisis:
    """Fast, deterministic rules; catches slang/obfuscations."""
    if not user_text:
        return "none"
    n = _normalize(user_text)
    e = _expand_slang(n)

    if _self_harm_re.search(e):
        return "self_harm"
    if _other_harm_re.search(e):
        return "other_harm"

    if "kill myself" in e and "microsoft kms" not in e and "key management service" not in e:
        return "self_harm"

    return "none"

async def detect_crisis_with_moderation(user_text: str) -> Crisis:
    """
    Combined signal: rules first (low-latency), then LLM second opinion.
    """
    rule = detect_crisis(user_text)
    if rule != "none":
        return rule
    mod = await _moderation_label_llm(user_text)
    return mod or "none"
