from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from .db import Base

class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(String(64), index=True, default="anon")
    user_text = Column(Text)
    detected_mood = Column(String(32))
    chosen_strategy = Column(String(64))
    encouragement = Column(Text)
    safety_flag = Column(String(8))  # "true"/"false"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
