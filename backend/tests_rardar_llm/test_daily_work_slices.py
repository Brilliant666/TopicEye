from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.services.llm import daily_provider_budget as daily, run_failure_guard
from app.services.llm.provider_budget import ProviderBudgetError, file_lock


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")
    ledger = daily.daily_ledger(100)
    ledger.interactive_reserve = 10
    ledger.early_background_limit = 20
    return ledger


@pytest.mark.asyncio
async def test_persistent_policy_defaults_preserve_whole_day_cap(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        daily.AppSettingRepository,
        "get_by_key",
        AsyncMock(return_value=SimpleNamespace(value='{"providerRequestLimit":100}')),
    )
    assert await daily.configured_limit(object()) == 100
    assert await daily.configured_execution_policy(object(), 100) == {
        "interactiveReserve": 10,
        "earlyBackgroundLimit": 20,
    }
    # Small explicit caps are never raised to satisfy defaults.
    assert await daily.configured_execution_policy(object(), 4) == {"interactiveReserve": 4, "earlyBackgroundLimit": 4}


@pytest.mark.asyncio
async def test_work_slice_yields_before_dispatch_without_failure_or_new_allowance(ledger):
    caught_as_failure = False
    with (
        run_failure_guard.run_failure_guard(isolate_stages=True) as guard,
        daily.work_slice(max_requests=2) as state,
        pytest.raises(daily.ProviderWorkYield) as yielded,
    ):
        try:
            for _ in range(3):
                async with daily.managed_budget_execution(
                    None, (ledger, "project_profile"), scene="rardar_project_profile"
                ):
                    pass
        except Exception:
            caught_as_failure = True
            raise
    assert yielded.value.code == state.code == "work_slice_exhausted"
    assert state.used_requests == 2
    assert ledger.snapshot()["attempted"] == 2
    assert ledger.snapshot()["failed"] == 0
    assert not caught_as_failure
    assert guard.failures == 0
    # Resume is a fresh small slice, not a new daily ledger.
    with daily.work_slice(1):
        async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene="rardar_project_profile"):
            pass
    assert daily.daily_ledger(100).snapshot()["attempted"] == 3


@pytest.mark.asyncio
async def test_manual_background_respects_reserve_without_slice(ledger):
    # Model a nearly spent ledger without making any network requests.
    ledger.reservation_limit = 3
    ledger.interactive_reserve = 2
    async with daily.managed_budget_execution(None, (ledger, "news_quickread"), scene="rardar_news_quickread"):
        pass
    with pytest.raises(daily.ProviderWorkYield, match="interactive_budget_reserved"):
        async with daily.managed_budget_execution(None, (ledger, "news_quickread"), scene="rardar_news_quickread"):
            pytest.fail("No background dispatch into reserved allowance")
    for _ in range(2):
        async with daily.managed_budget_execution(
            None, (ledger, "find_project"), scene="rardar_find_project_comparison"
        ):
            pass
    with pytest.raises(ProviderBudgetError, match="exhausted"):
        async with daily.managed_budget_execution(
            None, (ledger, "find_project"), scene="rardar_find_project_comparison"
        ):
            pytest.fail("Interactive traffic cannot exceed the same cap")
    assert ledger.snapshot()["attempted"] == 3
    assert ledger.limit == 100


@pytest.mark.asyncio
async def test_interactive_waits_for_current_request_then_preempts_next_background(ledger):
    first_started = asyncio.Event()
    release = asyncio.Event()
    order = []

    async def background():
        async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene="rardar_project_profile"):
            order.append("background")
            first_started.set()
            await release.wait()
        with pytest.raises(daily.ProviderWorkYield, match="interactive_request_waiting"):
            async with daily.managed_budget_execution(
                None, (ledger, "project_profile"), scene="rardar_project_profile"
            ):
                pytest.fail("Background cannot reacquire ahead of waiting Find")

    async def interactive():
        await first_started.wait()
        async with daily.managed_budget_execution(
            None, (ledger, "find_project"), scene="rardar_find_project_comparison", wait_seconds=2
        ):
            order.append("find")

    background_task = asyncio.create_task(background())
    find_task = asyncio.create_task(interactive())
    await first_started.wait()
    for _ in range(100):
        if daily._interactive_waiting(ledger.execution_lock.parent):
            break
        await asyncio.sleep(0.01)
    assert daily._interactive_waiting(ledger.execution_lock.parent)
    release.set()
    await asyncio.gather(background_task, find_task)
    assert order == ["background", "find"]
    assert ledger.snapshot()["attempted"] == 2
    assert not daily._interactive_waiting(ledger.execution_lock.parent)


