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
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Interaction
from .schemas import ChatRequest, ChatResponse
from .orchestrator import run_pipeline
from .agents.mood import _pipe, detect_mood  # warm-up + quick label
from .agents.safety import detect_crisis     # returns "none" | "self_harm" | "other_harm"
from .prompts import ENCOURAGEMENT_SYSTEM, CRISIS_MESSAGE_SELF, CRISIS_MESSAGE_OTHERS
from .auth import router as auth_router  # <-- Google OAuth endpoints

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(title="Agentic Mental Health Companion")

# CORS: prefer .env, keep your useful fallbacks
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5175").rstrip("/")
extra_origins = [
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5178",
    "http://127.0.0.1:5178",
]
allow_origins = list({FRONTEND_ORIGIN, *extra_origins})

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secure session cookie for Google login
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",       # good for dev; set "none" + HTTPS in cross-site prod
    https_only=False,      # set True in production with HTTPS
)

# Create DB tables (no-op if already exist)
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
# Startup: warm the HF emotion model once
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def warm_models():
    try:
        pipe = _pipe()      # build pipeline (cached by lru_cache)
        pipe("hello")       # quick inference to load weights
        print("✅ Mood model warmed")
    except Exception as e:
        print("⚠️ Could not warm mood model:", e)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def fetch_history_as_messages(db: Session, user_id: str, limit: int = 8) -> List[Dict[str, str]]:
    """
    Fetch the last `limit` turns and format them as OpenAI-style messages:
    [{role:'user'|'assistant', content:'...'}]
    """
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
            json={
                "model": OPENAI_MODEL,
                "stream": True,
                "messages": messages,
                "temperature": 0.7,
            },
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
                    # swallow malformed keepalives/etc
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
    # If your Interaction model has `user_sub`, populate it
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
