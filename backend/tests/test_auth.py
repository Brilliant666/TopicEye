from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.auth import get_current_user, login, logout, me, register
from app.core.database import Base
from app.models.user import User
from app.schemas.auth import AuthLoginRequest, AuthRegisterRequest
from app.services.auth_service import (
    authenticate_user,
    create_session,
    create_user,
    get_user_for_token,
    revoke_token,
    verify_password,
)


class _FakeSessionLookupResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _LockedLastSeenSession:
    def __init__(self, user):
        self.user = user
        self.execute_count = 0
        self.rolled_back = False

    async def execute(self, _statement):
        self.execute_count += 1
        if self.execute_count == 1:
            return _FakeSessionLookupResult((101, self.user.id))
        raise OperationalError("UPDATE user_sessions", {}, Exception("database is locked"))

    async def flush(self):
        raise AssertionError("flush should not run after a locked update")

    async def rollback(self):
        self.rolled_back = True

    async def get(self, model, user_id):
        assert model is User
        assert user_id == self.user.id
        return self.user


@pytest.mark.asyncio
async def test_auth_service_registers_lowercase_email_and_hashes_password():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="Codex@Example.COM", password="Password123", display_name=None)

        assert user.email == "codex@example.com"
        assert user.display_name == "codex"
        assert user.password_hash != "Password123"
        assert verify_password("Password123", user.password_hash)
        assert not verify_password("wrong-password", user.password_hash)

    await engine.dispose()


@pytest.mark.asyncio
async def test_auth_service_session_lifecycle():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="session@example.com", password="Password123")
        token, session = await create_session(db, user)

        assert session.token_hash != token
        assert await authenticate_user(db, email="SESSION@example.com", password="Password123") is not None
        assert await authenticate_user(db, email="session@example.com", password="bad") is None

        current_user = await get_user_for_token(db, token)
        assert current_user is not None
        assert current_user.email == "session@example.com"

        assert await revoke_token(db, token) is True
        assert await get_user_for_token(db, token) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_user_for_token_returns_user_when_last_seen_sqlite_locked():
    user = User(id=7, email="locked@example.com", password_hash="hash", display_name="Locked")
    db = _LockedLastSeenSession(user)

    current_user = await get_user_for_token(db, "session-token")

    assert current_user is user
    assert db.rolled_back is True
    assert db.execute_count == 2


@pytest.mark.asyncio
async def test_auth_route_functions_register_login_me_logout():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        registered = await register(
            AuthRegisterRequest(email="Route@Example.com", password="Password123", display_name="Route User"),
            db,
        )
        assert registered.user.email == "route@example.com"
        assert registered.token_type == "bearer"

        duplicate_error = None
        try:
            await register(AuthRegisterRequest(email="route@example.com", password="Password123"), db)
        except HTTPException as exc:
            duplicate_error = exc
        assert duplicate_error is not None
        assert duplicate_error.status_code == 409

        logged_in = await login(AuthLoginRequest(email="route@example.com", password="Password123"), db)
        current_user = await get_current_user(f"Bearer {logged_in.access_token}", db)
        assert isinstance(current_user, User)
        assert (await me(current_user)).email == "route@example.com"

        assert (await logout(f"Bearer {logged_in.access_token}", db))["logged_out"] is True
        invalid_error = None
        try:
            await get_current_user(f"Bearer {logged_in.access_token}", db)
        except HTTPException as exc:
            invalid_error = exc
        assert invalid_error is not None
        assert invalid_error.status_code == 401

    await engine.dispose()
