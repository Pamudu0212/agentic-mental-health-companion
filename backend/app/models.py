# app/models.py
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
