# app/main.py
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
import json
import asyncio
import traceback
from typing import List, Dict, Optional

import httpx
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import desc
from sqlalchemy.orm import Session, sessionmaker
from pydantic import BaseModel

from .db import Base, engine, get_db
from .models import Interaction, Strategy  # ensure Strategy table is created
from .schemas import ChatRequest, ChatResponse
from .orchestrator import run_pipeline
from .agents.mood import _pipe, detect_mood
from .agents.safety import detect_crisis
from .prompts import ENCOURAGEMENT_SYSTEM, CRISIS_MESSAGE_SELF, CRISIS_MESSAGE_OTHERS
from .auth import router as auth_router  # Google OAuth endpoints

# Coping strategy suggestors
from .agents.strategy import suggest_strategy, suggest_resources, Crisis

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(title="Agentic Mental Health Companion")

# --- CORS (env-driven with sensible local fallbacks) ---
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5175").rstrip("/")
_extra_origins = [
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5178",
    "http://127.0.0.1:5178",
]
allow_origins = list({FRONTEND_ORIGIN, *_extra_origins})

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Secure session cookie for Google login (adjust for prod) ---
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",       # use "none" with HTTPS for cross-site prod
    https_only=False,       # set True in production with HTTPS
)

# Ensure tables exist (no-op if already exist)
Base.metadata.create_all(bind=engine)

# include /api/auth/google, /api/auth/me, /api/auth/logout, etc.
app.include_router(auth_router)

# -----------------------------------------------------------------------------
# Root redirect so landing on backend "/" doesn't show 404
# -----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def index():
    return RedirectResponse(url=f"{FRONTEND_ORIGIN}/")

# -----------------------------------------------------------------------------
# Startup: warm model + seed strategies if empty
# -----------------------------------------------------------------------------
SessionLocal = sessionmaker(bind=engine)

def _seed_strategies_if_empty() -> None:
    """Populate mh_strategies with a few vetted starter rows if it's empty."""
    try:
        db = SessionLocal()
        try:
            count = db.query(Strategy).count()
            if count > 0:
                return

            rows = [
                Strategy(
                    id="breathing.box_60s",
                    tag="breathing",
                    label="Box Breathing (1 min)",
                    step="Inhale 4, hold 4, exhale 4, hold 4 — repeat 4 times.",
                    why="Slows arousal and steadies attention.",
                    moods="distress,anger,sadness,neutral",
                    keywords="breath,panic,anxiety,inhale,exhale,calm",
                    time_cost_sec=60,
                    source_name="NHS (summary)",
                    source_url="https://www.nhs.uk/mental-health/self-help/guides-tools-and-activities/breathing-exercises-for-stress/",
                    reviewer="team",
                    last_reviewed_at="2025-09-26",
                ),
                Strategy(
                    id="grounding.54321",
                    tag="grounding",
                    label="5–4–3–2–1 Grounding",
                    step="Name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.",
                    why="Shifts attention to senses and reduces rumination.",
                    moods="distress,sadness,neutral",
                    keywords="ground,present,overthink,panic,dissociate",
                    time_cost_sec=90,
                    source_name="NHS (summary)",
                    source_url="https://www.nhs.uk/mental-health/",
                    reviewer="team",
                    last_reviewed_at="2025-09-26",
                ),
                Strategy(
                    id="walk.window_2m",
                    tag="walk",
                    label="Window / step away",
                    step="Look out a window or walk for 2 minutes and notice 3 details.",
                    why="Movement + visual variety can regulate mood.",
                    moods="anger,sadness,neutral,joy",
                    keywords="walk,outside,window,restless,stuck",
                    time_cost_sec=120,
                    source_name="WHO (summary)",
                    source_url="https://www.who.int/",
                    reviewer="team",
                    last_reviewed_at="2025-09-26",
                ),
            ]
            db.add_all(rows)
            db.commit()
            print("✅ Seeded mh_strategies with starter rows")
        finally:
            db.close()
    except Exception as e:
        print("⚠️ Seeding mh_strategies skipped:", e)

@app.on_event("startup")
async def warm_models():
    # Warm emotion model (cached by lru_cache)
    try:
        pipe = _pipe()
        pipe("hello")
        print("✅ Mood model warmed")
    except Exception as e:
        print("⚠️ Could not warm mood model:", e)

    # Seed DB-backed strategies once (safe no-op if not empty)
    _seed_strategies_if_empty()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def fetch_history_as_messages(db: Session, user_id: str, limit: int = 8) -> List[Dict[str, str]]:
    """Return last `limit` turns in OpenAI-style message format."""
    rows = (
        db.query(Interaction)
        .filter(Interaction.user_id == user_id)
        .order_by(desc(Interaction.created_at))
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))  # oldest -> newest

    messages: List[Dict[str, str]] = []
    for r in rows:
        if r.user_text:
            messages.append({"role": "user", "content": r.user_text})
        if r.encouragement:
            messages.append({"role": "assistant", "content": r.encouragement})
    return messages

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

