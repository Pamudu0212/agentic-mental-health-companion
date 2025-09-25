# app/agents/resources.py
from __future__ import annotations
import json, os, re
from typing import TypedDict, Literal, List, Dict, Any

Type = Literal["video", "article", "book"]

class Resource(TypedDict, total=False):
    id: str
    type: Type
    title: str
    url: str
    duration: str
    language: str
    moods: List[str]
    keywords: List[str]
    why: str
    cautions: str
    source: str

# --- where we load the big catalog ---
CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "resources.json")

# base (optional) seeds; keep a couple in code so you have something even if the JSON is missing
SEED: List[Resource] = [
    {
        "id": "yt-box-breathing-2m",
        "type": "video",
        "title": "Box Breathing (4x4) — 2-minute guide",
        "url": "https://www.youtube.com/watch?v=tEmt1Znux58",
        "duration": "2m",
        "language": "en",
        "moods": ["anxiety","distress","overwhelm","panic"],
        "keywords": ["breathing","box breathing","calm","arousal","heart racing"],
        "why": "Paced breathing may lower arousal and steady attention.",
        "cautions": "Stop if dizzy; skip with severe respiratory issues.",
        "source": "YouTube",
    }
]

def _normalize_item(x: Dict[str, Any]) -> Resource:
    def _list(v):
        if isinstance(v, list): return v
        if isinstance(v, str): return [s.strip() for s in re.split(r"[;,]", v) if s.strip()]
        return []
    return Resource(
        id=str(x.get("id","")).strip(),
        type=str(x.get("type","article")).strip(),  # type: ignore
        title=str(x.get("title","")).strip(),
        url=str(x.get("url","")).strip(),
        duration=str(x.get("duration","")).strip(),
        language=str(x.get("language","en")).strip(),
        moods=[s.lower() for s in _list(x.get("moods"))],
        keywords=[s.lower() for s in _list(x.get("keywords"))],
        why=str(x.get("why","")).strip(),
        cautions=str(x.get("cautions","")).strip(),
        source=str(x.get("source","")).strip(),
    )

def load_catalog() -> List[Resource]:
    items = list(SEED)
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for it in data.get("resources", []):
                items.append(_normalize_item(it))
    except FileNotFoundError:
        pass
    # de-dup by id
    seen = set(); dedup = []
    for it in items:
        if it["id"] in seen: continue
        seen.add(it["id"]); dedup.append(it)
    return dedup

CATALOG: List[Resource] = load_catalog()

# --- lightweight synonym map used by the matcher (expand anytime) ---
SYNONYMS: Dict[str, List[str]] = {
    "anxiety": ["anxious","worry","worried","panic","nervous","on edge","uneasy"],
    "panic": ["panic attack","heart racing","can’t breathe","breathless","shaky","sweaty"],
    "sleep": ["insomnia","can’t sleep","awake at night","tired","restless"],
    "study": ["exam","test","final","midterm","assignment","performance"],
    "tension": ["tight","stiff","sore","ache","pressure"],
    "overwhelm": ["overwhelmed","too much","can’t cope","stressed"],
    "rumination": ["overthinking","looping thoughts","stuck thinking","negative thoughts"],
    "breathing": ["breath","inhale","exhale","box breathing","4-7-8"],
    "sadness": ["down","low","blue","tearful"],
    "motivation": ["procrastination","can’t start","stuck","no energy"],
}
