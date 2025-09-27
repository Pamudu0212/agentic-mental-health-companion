# app/agents/mood.py
from functools import lru_cache
from typing import Dict

from transformers import pipeline


# Map the model's fine-grained labels into the simpler set your UI expects.
# You can tweak these to your taste.
LABEL_MAP: Dict[str, str] = {
    "anger": "anger",
    "disgust": "anger",     # hostile/aversion often pairs better with "anger" bucket
    "fear": "distress",     # clearer for mental-health UX than "fear"
    "sadness": "sadness",
    "joy": "joy",
    "neutral": "neutral",
    "surprise": "optimism", # or set to "neutral" if you prefer
}

MODEL_NAME = "j-hartmann/emotion-english-distilroberta-base"


@lru_cache(maxsize=1)
def _pipe():
    """
    Build & cache the HF pipeline once.
    The app imports this in startup to warm the model.
    """
    # return_all_scores=True lets us disambiguate cleanly
    return pipeline(
        "text-classification",
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        return_all_scores=True,
        truncation=True,
    )


def _map_label(label: str) -> str:
    """
    Map raw model label into our UI mood buckets.
    Unknown labels fall back to neutral.
    """
    return LABEL_MAP.get(label.lower(), "neutral")


def detect_mood(text: str) -> str:
    """
    Robust emotion detection using a modern GoEmotions-based model.
    Returns one of: anger | sadness | joy | neutral | optimism | distress
    (or whatever you configure in LABEL_MAP).
    """
    if not text or not text.strip():
        return "neutral"

    try:
        preds = _pipe()(text, truncation=True)
        # Pipeline returns a list with one item (for the single input),
        # which is a list of {label, score} dicts.
        scores = preds[0]
        top = max(scores, key=lambda x: x["score"])
        return _map_label(top["label"])
    except Exception:
        # In case of any runtime/download error, fail safely.
        return "neutral"
