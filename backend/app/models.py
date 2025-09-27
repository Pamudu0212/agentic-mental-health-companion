from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base


class User(Base):
    """
    Google-authenticated user.
    - sub: stable Google subject id (string)
    - email/name/picture: for convenience in your UI
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    sub = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    picture = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # backref to interactions
    interactions = relationship("Interaction", back_populates="user")


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # NEW: user_sub links to users.sub (nullable for anonymous)
    user_sub = Column(String(255), ForeignKey("users.sub"), index=True, nullable=True)

    # (optional) keep your old user_id for backward compatibility
    # You can remove this later after migrating data
    user_id = Column(String(64), index=True, default="anon")

    user_text = Column(Text)
    detected_mood = Column(String(32))
    chosen_strategy = Column(String(64))
    encouragement = Column(Text)
    safety_flag = Column(String(8))  # "true"/"false"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ORM relationship
    user = relationship("User", back_populates="interactions")


# ---- IR-backed coping strategy records ----
class Strategy(Base):
    __tablename__ = "mh_strategies"

    # Primary key: stable string id so you can upsert/import easily
    id = Column(String(255), primary_key=True)            # e.g., "breathing.box_60s"
    tag = Column(String(64), nullable=False, index=True)  # "breathing"
    label = Column(String(255), nullable=False)           # "Box Breathing (1 min)"
    step = Column(Text, nullable=False)                   # micro-step text (≤ ~200 chars)

    # Optional metadata for retrieval / provenance (Responsible AI)
    why = Column(Text, default="")                        # brief rationale
    moods = Column(Text, default="")                      # "distress,anger,neutral"
    keywords = Column(Text, default="")                   # "breath,panic,anxiety"
    intensity = Column(String(16), default="")            # "low|med|high" (optional)
    time_cost_sec = Column(Integer, default=60)
    contraindications = Column(Text, default="")          # e.g., "avoid breath-holding if ..."
    language = Column(String(8), default="en")            # "en" / "si" etc.

    source_name = Column(String(255), default="")         # e.g., "NHS"
    source_url = Column(String(1024), default="")         # canonical page for auditing
    last_reviewed_at = Column(String(32), default="")     # ISO date string
    reviewer = Column(String(255), default="")            # internal approver
