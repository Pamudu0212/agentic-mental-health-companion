# app/agents/safety.py
import re
from typing import Literal

CrisisType = Literal["none", "self_harm", "other_harm"]

# Handle "I'm" variants (apostrophe / no apostrophe / spaces)
IM = r"(?:i\s*am|i'?m|im)"

def _normalize(text: str) -> str:
    t = text.lower()
    t = t.replace("’", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t.strip())
    return t

# -----------------------------------------------------------------------------
# Fast substring checks (high precision)
# -----------------------------------------------------------------------------
def _fast_other_harm_hits(t: str) -> bool:
    """
    Catch common 'im danger' / 'i am dangerous' / 'im a threat (to others)' cases.
    """
    # direct declarations
    if ("im danger" in t) or ("i am danger" in t) or ("im dangerous" in t) or ("i am dangerous" in t):
        return True
    if ("im a danger" in t) or ("i am a danger" in t) or ("im a threat" in t) or ("i am a threat" in t):
        return True

    # explicit targets with "danger/threat to ..."
    if any(kw in t for kw in ["danger to", "dangerous to", "threat to"]):
        if any(trg in t for trg in [
            "others", "people", "everyone", "someone", "them", "him", "her",
            "public", "classmates", "coworkers", "family"
        ]):
            return True

    return False

# -----------------------------------------------------------------------------
# Regex backstops (cover euphemisms/paraphrases and mass-violence variants)
# -----------------------------------------------------------------------------

# Self-harm (including euphemisms)
SELF_HARM_PATTERNS = [
    r"\b(kill myself|end my life|end it all|i want to die|i want to end it)\b",
    r"\b(suicide|die by suicide|self[-\s]?harm)\b",
    r"\b(hurt myself|cut myself|i might hurt myself|i'?m going to hurt myself)\b",
    rf"\b{IM}\s+(?:a\s+)?danger(?:ous)?\s+to\s+(?:myself|me)\b",
    r"\b(can'?t go on|no reason to live)\b",
    # euphemisms
    r"\b(unalive\s+myself|end\s+my\s+own\s+life|take\s+my\s+own\s+life)\b",
]

# Other-harm (including euphemisms, mass-violence, and common misspellings)
OTHER_HARM_PATTERNS = [
    # direct harms
    r"\b(kill\s+(?:them|him|her|someone|people|others|everyone))\b",
    r"\b(?:hurt|harm|attack|stab|shoot)\s+(?:someone|people|others|him|her|them|everyone)\b",
    r"\b(homicidal|violent|violance)\s+(?:urges|thoughts)?\b",

    # “I'm a danger/dangerous/threat (to others)”
    rf"\b{IM}\s+(?:a\s+)?(?:danger|dangerous|threat)(?:\s+to\s+(?:others|people|everyone|them|someone))?\b",

    # “I might / am going to / will hurt|harm|attack …”
    rf"\b{IM}\s+(?:might|am going to|will)\s+(?:hurt|harm|attack|stab|shoot)\s+(?:someone|people|others|him|her|them|everyone)\b",

    # euphemisms: “unalive someone”, “take a life”, “end someone’s life”
    r"\b(unalive|end|take)\s+(?:someone|people|others|him|her|them|everyone|a\s+life)\b",
    r"\b(take\s+(?:someone's|their)\s+life)\b",
    r"\b(end\s+(?:someone's|their)\s+life)\b",

    # mass-violence / school-shooting / bombing phrasings
    r"\b(shoot\s*up|shoot-up)\s+(?:a\s+)?(school|mall|store|place|church|synagogue|office|work|public|crowd)\b",
    r"\b(school\s+shoot(?:ing|er))\b",
    r"\b(mass\s+(?:shooting|murder|violence|attack))\b",
    r"\b(blow\s+up|bomb|detonate)\s+(?:a\s+)?(school|building|place|office|train|bus|airport|mall|crowd)\b",
    r"\b(knife|stab)\s+(?:people|others|someone|them|classmates)\b",
    r"\b(assault|rape)\s+(?:someone|people|her|him|them)\b",
]

def detect_crisis(text: str) -> CrisisType:
    """
    Returns one of: "none", "self_harm", "other_harm".
    """
    t = _normalize(text)

    # 1) fast, precise hits
    if _fast_other_harm_hits(t):
        return "other_harm"

    # 2) regex backstops
    for pat in SELF_HARM_PATTERNS:
        if re.search(pat, t):
            return "self_harm"

    for pat in OTHER_HARM_PATTERNS:
        if re.search(pat, t):
            return "other_harm"

    # 3) final safety backstop:
    # if a danger/threat word AND a third-party noun co-occur, treat as other_harm
    if re.search(r"\b(danger|dangerous|threat)\b", t) and re.search(
        r"\b(others|people|someone|everyone|them|him|her|public|classmates|coworkers|family)\b", t
    ):
        return "other_harm"

    return "none"