@pytest.mark.asyncio
async def test_pre_window_background_ceiling_preserves_later_budget(ledger, monkeypatch):
    class Clock:
        @staticmethod
        def now(_zone):
            return datetime(2026, 9, 10, 0, tzinfo=UTC)

    monkeypatch.setattr(daily, "datetime", Clock)
    ledger.early_background_limit = 1
    async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene="rardar_project_profile"):
        pass
    with pytest.raises(daily.ProviderWorkYield, match="pre_window_background_limit"):
        async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene="rardar_project_profile"):
            pytest.fail("No previous-cycle budget monopoly before 08:30")
    assert ledger.snapshot()["remaining"] == 99


@pytest.mark.asyncio
async def test_policy_rechecked_under_network_lock_before_any_reservation(ledger, monkeypatch):
    checks = []

    def policy(_ledger, **_kwargs):
        checks.append(True)
        if len(checks) == 2:
            with pytest.raises(ProviderBudgetError, match="busy"), file_lock(ledger.execution_lock, blocking=False):
                pytest.fail("Policy must be checked while global request lock is held")
            raise daily.ProviderWorkYield("interactive_budget_reserved")

    monkeypatch.setattr(daily, "_check_work_policy", policy)
    with pytest.raises(daily.ProviderWorkYield):
        async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene="rardar_project_profile"):
            pytest.fail("No provider dispatch after reservation race")
    assert len(checks) == 2
    assert ledger.snapshot()["reserved"] == ledger.snapshot()["attempted"] == 0
    assert ledger.snapshot()["failed"] == 0


def test_cache_read_does_not_consume_work_slice_or_daily_requests(ledger):
    with daily.work_slice(1) as state:
        ledger.record("cache_hit", "project_profile")
        ledger.record("cache_hit", "scope_value")
    assert state.used_requests == 0
    assert ledger.snapshot()["remaining"] == 100


@pytest.mark.asyncio
async def test_same_provider_inputs_reuse_real_cache_without_another_dispatch(ledger, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services.llm import circuit_breaker, provider, provider_budget, response_cache

    cache = response_cache.LLMCache()
    monkeypatch.setattr(response_cache, "get_llm_cache", lambda: cache)
    monkeypatch.setattr(
        circuit_breaker,
        "get_llm_circuit_breaker",
        lambda _: SimpleNamespace(
            allow_request=AsyncMock(return_value=True), record_success=AsyncMock(), record_failure=AsyncMock()
        ),
    )
    monkeypatch.setattr(provider_budget, "execution_budget", lambda _: (ledger, "project_profile"))
    dispatches = []

    async def inner(*_args, **_kwargs):
        async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene="rardar_project_profile"):
            dispatches.append(True)
            return '{"summary":"source-grounded fixture"}', {"cache_hit": False}

    monkeypatch.setattr(provider, "_call_llm_with_metadata_inner", inner)
    messages = [{"role": "user", "content": "same public evidence and processing version"}]
    with daily.work_slice(1) as state:
        first = await provider.call_llm_with_metadata(messages, scene="rardar_project_profile", cache_identity="v1")
        for _ in range(3):
            repeated = await provider.call_llm_with_metadata(
                messages, scene="rardar_project_profile", cache_identity="v1"
            )
            assert repeated[0] == first[0]
            assert repeated[1]["cache_hit"] is True
        assert state.used_requests == 1
    assert dispatches == [True]
    assert ledger.snapshot()["attempted"] == 1
    assert ledger.snapshot()["remaining"] == 99


@pytest.mark.asyncio
async def test_natural_midnight_ends_old_slice_without_double_charge(tmp_path, monkeypatch):
    current = datetime(2026, 9, 10, 15, 59, tzinfo=UTC)

    class Clock:
        @staticmethod
        def now(_zone):
            return current

    monkeypatch.setattr(daily, "datetime", Clock)
    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")
    old = daily.daily_ledger(100)
    old.interactive_reserve, old.early_background_limit = 10, 20
    with daily.work_slice(6):
        async with daily.managed_budget_execution(None, (old, "project_profile"), scene="rardar_project_profile"):
            pass
        current = datetime(2026, 9, 10, 16, 1, tzinfo=UTC)
        with pytest.raises(daily.ProviderWorkYield, match="calendar_day_changed"):
            async with daily.managed_budget_execution(None, (old, "project_profile"), scene="rardar_project_profile"):
                pytest.fail("Previous-day slice must stop before reserving")
    new = daily.daily_ledger(100)
    new.interactive_reserve, new.early_background_limit = 10, 20
    with daily.work_slice(6):
        async with daily.managed_budget_execution(None, (new, "scope_value"), scene="rardar_scope_value"):
            pass
    assert old.run_id != new.run_id
    assert old.snapshot()["attempted"] == new.snapshot()["attempted"] == 1
    assert daily.daily_ledger(100).snapshot()["remaining"] == 99
