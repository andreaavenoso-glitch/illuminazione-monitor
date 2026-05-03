"""Password hashing + JWT helpers.

bcrypt for passwords (slow on purpose), HS256 JWT for stateless sessions.
Tokens carry ``sub`` (user id), ``role``, ``email`` and standard ``exp``.

We use the ``bcrypt`` library directly instead of passlib to avoid the
``passlib + bcrypt 4.x + Python 3.12`` compatibility issue (passlib 1.7.4
inspects ``bcrypt.__about__`` which was removed in bcrypt 4.1+).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt
from app.core.config import get_settings


def hash_password(plaintext: str) -> str:
    """Hash with bcrypt cost-12. Returns the encoded $2b$ string."""
    salted = bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return salted.decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    if not hashed or not isinstance(hashed, str):
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
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
