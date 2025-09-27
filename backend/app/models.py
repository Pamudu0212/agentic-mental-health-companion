# app/models.py
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

# ---- NEW: IR-backed coping strategy records ----
class Strategy(Base):
    __tablename__ = "mh_strategies"

    # Primary key: stable string id so you can upsert/import easily
    id = Column(String, primary_key=True)                 # e.g., "breathing.box_60s"
    tag = Column(String, nullable=False, index=True)      # "breathing"
    label = Column(String, nullable=False)                # "Box Breathing (1 min)"
    step = Column(Text, nullable=False)                   # micro-step text (≤ ~200 chars)

    # Optional metadata for retrieval / provenance (Responsible AI)
    why = Column(Text, default="")                        # brief rationale
    moods = Column(Text, default="")                      # "distress,anger,neutral"
    keywords = Column(Text, default="")                   # "breath,panic,anxiety"
    intensity = Column(String, default="")                # "low|med|high" (optional)
    time_cost_sec = Column(Integer, default=60)
    contraindications = Column(Text, default="")          # e.g., "avoid breath-holding if ..."
    language = Column(String, default="en")               # "en" / "si" etc.

    source_name = Column(String, default="")              # e.g., "NHS"
    source_url = Column(String, default="")               # canonical page for auditing
    last_reviewed_at = Column(String, default="")         # ISO date string
    reviewer = Column(String, default="")                 # internal approver
