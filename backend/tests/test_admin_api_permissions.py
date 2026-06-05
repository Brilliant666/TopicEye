from __future__ import annotations

from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
from app.api.v1 import auth as auth_api
from app.api.v1 import fanqie as fanqie_api
from app.api.v1 import llm_models as llm_models_api
from app.api.v1 import qimao as qimao_api
from app.api.v1 import scheduler as scheduler_api
from app.api.v1 import settings as settings_api
from app.api.v1 import sources as sources_api
from app.api.v1 import webnovel_reports as webnovel_reports_api
from app.api.v1 import zhihu as zhihu_api
from app.core.database import Base
from app.services.auth_service import create_session, create_user
from app.services.llm.model_list_cache import invalidate_model_list_cache
from app.services.source_cache import invalidate_source_list_cache


@pytest_asyncio.fixture
async def admin_api_client(monkeypatch) -> AsyncGenerator[tuple[httpx.AsyncClient, str, str], None]:
    invalidate_model_list_cache()
    invalidate_source_list_cache()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="user@example.com", password="Password123", role="user")
        admin = await create_user(db, email="admin@example.com", password="Password123", role="admin")
        user_token, _ = await create_session(db, user)
        admin_token, _ = await create_session(db, admin)
        await db.commit()

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(sources_api.router)
    app.include_router(settings_api.router)
    app.include_router(fanqie_api.router)
    app.include_router(qimao_api.router)
    app.include_router(zhihu_api.router)
    app.include_router(webnovel_reports_api.router)
    app.include_router(llm_models_api.router)
    app.include_router(scheduler_api.router)

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
        sources_api.get_db,
        settings_api.get_db,
        fanqie_api.get_db,
        qimao_api.get_db,
        zhihu_api.get_db,
        webnovel_reports_api.get_db,
        llm_models_api.get_db,
    }:
        app.dependency_overrides[dependency] = override_get_db

    async def fake_jobs():
        return []

    monkeypatch.setattr(scheduler_api, "get_all_job_configs", fake_jobs)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, user_token, admin_token

    invalidate_model_list_cache()
    invalidate_source_list_cache()
    await engine.dispose()


@pytest.mark.asyncio
async def test_management_apis_require_admin_role(admin_api_client):
    client, user_token, admin_token = admin_api_client
    endpoints = [
        "/sources?page=1&page_size=1",
        "/settings/duckdb/status",
        "/models",
        "/scheduler/jobs",
    ]

    for endpoint in endpoints:
        anonymous = await client.get(endpoint)
        assert anonymous.status_code == 401, endpoint

        ordinary = await client.get(endpoint, headers={"Authorization": f"Bearer {user_token}"})
        assert ordinary.status_code == 403, endpoint

        admin = await client.get(endpoint, headers={"Authorization": f"Bearer {admin_token}"})
        assert admin.status_code == 200, endpoint


@pytest.mark.asyncio
async def test_webnovel_read_apis_require_login_not_admin(admin_api_client):
    client, user_token, admin_token = admin_api_client
    endpoints = [
        "/fanqie/categories",
        "/fanqie/rankings",
        "/fanqie/category/1/books",
        "/qimao/rankings",
        "/qimao/categories",
        "/qimao/books",
        "/zhihu/categories",
        "/zhihu/albums",
        "/webnovel/reports/weekly?days=7",
    ]

    for endpoint in endpoints:
        anonymous = await client.get(endpoint)
        assert anonymous.status_code == 401, endpoint

        ordinary = await client.get(endpoint, headers={"Authorization": f"Bearer {user_token}"})
        assert ordinary.status_code == 200, endpoint

        admin = await client.get(endpoint, headers={"Authorization": f"Bearer {admin_token}"})
        assert admin.status_code == 200, endpoint


@pytest.mark.asyncio
async def test_webnovel_sync_apis_still_require_admin(admin_api_client, monkeypatch):
    client, user_token, admin_token = admin_api_client
    sync_calls = []

    async def fake_fanqie_sync():
        sync_calls.append("fanqie")
        return {"status": "ok"}

    async def fake_qimao_sync():
        sync_calls.append("qimao")

    async def fake_zhihu_sync():
        sync_calls.append("zhihu")

    from app.services import fanqie_service, qimao_service, zhihu_service

    monkeypatch.setattr(fanqie_service, "full_sync", fake_fanqie_sync)
    monkeypatch.setattr(qimao_service, "sync_qimao_ranks", fake_qimao_sync)
    monkeypatch.setattr(zhihu_service, "sync_zhihu_ranks", fake_zhihu_sync)

    endpoints = [
        "/fanqie/sync",
        "/qimao/sync",
        "/zhihu/sync",
    ]

    for endpoint in endpoints:
        anonymous = await client.post(endpoint)
        assert anonymous.status_code == 401, endpoint

        ordinary = await client.post(endpoint, headers={"Authorization": f"Bearer {user_token}"})
        assert ordinary.status_code == 403, endpoint

        admin = await client.post(endpoint, headers={"Authorization": f"Bearer {admin_token}"})
        assert admin.status_code == 200, endpoint

    assert sync_calls == ["fanqie", "qimao", "zhihu"]
