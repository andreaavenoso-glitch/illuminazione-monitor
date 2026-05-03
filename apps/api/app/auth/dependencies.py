"""FastAPI dependencies: ``current_user`` decodes the bearer JWT and loads
the matching ``User`` row; ``require_role`` builds a dependency that 403s
if the user's role is below the required tier.
"""
from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import jwt
from app.auth.security import decode_access_token
from app.core.database import get_session
from fastapi import Depends, Header, HTTPException, status
from shared_models import User
from sqlalchemy.ext.asyncio import AsyncSession

# Role hierarchy: admin > analyst > viewer
ROLE_RANK = {"viewer": 1, "analyst": 2, "admin": 3}


async def current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing subject")
    try:
        user_id = UUID(sub)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Token subject is not a valid id") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    if not authorization:
        return None
    try:
        return await current_user(authorization=authorization, session=session)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Build a FastAPI dependency that allows any of the given roles
    (or any role above the lowest one in the hierarchy)."""
    allowed: Iterable[str] = roles or ("viewer",)
    min_rank = min(ROLE_RANK.get(r, 0) for r in allowed)

    async def _dep(user: User = Depends(current_user)) -> User:
        rank = ROLE_RANK.get(user.role, 0)
        if rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' insufficient for this endpoint",
            )
        return user

    return _dep
