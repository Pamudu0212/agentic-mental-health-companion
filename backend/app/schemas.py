from typing import Optional
from pydantic import BaseModel, Field

class Safety(BaseModel):
    level: str  # 'safe' | 'watch' | 'crisis_self' | 'crisis_others'
    reason: Optional[str] = None

class ChatRequest(BaseModel):
    user_text: str = Field(..., min_length=1, max_length=4000)
    user_id: Optional[str] = None  # frontend may omit; backend defaults to "anon"

class ChatResponse(BaseModel):
    mood: str
    strategy: str
    encouragement: str
    crisis_detected: bool
    safety: Safety
