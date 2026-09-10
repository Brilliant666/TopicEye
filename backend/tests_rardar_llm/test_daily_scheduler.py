from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import scheduler as scheduler_module
from app.core.database import Base
from app.models.scheduled_job import ScheduledJob
from app.services import job_tracker


@pytest.mark.asyncio
async def test_daily_config_preserves_policy_fields_and_rejects_over_cap(monkeypatch):
    import json
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from app.repositories.app_setting_repo import AppSettingRepository
    from app.services import rardar_daily_operations
    from app.services.llm import daily_provider_budget

    @asynccontextmanager
    async def session():
        yield SimpleNamespace(commit=AsyncMock())

    save = AsyncMock()
    monkeypatch.setattr(job_tracker, "async_session", session)
    monkeypatch.setattr(
        AppSettingRepository,
        "get_by_key",
        AsyncMock(
            return_value=SimpleNamespace(
                value='{"providerRequestLimit":100,"interactiveReserve":12,"earlyBackgroundLimit":18}'
            )
        ),
    )
    monkeypatch.setattr(AppSettingRepository, "upsert_setting", save)
    monkeypatch.setattr(daily_provider_budget, "daily_budget_status", AsyncMock(return_value={}))
    monkeypatch.setattr(rardar_daily_operations, "latest_status", lambda: {})
    await job_tracker.daily_config_status(100)
    assert json.loads(save.call_args.args[1]) == {
        "providerRequestLimit": 100,
        "interactiveReserve": 12,
        "earlyBackgroundLimit": 18,
    }
    with pytest.raises(ValueError, match="provider_daily_config_invalid"):
        await job_tracker.daily_config_status(100, interactive_reserve=101)
    assert save.await_count == 1


def test_startup_window_does_not_gate_explicit_manual_action():
    assert not scheduler_module._rardar_daily_window_open(datetime(2026, 9, 10, 0, 29, tzinfo=UTC))
    assert scheduler_module._rardar_daily_window_open(datetime(2026, 9, 10, 0, 30, tzinfo=UTC))


@pytest.mark.asyncio
async def test_daily_status_only_exposes_safe_summary(monkeypatch):
    from contextlib import asynccontextmanager

    from app.services import rardar_daily_operations
    from app.services.llm import daily_provider_budget

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(job_tracker, "async_session", session)
    monkeypatch.setattr(daily_provider_budget, "daily_budget_status", AsyncMock(return_value={"configuredLimit": 100}))
    monkeypatch.setattr(
        rardar_daily_operations,
        "latest_status",
        lambda: {
            "status": "partial",
            "progress": {"private": "hidden"},
            "modules": {
                "discover": {"checked": 48, "failed": 1, "path": "private/path", "result": {"secret": "hidden"}}
            },
        },
    )
    result = await job_tracker.daily_config_status()
    assert result["dailyStatus"]["modules"] == {"discover": {"checked": 48, "failed": 1}}
    assert "hidden" not in str(result)


@pytest.mark.asyncio
async def test_control_requires_admin_and_cookie_origin(monkeypatch):
    import httpx
    from fastapi import FastAPI

    from app.api.v1.auth import get_current_admin_user
    from app.api.v1.scheduler import router

    app = FastAPI()
    app.include_router(router)
    called = AsyncMock(return_value={"status": "queued"})
    monkeypatch.setattr(job_tracker, "control_rardar_daily_job", called)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/scheduler/jobs/rardar_daily_operations/run")
        assert denied.status_code in {401, 403}
        app.dependency_overrides[get_current_admin_user] = lambda: object()
        denied = await client.post("/scheduler/jobs/rardar_daily_operations/run")
        assert denied.status_code == 403
        accepted = await client.post(
            "/scheduler/jobs/rardar_daily_operations/run", headers={"Authorization": "Bearer mock-admin"}
        )
        assert accepted.status_code == 200
        called.assert_awaited_once_with("run")


@pytest.mark.asyncio
async def test_tracker_preserves_partial_status_and_manual_origin(monkeypatch):
    monkeypatch.setattr(job_tracker, "_claim_job_run", AsyncMock(return_value=True))
    create = AsyncMock(return_value=1)
    finish = AsyncMock()
    release = AsyncMock()
    monkeypatch.setattr(job_tracker, "_create_log", create)
    monkeypatch.setattr(job_tracker, "_finish_log", finish)
    monkeypatch.setattr(job_tracker, "_release_job_run", release)

    @job_tracker.track_job("rardar_daily_operations")
    async def partial():
        return {"status": "partial", "published": 0}

    await partial(_trigger_type="manual")
    create.assert_awaited_once_with("rardar_daily_operations", trigger_type="manual")
    assert finish.call_args.args[1] == "PARTIAL"
    release.assert_awaited_once_with("rardar_daily_operations", "PARTIAL")


