# app/schemas.py
from typing import Optional
from pydantic import BaseModel, Field

class Safety(BaseModel):
    # 'safe' | 'watch' | 'crisis_self' | 'crisis_others'
    level: str
    reason: Optional[str] = None

class StrategySource(BaseModel):
    # Source metadata for the suggested strategy (if any)
    name: Optional[str] = None   # e.g., "NHS", "NICE", "WHO"
    url: Optional[str] = None    # canonical source page

class ChatRequest(BaseModel):
    user_text: str = Field(..., min_length=1, max_length=4000)
    user_id: Optional[str] = None  # frontend may omit; backend defaults to "anon"

class ChatResponse(BaseModel):
    mood: str
    strategy: str
    encouragement: str
    crisis_detected: bool
    safety: Safety

    # Whether we intentionally offered a concrete micro-step this turn
    advice_given: bool = False

    # Provenance for the strategy so the UI can show a "View source" button
    strategy_source: Optional[StrategySource] = None

    # Extra context for UI: brief rationale & human-friendly label of the step
    strategy_why: Optional[str] = None
    strategy_label: Optional[str] = None
