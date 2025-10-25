# app/auth.py
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, PlainTextResponse
from authlib.integrations.starlette_client import OAuth

from .db import SessionLocal
from .models import User

router = APIRouter()

# --- Settings ---------------------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5175").rstrip("/")

REDIRECT_PATH = "/api/auth/google/callback"
REDIRECT_URI = f"{BACKEND_URL}{REDIRECT_PATH}"  # MUST include http:// or https://

# --- OAuth client -----------------------------------------------------------
oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# --- Small helpers ----------------------------------------------------------
def _session_user(request: Request) -> Optional[dict]:
    return request.session.get("user")


def _set_session_user(request: Request, profile: dict) -> None:
    request.session["user"] = profile


def _clear_session_user(request: Request) -> None:
    request.session.pop("user", None)


# --- Routes -----------------------------------------------------------------
@router.get("/api/auth/me")
async def me(request: Request):
    ses = _session_user(request)
    if not ses:
        return JSONResponse({})
    db = SessionLocal()
    try:
        from .models import User
        u = db.query(User).filter(User.sub == ses["sub"]).first()
        return JSONResponse({
            "sub": ses["sub"],
            "email": ses.get("email"),
            "name": ses.get("name"),
            "picture": ses.get("picture"),
            "profile_complete": bool(u.profile_complete) if u else False,
            "timezone": u.timezone if u else "UTC",
        })
    finally:
        db.close()


@router.get("/api/auth/google")
async def google_login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return PlainTextResponse(
            "Google OAuth is not configured (missing GOOGLE_CLIENT_ID/SECRET).",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Validate REDIRECT_URI format
    if not REDIRECT_URI.startswith(('http://', 'https://')):
        print(f"❌ ERROR: REDIRECT_URI is malformed: {REDIRECT_URI}")
        return PlainTextResponse(
            "Server configuration error: Invalid redirect URI.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    print(f"[Auth] Starting login. BACKEND_URL={BACKEND_URL}  REDIRECT_URI={REDIRECT_URI}")

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    # Only pass redirect_uri here; do NOT pass it again in the callback.
    resp: RedirectResponse = await oauth.google.authorize_redirect(
        request,
        REDIRECT_URI,
        state=state,
        prompt="select_account",
    )
    # Fallback state cookie to survive some dev edge-cases
    resp.set_cookie(
        "oauth_state", state, max_age=300, httponly=True, secure=False, samesite="lax", path="/"
    )
    return resp


@router.get(REDIRECT_PATH)
async def google_callback(request: Request):
    # Debug what we received
    print("🔸 [Auth] Google callback hit")
    print("Query params:", dict(request.query_params))
    print("Session contents:", dict(request.session))
    print("Cookies:", dict(request.cookies))

    # CSRF state verification (session or fallback cookie)
    state_query = request.query_params.get("state")
    state_session = request.session.get("oauth_state")
    state_cookie = request.cookies.get("oauth_state")

    state_ok = bool(
        state_query
        and ((state_session and state_query == state_session) or (state_cookie and state_query == state_cookie))
    )
    if not state_ok:
        return PlainTextResponse(
            "CSRF Warning! State not equal in request and response.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Exchange code for tokens; do NOT pass redirect_uri here again.
        # The OAuth client should remember it from the initial request.
        token = await oauth.google.authorize_access_token(request)
        print("[Auth] Token received keys:", list(token.keys()))

        # Try to parse id_token first; if missing, fall back to userinfo endpoint
        profile = None
        userinfo = None

        try:
            userinfo = await oauth.google.parse_id_token(request, token)
            print("[Auth] parse_id_token ok")
        except Exception as e:
            print("[Auth] parse_id_token failed:", e)
            # If id_token parsing fails, try to get userinfo from the endpoint
            try:
                # Use the full userinfo endpoint URL
                userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
                resp = await oauth.google.get(userinfo_url, token=token)
                userinfo = resp.json()
                print("[Auth] userinfo endpoint ok")
            except Exception as userinfo_error:
                print("[Auth] userinfo endpoint also failed:", userinfo_error)
                # If both methods fail, try to extract from the token directly
                if 'userinfo' in token:
                    userinfo = token['userinfo']
                    print("[Auth] Using userinfo from token")
                elif 'id_token' in token and isinstance(token['id_token'], dict):
                    userinfo = token['id_token']
                    print("[Auth] Using id_token from token as dict")

        if not userinfo:
            raise RuntimeError("Could not retrieve user information from Google")

        profile = {
            "sub": userinfo.get("sub"),
            "email": userinfo.get("email"),
            "name": userinfo.get("name") or userinfo.get("given_name"),
            "picture": userinfo.get("picture"),
        }
        if not profile["sub"]:
            raise RuntimeError("No 'sub' in userinfo/id_token")

        # Save to session and clear one-time state
        _set_session_user(request, profile)
        request.session.pop("oauth_state", None)

        # Upsert DB user
        db = SessionLocal()
        try:
            from .models import User
            u = db.query(User).filter(User.sub == profile["sub"]).first()
            if not u:
                u = User(
                    sub=profile["sub"],
                    email=profile.get("email"),
                    name=profile.get("name"),
                    picture=profile.get("picture"),
                    timezone="Asia/Colombo",
                    profile_complete=False,
                )
                db.add(u)
            else:
                u.email = profile.get("email")
                u.name = profile.get("name")
                u.picture = profile.get("picture")
            db.commit()
        finally:
            db.close()

        # Redirect back to app and clear fallback cookie
        resp = RedirectResponse(url=f"{FRONTEND_ORIGIN}/", status_code=status.HTTP_302_FOUND)
        resp.delete_cookie("oauth_state", path="/")
        return resp

    except Exception as e:
        print("❌ [Auth] OAuth callback failed:", repr(e))
        import traceback
        traceback.print_exc()
        return PlainTextResponse(f"OAuth callback failed: {e}", status_code=status.HTTP_400_BAD_REQUEST)


@router.post("/api/auth/logout")
async def logout(request: Request):
    _clear_session_user(request)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("oauth_state", path="/")
    return resp