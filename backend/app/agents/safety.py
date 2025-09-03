import re

CRISIS_PATTERNS = [
    r"\b(kill myself|end it all|want to die|suicide|hurt myself)\b",
    r"\b(can't go on|no reason to live)\b",
]

# Simple rule-based crisis detector; can be extended with an LLM or classifier
def detect_crisis(text: str) -> bool:
    t = text.lower()
    for pat in CRISIS_PATTERNS:
        if re.search(pat, t):
            return True
    return False
