from uuid import UUID

from app.auth import current_user, hash_password, require_role, verify_password
from app.auth.security import create_access_token
from app.core.config import get_settings
from app.core.database import get_session
from app.core.rate_limit import limiter
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from shared_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,  # noqa: ARG001 — required by slowapi
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    repo = UserRepository(session)
    user = await repo.get_by_email(payload.email)
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    await repo.touch_last_login(user)
    await session.commit()

    settings = get_settings()
    token = create_access_token(user_id=user.id, role=user.role, email=user.email)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_token_minutes,
    )


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/users", response_model=list[UserRead])
async def list_users(
    active: bool | None = None,
    _admin: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[UserRead]:
    repo = UserRepository(session)
    users = await repo.list(active=active)
    return [UserRead.model_validate(u) for u in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    _admin: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    repo = UserRepository(session)
    if await repo.get_by_email(payload.email):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = await repo.create(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
    )
    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdateRequest,
    _admin: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> UserRead:
    repo = UserRepository(session)
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    fields: dict = {}
    if payload.full_name is not None:
        fields["full_name"] = payload.full_name
    if payload.role is not None:
        fields["role"] = payload.role
    if payload.is_active is not None:
        fields["is_active"] = payload.is_active
    if payload.password is not None:
        fields["password_hash"] = hash_password(payload.password)
    if fields:
        await repo.update(user, **fields)
        await session.commit()
        await session.refresh(user)
    return UserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    admin: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    repo = UserRepository(session)
    if not await repo.delete(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    await session.commit()
