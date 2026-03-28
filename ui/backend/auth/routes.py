from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from scripts.config import (
    FRONTEND_SUCCESS_REDIRECT,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
)
from ui.backend.session_store import read_session, write_session

router = APIRouter(prefix="/api/auth/google", tags=["google-auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.readonly",
]
OAUTH_STATE = "uci-nature-demo"


def _invalidate_google_auth_session(session: dict, google_auth: dict) -> None:
    session["google_auth"] = {
        "authenticated": False,
        "user": google_auth.get("user"),
        "access_token": None,
        "refresh_token": google_auth.get("refresh_token"),
        "expires_at": google_auth.get("expires_at"),
    }
    session["drive_connected"] = False


def _refresh_google_access_token(refresh_token: str) -> Optional[dict]:
    if not refresh_token:
        return None

    try:
        token_res = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
    except requests.RequestException:
        return None

    if not token_res.ok:
        return None

    token_data = token_res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return None

    expires_in = token_data.get("expires_in")
    expires_at = None
    if expires_in:
        try:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            ).isoformat()
        except Exception:
            expires_at = None

    return {
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token") or refresh_token,
        "expires_at": expires_at,
    }


def get_google_auth_state(session: Optional[dict] = None):
    session = session if session is not None else read_session()
    google_auth = session.get("google_auth") or {}

    access_token = google_auth.get("access_token")
    refresh_token = google_auth.get("refresh_token")
    authenticated = bool(google_auth.get("authenticated") and access_token)
    expires_at = google_auth.get("expires_at")
    session_changed = False

    should_refresh = False
    if refresh_token and (not access_token or not authenticated):
        should_refresh = True
    elif access_token and expires_at:
        try:
            expires_dt = datetime.fromisoformat(expires_at)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)

            if expires_dt <= datetime.now(timezone.utc):
                should_refresh = bool(refresh_token)
                if not should_refresh:
                    authenticated = False
                    access_token = None
                    _invalidate_google_auth_session(session, google_auth)
                    session_changed = True
        except Exception:
            pass

    if should_refresh:
        refreshed_auth = _refresh_google_access_token(refresh_token)
        if refreshed_auth:
            session["google_auth"] = {
                "authenticated": True,
                "user": google_auth.get("user"),
                "access_token": refreshed_auth["access_token"],
                "refresh_token": refreshed_auth["refresh_token"],
                "expires_at": refreshed_auth["expires_at"],
            }
            access_token = refreshed_auth["access_token"]
            authenticated = True
            session_changed = True
        else:
            authenticated = False
            access_token = None
            _invalidate_google_auth_session(session, google_auth)
            session_changed = True

    if session_changed:
        write_session(session)
        google_auth = session.get("google_auth") or {}

    return {
        "authenticated": authenticated,
        "access_token": access_token,
        "refresh_token": google_auth.get("refresh_token"),
        "expires_at": google_auth.get("expires_at"),
        "user": google_auth.get("user"),
    }


def _build_auth_url() -> str:
    params = {
        "client_id": GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": OAUTH_STATE,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


@router.get("/login")
def google_login():
    return {"auth_url": _build_auth_url()}


@router.get("/start")
def google_start():
    return {"auth_url": _build_auth_url()}


@router.get("/callback")
def google_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    if state != OAUTH_STATE:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        token_res = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Google token endpoint: {exc}",
        ) from exc

    if not token_res.ok:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to exchange Google OAuth code: {token_res.text}",
        )

    token_data = token_res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Google OAuth access token missing")

    try:
        userinfo_res = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Google profile endpoint: {exc}",
        ) from exc

    if not userinfo_res.ok:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to load Google profile: {userinfo_res.text}",
        )

    google_user = userinfo_res.json()

    session = read_session()
    previous_google_user = ((session.get("google_auth") or {}).get("user") or {}).get("email")
    new_google_user = google_user.get("email")

    expires_in = token_data.get("expires_in")
    expires_at = None
    if expires_in:
        try:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            ).isoformat()
        except Exception:
            expires_at = None

    session["google_auth"] = {
        "authenticated": True,
        "user": {
            "email": google_user.get("email"),
            "name": google_user.get("name"),
            "picture": google_user.get("picture"),
        },
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
    }

    if previous_google_user and previous_google_user != new_google_user:
        session["selected_drive_folder"] = None
        session["drive_connected"] = False
        session["drive_name"] = None
        session["drive_email"] = None
    write_session(session)

    return RedirectResponse(url=FRONTEND_SUCCESS_REDIRECT, status_code=302)


@router.get("/me")
def google_me():
    google_auth = get_google_auth_state()
    return {
        "authenticated": bool(google_auth.get("authenticated")),
        "user": google_auth.get("user"),
    }


@router.post("/logout")
def google_logout():
    session = read_session()
    session["google_auth"] = {
        "authenticated": False,
        "user": None,
        "access_token": None,
        "refresh_token": None,
        "expires_at": None,
    }
    session["drive_connected"] = False
    session["selected_drive_folder"] = None
    write_session(session)

    return {"message": "Logged out from Google"}
