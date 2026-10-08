from datetime import datetime, timedelta, timezone

import jwt

from backend.config import settings

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    """Sign a JWT whose subject is the user id."""
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Return the user id in `token`, or None if it is invalid or expired."""
    secret = settings.jwt_secret.get_secret_value()
    if not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
