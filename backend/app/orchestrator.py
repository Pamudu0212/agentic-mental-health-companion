# app/orchestrator.py
from .agents.mood import detect_mood
from .agents.safety import detect_crisis
from .agents.strategy import suggest_strategy
from .agents.encouragement import encourage
from .prompts import CRISIS_MESSAGE

async def run_pipeline(user_text: str):
    # 1) Safety override first — if crisis, stop and return crisis message
    crisis = detect_crisis(user_text)
    if crisis:
        return {
            "mood": "unknown",
            "strategy": "",
            "encouragement": CRISIS_MESSAGE,
            "crisis_detected": True,
        }

    # 2) Mood → Strategy → Encouragement
    mood = detect_mood(user_text)
    strategy = await suggest_strategy(mood, user_text)
    encouragement = await encourage(user_text, mood, strategy)

    return {
        "mood": mood,
        "strategy": strategy,
        "encouragement": encouragement,
        "crisis_detected": False,
    }
