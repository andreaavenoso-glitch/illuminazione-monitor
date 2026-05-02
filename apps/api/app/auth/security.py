"""Password hashing + JWT helpers.

bcrypt for passwords (slow on purpose), HS256 JWT for stateless sessions.
Tokens carry ``sub`` (user id), ``role``, ``email`` and standard ``exp``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from app.core.config import get_settings
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plaintext: str) -> str:
    return _pwd_context.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plaintext, hashed)
    except Exception:  # noqa: BLE001 — passlib raises a few distinct types
        return False


def create_access_token(
    *,
    user_id: UUID | str,
    role: str,
    email: str,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(tz=UTC)
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_access_token_minutes
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
