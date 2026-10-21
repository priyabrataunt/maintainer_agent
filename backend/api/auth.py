import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import get_db
from backend.services.jwt import create_access_token
from backend.services.users import get_or_create_user

router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"
STATE_COOKIE_NAME = "oauth_state"
ACCESS_TOKEN_COOKIE_NAME = "access_token"


@router.get("/auth/login")
def login():
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "state": state,
            "scope": "read:user",
        }
    )
    response = RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{query}")
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        httponly=True,
        samesite="lax",
        max_age=600,
    )
    return response


def exchange_code_for_profile(
    code: str, transport: httpx.BaseTransport | None = None
) -> dict:
    """Exchange an OAuth `code` for an access token, then fetch the GitHub profile."""
    with httpx.Client(transport=transport) as client:
        token_response = client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret.get_secret_value(),
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=400, detail="GitHub OAuth code exchange failed"
            )

        user_response = client.get(
            f"{GITHUB_API_URL}/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_response.raise_for_status()
        return user_response.json()


@router.get("/auth/callback")
def callback(
    code: str,
    state: str,
    oauth_state: str | None = Cookie(default=None, alias=STATE_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if oauth_state is None or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    profile = exchange_code_for_profile(code)
    user = get_or_create_user(
        db,
        github_id=profile["id"],
        login=profile["login"],
        name=profile.get("name"),
    )

    token = create_access_token(user.id)
    response = JSONResponse(
        {"user_id": user.id, "github_id": user.github_id, "login": user.login}
    )
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return response
