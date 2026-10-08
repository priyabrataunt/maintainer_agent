import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import get_db
from backend.models.user import User
from backend.security import create_access_token, decode_access_token

router = APIRouter()

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
STATE_COOKIE = "oauth_state"
TOKEN_COOKIE = "access_token"
STATE_MAX_AGE_SECONDS = 600


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    github_id: int
    login: str
    avatar_url: str | None


def get_http_client():
    with httpx.Client(timeout=10) as client:
        yield client


def current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_access_token(access_token) if access_token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/auth/login")
def login():
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "state": state,
            "scope": "read:user",
        }
    )
    response = RedirectResponse(f"{AUTHORIZE_URL}?{query}")
    response.set_cookie(
        STATE_COOKIE, state, max_age=STATE_MAX_AGE_SECONDS, httponly=True, samesite="lax"
    )
    return response


@router.get("/auth/callback")
def callback(
    code: str,
    state: str,
    oauth_state: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
    http: httpx.Client = Depends(get_http_client),
):
    if not oauth_state or not secrets.compare_digest(state, oauth_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token_response = http.post(
        TOKEN_URL,
        data={
            "client_id": settings.github_oauth_client_id,
            "client_secret": settings.github_oauth_client_secret.get_secret_value(),
            "code": code,
            "redirect_uri": settings.github_oauth_redirect_uri,
        },
        headers={"Accept": "application/json"},
    )
    github_token = token_response.json().get("access_token")
    if token_response.status_code != 200 or not github_token:
        raise HTTPException(status_code=400, detail="GitHub rejected the OAuth code")

    profile_response = http.get(USER_URL, headers={"Authorization": f"Bearer {github_token}"})
    if profile_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not fetch GitHub profile")
    profile = profile_response.json()

    user = db.scalar(select(User).where(User.github_id == profile["id"]))
    if user is None:
        user = User(github_id=profile["id"])
        db.add(user)
    user.login = profile["login"]
    user.avatar_url = profile.get("avatar_url")
    db.commit()
    db.refresh(user)

    response = RedirectResponse("/me", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    response.set_cookie(
        TOKEN_COOKIE,
        create_access_token(user.id),
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(current_user)):
    return user
