from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sqlite_retry import retry_sqlite_locked
from app.models.user import User, UserSession

_HASH_ALGORITHM = "pbkdf2_sha256"
_HASH_ITERATIONS = 260_000
_SALT_BYTES = 16
_SESSION_TOKEN_BYTES = 32


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _HASH_ITERATIONS)
    return "$".join([
        _HASH_ALGORITHM,
        str(_HASH_ITERATIONS),
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    ])


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != _HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(_SESSION_TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: Optional[str] = None,
    role: str = "user",
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name or normalize_email(email).split("@", 1)[0],
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def ensure_admin_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: Optional[str] = None,
) -> User:
    user = await get_user_by_email(db, email)
    if not user:
        return await create_user(
            db,
            email=email,
            password=password,
            display_name=display_name,
            role="admin",
        )

    changed = False
    if user.password_hash == "__seeded_after_startup__":
        user.password_hash = hash_password(password)
        changed = True
    if user.role != "admin":
        user.role = "admin"
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if display_name and not user.display_name:
        user.display_name = display_name
        changed = True
    if changed:
        user.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> Optional[User]:
    user = await get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def create_session(db: AsyncSession, user: User, *, days: int = 30) -> tuple[str, UserSession]:
    token = new_session_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
    )

    async def insert_session() -> UserSession:
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    await retry_sqlite_locked(insert_session, on_retry=db.rollback)
    return token, session


async def get_user_for_token(db: AsyncSession, token: str) -> Optional[User]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserSession.id, User.id)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    )
    row = result.first()
    if not row:
        return None
    _, user_id = row
    return await db.get(User, user_id)


async def revoke_token(db: AsyncSession, token: str) -> bool:
    result = await db.execute(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return False
    session.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return True
