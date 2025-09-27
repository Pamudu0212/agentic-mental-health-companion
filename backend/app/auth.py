# app/auth.py
from __future__ import annotations
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

@router.get("/google")
async def google_login(request: Request):
    redirect_uri = f"{BACKEND_URL}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.parse_id_token(request, token)

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name") or (email.split("@")[0] if email else None)
    picture = userinfo.get("picture")

    if not sub or not email:
        return JSONResponse({"error": "Invalid Google response"}, status_code=400)

    user = db.query(User).filter(User.sub == sub).one_or_none()
    if user is None:
        user = User(sub=sub, email=email, name=name, picture=picture)
        db.add(user)
    else:
        user.name = name
        user.picture = picture
    user.last_login = datetime.utcnow()
    db.commit()

    request.session["user"] = {
        "sub": user.sub,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    }
    return RedirectResponse(url="/")

@router.post("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return JSONResponse({"ok": True})

@router.get("/me")
async def me(request: Request):
    user = request.session.get("user")
    return JSONResponse(user or {})
