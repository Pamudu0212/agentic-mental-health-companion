from transformers import pipeline
from functools import lru_cache

LABEL_MAP = {
    0: "anger",
    1: "joy",
    2: "optimism",
    3: "sadness",
}

@lru_cache(maxsize=1)
def _pipe():
    model_name = "cardiffnlp/twitter-roberta-base-emotion"
    clf = pipeline(
        "text-classification",
        model=model_name,
        tokenizer=model_name,
        top_k=1,
        truncation=True,
    )
    return clf

def detect_mood(text: str) -> str:
    try:
        out = _pipe()(text)
        # Depending on transformers version, out can be:
        # [{'label': 'joy', 'score': 0.78}]  OR  [[{'label': 'joy', 'score': 0.78}]]
        res = out[0]
        if isinstance(res, list) and res:
            label = res[0]["label"]
        elif isinstance(res, dict) and "label" in res:
            label = res["label"]
        else:
            label = "neutral"
        return label.lower()
    except Exception:
        return "neutral"
