"""Real orchestration with synthetic work; no external Provider."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import rardar_daily_operations as daily
from app.services.llm import daily_provider_budget as budget


@pytest.mark.asyncio
async def test_news_backlog_returns_after_a_useful_piece(tmp_path, monkeypatch):
    from app.services import rardar_hotspot_news, rardar_news_quickread

    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    items = [SimpleNamespace(id=i, model_dump=lambda **_: {"title": "fixture"}) for i in range(1, 41)]

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(daily, "async_session", session)
    monkeypatch.setattr(
        rardar_hotspot_news,
        "load_hotspot_news",
        AsyncMock(return_value=(SimpleNamespace(items=items, totalPages=1), None)),
    )
    enhance = AsyncMock(
        return_value=SimpleNamespace(
            considered=1, enhanced=1, cacheHits=0, alreadyChinese=0, failed=0, status="completed", items=[]
        )
    )
    monkeypatch.setattr(rardar_news_quickread, "enhance_hotspot_news", enhance)
    result = await daily._news_enhance(ledger, {}, lambda: None)
    assert 0 < enhance.await_count <= 6  # Baseline called all 40 before yielding.
    assert result["unfinished"] >= 34


@pytest.mark.asyncio
async def test_backlogs_take_round_robin_turns_in_same_run(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    monkeypatch.setattr(budget, "daily_execution_budget", AsyncMock(return_value=(ledger, "project_profile")))
    for name in ("_today", "_news_refresh", "_public_materials"):
        monkeypatch.setattr(daily, name, AsyncMock(return_value={"status": "completed"}))
    monkeypatch.setattr(daily, "_inventory", AsyncMock(return_value=({"status": "checked"}, object(), [])))
    turns = []

    def action(name):
        async def run(*_args, **_kwargs):
            turns.append(name)
            return {"status": "partial", "hasMore": turns.count(name) < 3, "unfinished": 100}

        return run

    monkeypatch.setattr(daily, "_discover", action("discover"))
    monkeypatch.setattr(daily, "_news_enhance", action("news"))
    monkeypatch.setattr(daily, "_today_profiles", action("today"))
    await daily.run_daily_operations()
    assert turns == ["discover", "news", "today"] * 3
    assert ledger.snapshot()["attempted"] == 0


@pytest.mark.asyncio
async def test_news_slice_includes_historical_debt_without_duplicates(tmp_path, monkeypatch):
    from app.services import rardar_hotspot_news, rardar_news_quickread

    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    now = datetime.now(UTC)
    items = [
        SimpleNamespace(
            id=i, publishedAt=now if i <= 8 else now - timedelta(days=30), model_dump=lambda **_: {"title": "fixture"}
        )
        for i in range(1, 13)
    ]

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(daily, "async_session", session)
    monkeypatch.setattr(
        rardar_hotspot_news,
        "load_hotspot_news",
        AsyncMock(return_value=(SimpleNamespace(items=items, totalPages=1), None)),
    )
    ids = []

    async def enhance(_db, *, frozen_page, **_kwargs):
        ids.append(frozen_page.items[0].id)
        return SimpleNamespace(considered=1, enhanced=0, cacheHits=1, alreadyChinese=0, failed=0, status="completed")

    monkeypatch.setattr(rardar_news_quickread, "enhance_hotspot_news", enhance)
    progress = {}
    await daily._news_enhance(ledger, progress, lambda: None)
    assert ids == [1, 2, 12, 3, 4, 11]
    await daily._news_enhance(ledger, progress, lambda: None)
    assert len(ids) == len(set(ids)) == 12


@pytest.mark.asyncio
async def test_public_material_inventory_yields_and_resumes_without_refetch(tmp_path, monkeypatch):
    from app.services import rardar_managed_materials, rardar_project_evidence

    projects = [{"repository": f"fixture/p{i}", "facts": {}} for i in range(15)]
    monkeypatch.setattr(rardar_project_evidence, "_persistent_root", lambda: tmp_path / "evidence")
    monkeypatch.setattr(rardar_managed_materials, "inventory_managed_materials", lambda _: {"projects": projects})
    fetch = AsyncMock(return_value=SimpleNamespace(payload={"readme": {"path": "README.md"}}))
    monkeypatch.setattr(rardar_project_evidence, "collect_project_evidence", fetch)
    progress = {}
    first = await daily._public_materials(progress, lambda: None, max_items=6)
    assert first["checked"] == 15 and first["processed"] == 6 and first["hasMore"]
    await daily._public_materials(progress, lambda: None, max_items=6)
    last = await daily._public_materials(progress, lambda: None, max_items=6)
    assert last["processed"] == 15 and not last["hasMore"]
    assert fetch.await_count == 15


@pytest.mark.asyncio
async def test_cooperative_pause_does_not_lock_out_same_day_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    monkeypatch.setattr(budget, "daily_execution_budget", AsyncMock(return_value=(ledger, "project_profile")))
    for name in ("_today", "_news_refresh", "_public_materials", "_discover", "_news_enhance", "_today_profiles"):
        monkeypatch.setattr(daily, name, AsyncMock(return_value={"status": "completed"}))
    monkeypatch.setattr(daily, "_inventory", AsyncMock(return_value=({"status": "checked"}, None, [])))
    pause = AsyncMock(return_value=True)
    monkeypatch.setattr(daily, "_execution_paused", pause)
    for _ in range(4):
        assert (await daily.run_daily_operations())["status"] == "partial"
    pause.return_value = False
    resumed = await daily.run_daily_operations()
    assert resumed.get("reason") != "daily_retry_limit"
    assert resumed.get("failureRetries", 0) == 0
    assert daily._news_enhance.await_count == 1
    assert ledger.snapshot()["attempted"] == 0
