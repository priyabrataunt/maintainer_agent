from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken

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


class TokenStorageDisabled(Exception):
    """No TOKEN_ENCRYPTION_KEY is configured, so tokens cannot be stored or read."""


def _fernet() -> Fernet:
    key = settings.token_encryption_key.get_secret_value()
    if not key:
        raise TokenStorageDisabled("TOKEN_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode())


def token_storage_enabled() -> bool:
    return bool(settings.token_encryption_key.get_secret_value())


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str | None:
    """The plaintext token, or None if it cannot be decrypted (key changed or data tampered)."""
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return None
