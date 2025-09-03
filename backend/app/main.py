# app/main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Interaction
from .schemas import ChatRequest, ChatResponse
from .orchestrator import run_pipeline
from .agents.mood import _pipe  # warm-up

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(title="Agentic Mental Health Companion")

# CORS: allow Vite dev server and localhost (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create DB tables (no-op if already exist)
Base.metadata.create_all(bind=engine)

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
# Routes
# -----------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: Session = Depends(get_db)):
    # Run the agent pipeline
    result = await run_pipeline(body.user_text)

    # Persist minimal interaction record
    record = Interaction(
        user_id=body.user_id or "anon",
        user_text=body.user_text,
        detected_mood=result["mood"],
        chosen_strategy=result["strategy"],
        encouragement=result["encouragement"],
        safety_flag="true" if result["crisis_detected"] else "false",
    )
    db.add(record)
    db.commit()

    # Return the response payload
    return ChatResponse(**result)
