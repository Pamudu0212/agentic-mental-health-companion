# app/routes_users.py
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

router = APIRouter(prefix="/api/user", tags=["user"])

class ProfileIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    timezone: Optional[str] = Field(None, max_length=64)

@router.get("/profile")
def get_profile(request: Request, db: Session = Depends(get_db)):
    ses = request.session.get("user")
    if not ses:
        return JSONResponse({"error": "not_logged_in"}, status_code=401)
    u = db.query(User).filter(User.sub == ses["sub"]).first()
    return {
        "email": u.email,
        "name": u.name,
        "picture": u.picture,
        "timezone": u.timezone,
        "profile_complete": bool(u.profile_complete),
    }

@router.post("/profile")
def update_profile(body: ProfileIn, request: Request, db: Session = Depends(get_db)):
    ses = request.session.get("user")
    if not ses:
        return JSONResponse({"error": "not_logged_in"}, status_code=401)
    u = db.query(User).filter(User.sub == ses["sub"]).first()
    if not u:
        return JSONResponse({"error": "user_missing"}, status_code=400)
    if body.name is not None:
        u.name = body.name.strip()
    if body.timezone is not None:
        u.timezone = body.timezone.strip() or "UTC"
    # mark complete once they submit at least once
    u.profile_complete = True
    db.commit()
    return {"ok": True, "profile_complete": True}