async def _openai_stream(messages: List[Dict[str, str]]):
    """
    Stream plain-text tokens from OpenAI/Groq Chat Completions.
    Yields text chunks.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": OPENAI_MODEL, "stream": True, "messages": messages, "temperature": 0.7},
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                    delta = data["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                        await asyncio.sleep(0)
                except Exception:
                    continue

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

async def _handle_chat(body: ChatRequest, request: Request, db: Session) -> ChatResponse:
    """Shared core for /chat and /api/chat."""
    user_id = body.user_id or "anon"
    history = fetch_history_as_messages(db, user_id, limit=8)

    # Run the agent pipeline (handles crisis internally too)
    result = await run_pipeline(body.user_text, history=history)

    # Logged-in user from session (set by Google callback)
    ses_user: Optional[dict] = request.session.get("user")
    user_sub = ses_user.get("sub") if ses_user else None

    # Persist minimal interaction record (backwards compatible)
    values = dict(
        user_id=user_id,
        user_text=body.user_text,
        detected_mood=result["mood"],
        chosen_strategy=result["strategy"],
        encouragement=result["encouragement"],
        safety_flag="true" if result["crisis_detected"] else "false",
    )
    if hasattr(Interaction, "user_sub"):
        values["user_sub"] = user_sub

    db.add(Interaction(**values))
    db.commit()

    return ChatResponse(**result)

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request, db: Session = Depends(get_db)):
    """Non-streaming chat (original path)."""
    return await _handle_chat(body, request, db)

@app.post("/api/chat")
async def chat_api(body: ChatRequest, request: Request, db: Session = Depends(get_db)):
    """
    Non-streaming chat (frontend usually calls this through Vite proxy).
    Wrapped with try/except to surface readable errors instead of a blind 500.
    """
    try:
        return await _handle_chat(body, request, db)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "chat_failed", "message": str(e), "type": e.__class__.__name__},
        )

@app.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request, db: Session = Depends(get_db)):
    """
    Streaming chat endpoint that yields tokens as they're generated.
    Frontend can read incremental chunks and render in real time.
    """
    user_id = body.user_id or "anon"

    # Safety short-circuit using only the new user text
    crisis_type = detect_crisis(body.user_text)  # "none" | "self_harm" | "other_harm"
    if crisis_type != "none":
        crisis_message = CRISIS_MESSAGE_SELF if crisis_type == "self_harm" else CRISIS_MESSAGE_OTHERS

        async def crisis_gen():
            yield crisis_message

        # persist crisis response
        values = dict(
            user_id=user_id,
            user_text=body.user_text,
            detected_mood="unknown",
            chosen_strategy="",
            encouragement=crisis_message,
            safety_flag="true",
        )
        ses_user: Optional[dict] = request.session.get("user")
        user_sub = ses_user.get("sub") if ses_user else None
        if hasattr(Interaction, "user_sub"):
            values["user_sub"] = user_sub

        db.add(Interaction(**values))
        db.commit()
        return StreamingResponse(crisis_gen(), media_type="text/plain")

    # Build short context
    history = fetch_history_as_messages(db, user_id, limit=8)
    messages = [{"role": "system", "content": ENCOURAGEMENT_SYSTEM}] + history + [
        {"role": "user", "content": body.user_text}
    ]

    accumulated = {"text": ""}

    async def generator():
        async for chunk in _openai_stream(messages):
            accumulated["text"] += chunk
            yield chunk
        # after stream completes, store one interaction row
        values = dict(
            user_id=user_id,
            user_text=body.user_text,
            detected_mood=detect_mood(body.user_text),
            chosen_strategy="",
            encouragement=accumulated["text"],
            safety_flag="false",
        )
        ses_user: Optional[dict] = request.session.get("user")
        user_sub = ses_user.get("sub") if ses_user else None
        if hasattr(Interaction, "user_sub"):
            values["user_sub"] = user_sub

        db.add(Interaction(**values))
        db.commit()

    return StreamingResponse(generator(), media_type="text/plain")

# -----------------------------------------------------------------------------
# Coping strategy endpoints (API + aliases)
# -----------------------------------------------------------------------------
class StrategyIn(BaseModel):
    mood: str = "neutral"
    user_text: str
    crisis: Crisis = "none"
    history: Optional[List[Dict[str, str]]] = None
    exclude_ids: Optional[List[str]] = None

@app.post("/api/suggest/strategy")
async def api_suggest_strategy(inp: StrategyIn):
    step = await suggest_strategy(
        mood=inp.mood,
        user_text=inp.user_text,
        crisis=inp.crisis,
        history=inp.history,
    )
    return {"strategy": step}

@app.post("/api/suggest/resources")
async def api_suggest_resources(inp: StrategyIn):
    opts = await suggest_resources(
        mood=inp.mood,
        user_text=inp.user_text,
        crisis=inp.crisis,
        history=inp.history,
        exclude_ids=inp.exclude_ids,
    )
    return json.loads(opts) if opts else {"options": [], "needs_clinician": False}

# Aliases without /api prefix
@app.post("/suggest/strategy")
async def alias_suggest_strategy(inp: StrategyIn):
    return await api_suggest_strategy(inp)

@app.post("/suggest/resources")
async def alias_suggest_resources(inp: StrategyIn):
    return await api_suggest_resources(inp)
