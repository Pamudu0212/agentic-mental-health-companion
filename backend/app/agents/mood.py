# app/agents/mood.py
from functools import lru_cache
from typing import Dict, List, Tuple
import os
from transformers import pipeline

# Map model's fine-grained labels to UI buckets
LABEL_MAP: Dict[str, str] = {
    "anger": "anger",
    "disgust": "anger",
    "fear": "distress",
    "sadness": "sadness",
    "joy": "joy",
    "neutral": "neutral",
}

MODEL_NAME = os.getenv("MOOD_MODEL", "j-hartmann/emotion-english-distilroberta-base")
CONF_THRESHOLD = float(os.getenv("MOOD_CONF_THRESHOLD", "0.55"))
HISTORY_K = int(os.getenv("MOOD_HISTORY", "5"))                  # how many prior user msgs
DECAY = float(os.getenv("MOOD_DECAY", "0.6"))                    # 0<DECAY<1 newer >> older
CURRENT_BOOST = float(os.getenv("MOOD_CURRENT_BOOST", "1.2"))    # extra weight on current msg

# --- Emoji priors (cheap signal to boost clarity) ---
EMOJI_PRIOR = {
    "joy":      set("😀😁😂🤣😊🙂😍🥳❤️✨👍"),
    "sadness":  set("😞😔😢😭🙁💔"),
    "anger":    set("😠😡🤬"),
    "distress": set("😨😰😥😓😱"),
}

def _apply_emoji_prior(scores: Dict[str, float], text: str, bump: float = 0.10) -> Dict[str, float]:
    hit = None
    for bucket, emojis in EMOJI_PRIOR.items():
        if any(e in text for e in emojis):
            hit = bucket
            break
    if hit:
        scores[hit] = scores.get(hit, 0.0) + bump
        total = sum(scores.values())
        if total > 0:
            for k in scores:
                scores[k] /= total
    return scores

@lru_cache(maxsize=1)
def _pipe():
    # Cached HF pipeline to avoid cold start per request
    return pipeline("text-classification", model=MODEL_NAME, top_k=None)

def _map_label(lbl: str) -> str:
    return LABEL_MAP.get(lbl.lower(), "neutral")

def _scores_for(text: str) -> Dict[str, float]:
    """Return bucket probabilities for a single text."""
    raw = _pipe()(text, truncation=True)[0]  # list of {label, score}
    out: Dict[str, float] = {}
    for item in raw:
        out[_map_label(item["label"])] = out.get(_map_label(item["label"]), 0.0) + float(item["score"])
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}

def _blend_with_decay(prob_seq: List[Dict[str, float]], decay: float = DECAY, current_boost: float = CURRENT_BOOST) -> Dict[str, float]:
    """
    Blend probs (oldest -> newest) with geometric decay so newer messages weigh more.
    weights_i = decay**(n-1-i); newest (i=n-1) gets 1.0 * current_boost.
    """
    n = len(prob_seq)
    if n == 1:
        return prob_seq[0]
    # build weights oldest->newest
    weights = [decay ** (n - 1 - i) for i in range(n)]
    weights[-1] *= max(current_boost, 0.0)  # emphasize current
    wsum = sum(weights) or 1.0
    weights = [w / wsum for w in weights]

    acc: Dict[str, float] = {}
    for probs, w in zip(prob_seq, weights):
        for k, v in probs.items():
            acc[k] = acc.get(k, 0.0) + w * v
    # normalize
    total = sum(acc.values()) or 1.0
    return {k: v / total for k, v in acc.items()}

def detect_mood_plus(
    text: str,
    history_user_texts: List[str] | None = None,
    return_extras: bool = False
) -> Tuple[str, float, List[Tuple[str, float]]]:
    """
    Stable mood detector with geometric decay weighting.
    Returns (mood_label, confidence, top3).
    - Looks at the current user message
    - Optionally blends up to the last HISTORY_K user messages for stability
    - Applies emoji priors on the current message only
    """
    if not text or not text.strip():
        return ("neutral", 1.0, [("neutral", 1.0)])

    # 1) current message: model scores + emoji prior
    current = _apply_emoji_prior(_scores_for(text), text)

    # 2) optional smoothing from conversation context (last K user turns)
    seq: List[Dict[str, float]] = []
    if history_user_texts:
        for h in history_user_texts[-HISTORY_K:]:  # oldest->newest within the window
            if h and h.strip():
                seq.append(_scores_for(h))
    seq.append(current)  # newest (current turn) at the end

    blended = _blend_with_decay(seq) if len(seq) > 1 else current

    # 3) top-3 + low-confidence handling
    rank = sorted(blended.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_p = rank[0]
    label = top_label if top_p >= CONF_THRESHOLD else "neutral"

    if return_extras:
        return (label, float(top_p), [(k, float(v)) for k, v in rank[:3]])
    return (label, float(top_p), [(k, float(v)) for k, v in rank[:3]])

# Backward-compatible API (single label only)
def detect_mood(text: str) -> str:
    label, _, _ = detect_mood_plus(text, history_user_texts=None, return_extras=False)
    return label
