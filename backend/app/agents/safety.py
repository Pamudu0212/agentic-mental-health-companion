import re
from typing import Literal

CrisisType = Literal["none", "self_harm", "other_harm"]

# "I'm" variants (apostrophe/no apostrophe/spaces)
IM = r"(?:i\s*am|i'?m|im)"


def _normalize(text: str) -> str:
    """
    Lowercase, normalize punctuation, and squeeze whitespace to simplify matching.
    """
    t = text.lower()
    t = t.replace("’", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t.strip())
    return t


# ----------------------------
# Substring fast-paths first
# ----------------------------
def _fast_other_harm_hits(t: str) -> bool:
    """
    Catch the common 'im danger' / 'i am dangerous' / 'im a threat (to others)' cases
    really early with simple substring checks.
    """
    # Direct "danger/dangerous/threat" declarations after "i'm"
    if ("im danger" in t) or ("i am danger" in t) or ("im dangerous" in t) or ("i am dangerous" in t):
        return True

    if ("im a danger" in t) or ("i am a danger" in t) or ("im a threat" in t) or ("i am a threat" in t):
        return True

    # With explicit target
    if "danger to others" in t or "dangerous to others" in t or "threat to others" in t:
        return True
    if "danger to people" in t or "dangerous to people" in t or "threat to people" in t:
        return True
    if "danger to everyone" in t or "dangerous to everyone" in t or "threat to everyone" in t:
        return True
    if "danger to someone" in t or "danger to them" in t or "danger to him" in t or "danger to her" in t:
        return True

    return False


# ----------------------------
# Regex backstops (high recall)
# ----------------------------
SELF_HARM_PATTERNS = [
    r"\b(kill myself|end my life|end it all|i want to die|i want to end it)\b",
    r"\b(suicide|die by suicide|self[-\s]?harm)\b",
    r"\b(hurt myself|cut myself|i might hurt myself|i'?m going to hurt myself)\b",
    rf"\b{IM}\s+(?:a\s+)?danger(?:ous)?\s+to\s+(?:myself|me)\b",
    r"\b(can'?t go on|no reason to live)\b",
]

OTHER_HARM_PATTERNS = [
    r"\b(kill (?:them|him|her|someone|people|others|everyone))\b",
    r"\b(?:hurt|harm|attack|stab|shoot)\s+(?:someone|people|others|him|her|them|everyone)\b",
    r"\b(homicidal|violent (?:urges|thoughts))\b",

    # "I'm a danger/dangerous/threat (to others)" — regex backstop
    rf"\b{IM}\s+(?:a\s+)?(?:danger|dangerous|threat)(?:\s+to\s+(?:others|people|everyone|them|someone))?\b",

    # "I might/am going to/will hurt/harm/attack someone"
    rf"\b{IM}\s+(?:might|am going to|will)\s+(?:hurt|harm|attack|stab|shoot)\s+(?:someone|people|others|him|her|them|everyone)\b",
]


def detect_crisis(text: str) -> CrisisType:
    """
    Returns one of: "none", "self_harm", "other_harm".
    """
    t = _normalize(text)

    # ---- fast substring checks (high precision) ----
    if _fast_other_harm_hits(t):
        return "other_harm"

    # ---- regex backstops ----
    for pat in SELF_HARM_PATTERNS:
        if re.search(pat, t):
            return "self_harm"

    for pat in OTHER_HARM_PATTERNS:
        if re.search(pat, t):
            return "other_harm"

    # If both 'danger/dangerous/threat' and a third-party noun appear, err on safety
    if re.search(r"\b(danger|dangerous|threat)\b", t) and re.search(
        r"\b(others|people|someone|everyone|them|him|her)\b", t
    ):
        return "other_harm"

    return "none"


# ------------------------------------------------------------------
# Ambiguous-risk detector (new): not a confirmed crisis, but worrying
# ------------------------------------------------------------------
def detect_ambiguous_risk(text: str) -> bool:
    """
    Detects ambiguous “danger/threat” language that is not clearly
    self-harm or other-harm. Returns True for statements like:
      - “i’m danger”, “i am dangerous”, “danger”
      - “i feel like a threat”
    but only when the full crisis detector above returns "none".
    """
    t = _normalize(text)

    # If it's already a clear crisis, it's NOT ambiguous.
    if detect_crisis(t) != "none":
        return False

    # Bare ‘danger / dangerous / threat’ anywhere in the utterance.
    if re.search(r"\b(danger|dangerous|threat)\b", t):
        return True

    return False
