from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.user import User
from app.schemas.auth import AuthLoginRequest, AuthRegisterRequest, AuthTokenResponse, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_session,
    create_user,
    get_user_by_email,
    get_user_for_token,
    revoke_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    return token.strip()


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)
    user = await get_user_for_token(db, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: AuthRegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    try:
        user = await create_user(db, email=data.email, password=data.password, display_name=data.display_name)
        token, session = await create_session(db, user)
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    return AuthTokenResponse(access_token=token, expires_at=session.expires_at, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthTokenResponse)
async def login(data: AuthLoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, email=data.email, password=data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token, session = await create_session(db, user)
    return AuthTokenResponse(access_token=token, expires_at=session.expires_at, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    token = _extract_bearer_token(authorization)
    await revoke_token(db, token)
    return {"logged_out": True}
