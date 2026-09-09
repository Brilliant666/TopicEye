from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import llm_usage
from app.services.llm import _call_engine as engine, daily_provider_budget as daily, provider
from app.services.llm.provider_budget import ProviderBudgetError
from app.services.rardar_llm_control import RardarLLMScene


@pytest.mark.asyncio
async def test_actual_dispatch_shares_cap_across_scenes_and_disables_sdk_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")
    ledger = daily.daily_ledger(1)
    limiter = SimpleNamespace(acquire=AsyncMock())
    monkeypatch.setattr(engine, "_rate_limiter", limiter)
    monkeypatch.setattr(engine, "_get_token_rate_limiter", lambda: limiter)
    monkeypatch.setattr(engine, "_get_model_rate_limiter", lambda _: None)
    monkeypatch.setattr(engine, "execution_budget", lambda _: None)
    monkeypatch.setattr(engine, "daily_execution_budget", AsyncMock(return_value=(ledger, "news_quickread")))
    monkeypatch.setattr(provider, "_litellm_extra_kwargs", lambda _: {"num_retries": 9})
    monkeypatch.setattr(llm_usage, "record_llm_call_in_new_session", AsyncMock())
    monkeypatch.setattr(engine.run_guard, "before_attempt", lambda: None)
    monkeypatch.setattr(engine.run_guard, "failed", lambda _: None)

    @asynccontextmanager
    async def slot(*_args):
        yield

    monkeypatch.setattr(engine, "acquire_completion_slot", slot)
    dispatches = []

    async def fake_completion(**kwargs):
        dispatches.append(kwargs)
        raise TimeoutError("mock only")

    monkeypatch.setattr(engine, "acompletion", fake_completion)
    with pytest.raises(TimeoutError):
        await engine._call_llm_single([], "mock", None, None, 0.3, 100, None, scene="rardar_news_quickread")
    monkeypatch.setattr(engine, "daily_execution_budget", AsyncMock(return_value=(ledger, "find_project")))
    with pytest.raises(ProviderBudgetError, match="exhausted"):
        await engine._call_llm_single([], "mock", None, None, 0.3, 100, None, scene="rardar_find_project_comparison")
    assert len(dispatches) == 1
    assert dispatches[0]["num_retries"] == 0
    assert ledger.snapshot()["attempted"] == 1
    assert ledger.snapshot()["failed"] == 1


@pytest.mark.asyncio
async def test_enabled_unconfigured_blocks_but_unrelated_scenes_do_not_access_settings(monkeypatch):
    from app.core import database

    monkeypatch.setattr(daily.settings, "RARDAR_DAILY_OPERATIONS_ENABLED", True)
    calls = []

    @asynccontextmanager
    async def session():
        calls.append("settings")
        yield object()

    monkeypatch.setattr(database, "async_session", session)
    monkeypatch.setattr(daily, "configured_limit", AsyncMock(return_value=None))
    assert await daily.daily_execution_budget("general") is None
    assert calls == []
    with pytest.raises(ProviderBudgetError, match="unconfigured"):
        await daily.daily_execution_budget("rardar_news_quickread")
    assert calls == ["settings"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", list(RardarLLMScene))
async def test_every_registered_rardar_scene_uses_same_daily_ledger(scene, tmp_path, monkeypatch):
    from app.core import database

    monkeypatch.setattr(daily.settings, "RARDAR_DAILY_OPERATIONS_ENABLED", True)
    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(database, "async_session", session)
    monkeypatch.setattr(daily, "configured_limit", AsyncMock(return_value=100))
    resolved = await daily.daily_execution_budget(scene.value)
    assert resolved is not None
    ledger, stage = resolved
    assert stage in ledger.stages
    assert ledger.path == daily.daily_ledger(100).path
    assert ledger.run_id == f"daily-{daily.calendar_day()}"
    assert ledger.snapshot()["attempted"] == 0
