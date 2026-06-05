from __future__ import annotations

from typing import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
from app.api.v1 import auth as auth_api
from app.api.v1 import creation as creation_api
from app.api.v1 import feedback as feedback_api
from app.core.database import Base
from app.models.content import ContentItem, ContentStatus
from app.services.auth_service import create_session, create_user


@pytest.mark.asyncio
async def test_feedback_and_creation_mutation_apis_require_login(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="workflow-user@example.com", password="Password123", role="user")
        token, _session = await create_session(db, user)
        db.add(
            ContentItem(
                id=1,
                title="创作与反馈样本",
                url="https://example.com/workflow",
                source_name="测试信源",
                source_type="RSS",
                status=ContentStatus.ANALYZED,
            )
        )
        await db.commit()

    async def fake_generate_creation_plan(db, content_id: int, platform: str):
        return {"titles": ["测试方案"], "_meta": {"content_id": content_id, "platform": platform}}

    monkeypatch.setattr(creation_api, "generate_creation_plan", fake_generate_creation_plan)

    app = FastAPI()
    app.include_router(feedback_api.router)
    app.include_router(creation_api.router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    for dependency in {
        auth_api.get_db,
        feedback_api.get_db,
        creation_api.get_db,
    }:
        app.dependency_overrides[dependency] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        platforms = await client.get("/creation/platforms")
        assert platforms.status_code == 200

        anonymous_feedback = await client.post(
            "/feedback",
            json={"content_id": 1, "feedback_type": "great_pick"},
        )
        assert anonymous_feedback.status_code == 401

        authorized_feedback = await client.post(
            "/feedback",
            headers={"Authorization": f"Bearer {token}"},
            json={"content_id": 1, "feedback_type": "great_pick"},
        )
        assert authorized_feedback.status_code == 201

        anonymous_stats = await client.get("/feedback/stats")
        assert anonymous_stats.status_code == 401

        authorized_stats = await client.get("/feedback/stats", headers={"Authorization": f"Bearer {token}"})
        assert authorized_stats.status_code == 200
        assert authorized_stats.json()["total"] == 1

        anonymous_plan = await client.post(
            "/creation/plan",
            json={"content_id": 1, "platform": "wechat"},
        )
        assert anonymous_plan.status_code == 401

        authorized_plan = await client.post(
            "/creation/plan",
            headers={"Authorization": f"Bearer {token}"},
            json={"content_id": 1, "platform": "wechat"},
        )
        assert authorized_plan.status_code == 200
        assert authorized_plan.json()["titles"] == ["测试方案"]

    await engine.dispose()