@pytest.mark.asyncio
async def test_rardar_only_registers_daily_job_and_startup_catchup(monkeypatch):
    fake = MagicMock(running=False)
    monkeypatch.setattr(scheduler_module, "scheduler", fake)
    monkeypatch.setattr(scheduler_module.settings, "RARDAR_PRODUCT_MODE", True)
    monkeypatch.setattr(scheduler_module.settings, "RARDAR_DAILY_OPERATIONS_ENABLED", True)
    catchup = AsyncMock()
    monkeypatch.setattr(scheduler_module, "_rardar_startup_catchup", catchup)
    scheduler_module.start_scheduler()
    import asyncio

    await asyncio.sleep(0)
    assert [call.kwargs["id"] for call in fake.add_job.call_args_list] == ["rardar_daily_operations"]
    assert str(fake.add_job.call_args.kwargs["trigger"].timezone) == "Asia/Shanghai"
    fake.start.assert_called_once()
    catchup.assert_awaited_once()


def test_rardar_disabled_does_not_start_other_product_jobs(monkeypatch):
    fake = MagicMock(running=False)
    monkeypatch.setattr(scheduler_module, "scheduler", fake)
    monkeypatch.setattr(scheduler_module.settings, "RARDAR_PRODUCT_MODE", True)
    monkeypatch.setattr(scheduler_module.settings, "RARDAR_DAILY_OPERATIONS_ENABLED", False)
    scheduler_module.start_scheduler()
    fake.start.assert_not_called()
    fake.add_job.assert_not_called()


@pytest.mark.asyncio
async def test_pause_survives_registration_and_blocks_run(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(job_tracker, "async_session", factory)
    await job_tracker._upsert_job_config("paused", "测试")
    async with factory() as db:
        job = (await db.execute(select(ScheduledJob).where(ScheduledJob.job_key == "paused"))).scalar_one()
        job.enabled = False
        await db.commit()
    await job_tracker._upsert_job_config("paused", "更新名称")
    assert not await job_tracker._claim_job_run("paused", "更新名称", "", 60)
    async with factory() as db:
        job = (await db.execute(select(ScheduledJob).where(ScheduledJob.job_key == "paused"))).scalar_one()
        assert not job.enabled
        assert job.last_run_at is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_restart_recovers_only_unowned_daily_writer(monkeypatch, tmp_path):
    from app.services import rardar_daily_operations
    from app.services.llm.provider_budget import file_lock

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(job_tracker, "async_session", factory)
    monkeypatch.setattr(rardar_daily_operations, "operation_root", lambda: tmp_path)
    await job_tracker._claim_job_run("rardar_daily_operations", "日程", "", 14400)
    with file_lock(tmp_path / "writer.lock", blocking=False):
        assert not await job_tracker.recover_rardar_daily_lease()
    assert await job_tracker.recover_rardar_daily_lease()
    assert not await job_tracker.recover_rardar_daily_lease()
    assert await job_tracker._claim_job_run("rardar_daily_operations", "日程", "", 14400)
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_run_is_enqueued_in_real_scheduler_interface(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(job_tracker, "async_session", factory)
    monkeypatch.setattr(scheduler_module.settings, "RARDAR_PRODUCT_MODE", True)
    monkeypatch.setattr(scheduler_module.settings, "RARDAR_DAILY_OPERATIONS_ENABLED", True)
    fake = MagicMock(running=True)
    fake.get_job.return_value = None
    monkeypatch.setattr(scheduler_module, "scheduler", fake)
    assert await job_tracker.control_rardar_daily_job("run") == {"status": "queued"}
    assert fake.add_job.call_args.kwargs["trigger"] == "date"
    assert fake.add_job.call_args.kwargs["kwargs"] == {"_trigger_type": "manual"}
    fake.get_job.return_value = object()
    assert await job_tracker.control_rardar_daily_job("run") == {"status": "running"}
    assert fake.add_job.call_count == 1
    await job_tracker.control_rardar_daily_job("pause")
    assert await job_tracker.control_rardar_daily_job("run") == {"status": "paused"}
    await engine.dispose()
