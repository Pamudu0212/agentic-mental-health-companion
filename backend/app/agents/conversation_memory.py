# app/agents/conversation_memory.py
from __future__ import annotations
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
import json


@dataclass
class ConversationTurn:
    user_message: str
    agent_response: str
    mood: str
    timestamp: float
    crisis_level: str = "none"


class ConversationMemory:
    def __init__(self, session_id: str, max_turns: int = 20):
        self.session_id = session_id
        self.max_turns = max_turns
        self.turns: List[ConversationTurn] = []
        self.persistent_themes: List[str] = []

    def add_turn(self, user_message: str, agent_response: str, mood: str, crisis_level: str = "none"):
        """Add a conversation turn to memory"""
        turn = ConversationTurn(
            user_message=user_message,
            agent_response=agent_response,
            mood=mood,
            timestamp=time.time(),
            crisis_level=crisis_level
        )
        self.turns.append(turn)

        # Keep only recent turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

        self._update_persistent_themes()

    def _update_persistent_themes(self):
        """Detect recurring themes/moods across conversation"""
        recent_moods = [turn.mood for turn in self.turns[-8:] if turn.mood]
        if len(recent_moods) >= 3:
            mood_counts = {}
            for mood in recent_moods:
                mood_counts[mood] = mood_counts.get(mood, 0) + 1

            # If same mood appears in 60%+ of recent turns, it's persistent
            total_turns = len(recent_moods)
            self.persistent_themes = [
                mood for mood, count in mood_counts.items()
                if count / total_turns >= 0.6
            ]

    def get_recent_history(self, last_n: int = 6) -> List[Dict[str, str]]:
        """Get recent conversation history in message format"""
        history = []
        for turn in self.turns[-last_n:]:
            history.extend([
                {"role": "user", "content": turn.user_message},
                {"role": "assistant", "content": turn.agent_response}
            ])
        return history

    def get_mood_trend(self) -> Dict[str, any]:
        """Analyze mood patterns over time"""
        if not self.turns:
            return {"trend": "stable", "persistent_moods": []}

        return {
            "trend": self._calculate_mood_trend(),
            "persistent_moods": self.persistent_themes,
            "recent_crisis": any(turn.crisis_level != "none" for turn in self.turns[-3:])
        }

    def _calculate_mood_trend(self) -> str:
        """Simple trend analysis based on mood patterns"""
        moods = [turn.mood for turn in self.turns if turn.mood]
        if len(moods) < 3:
            return "stable"

        # Simple trend detection (you can enhance this)
        negative_moods = {"sad", "angry", "anxious", "stressed", "overwhelmed"}
        recent_negative = sum(1 for mood in moods[-3:] if mood in negative_moods)

        if recent_negative >= 2:
            return "deteriorating"
        elif recent_negative == 0:
            return "improving"
        else:
            return "stable"