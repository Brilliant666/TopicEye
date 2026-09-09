from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm import daily_provider_budget as daily
from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    combined_budget_execution,
    execution_budget,
    selection_execution_budget,
    single_provider_attempt,
)


@pytest.fixture
def daily_root(tmp_path, monkeypatch):
    root = tmp_path / "daily"
    monkeypatch.setattr(daily, "daily_root", lambda: root)
    return root


def test_calendar_shanghai_boundary():
    assert daily.calendar_day(datetime(2026, 9, 9, 15, 59, tzinfo=UTC)) == "2026-09-09"
    assert daily.calendar_day(datetime(2026, 9, 9, 16, 0, tzinfo=UTC)) == "2026-09-10"
    with pytest.raises(ProviderBudgetError, match="date_invalid"):
        daily.calendar_day(datetime(2026, 9, 9))


def test_all_scenes_restart_and_failure_share_daily_cap(daily_root):
    instant = datetime(2026, 9, 9, tzinfo=UTC)
    for stage in ["news_quickread", "find_project", "project_profile"]:
        ledger = daily.daily_ledger(4, now=instant)
        with ledger.execution(stage):
            pass
    with pytest.raises(TimeoutError), daily.daily_ledger(4, now=instant).execution("scope_value"):
        raise TimeoutError("never recorded")
    resumed = daily.daily_ledger(4, now=instant)
    assert resumed.snapshot()["attempted"] == 4
    with pytest.raises(ProviderBudgetError, match="exhausted"), resumed.execution("user_copy"):
        pytest.fail("No fifth request")
    assert "never recorded" not in resumed.events.read_text()


def test_setting_change_cannot_reset_or_expand_same_day(daily_root):
    instant = datetime(2026, 9, 9, tzinfo=UTC)
    original = daily.daily_ledger(3, now=instant)
    with original.execution("find_project"):
        pass
    increased = daily.daily_ledger(100, now=instant)
    assert increased.reservation_limit == 3
    reduced = daily.daily_ledger(1, now=instant)
    with pytest.raises(ProviderBudgetError, match="exhausted"), reduced.execution("find_project"):
        pytest.fail("Reduced limit applies immediately")
    tomorrow = daily.daily_ledger(100, now=datetime(2026, 9, 10, tzinfo=UTC))
    assert tomorrow.snapshot()["remaining"] == 100
    assert tomorrow.execution_lock == original.execution_lock


def test_operation_and_daily_caps_both_charged_once(daily_root, tmp_path):
    ledger = daily.daily_ledger(5)
    operation = ProviderBudgetLedger.initialize(
        tmp_path / "operation" / "provider-budget.json", "operation", task_id="operation", limit=2
    )
    with (
        single_provider_attempt(),
        combined_budget_execution((operation, "news_quickread"), (ledger, "news_quickread")),
    ):
        pass
    assert ledger.snapshot()["attempted"] == operation.snapshot()["attempted"] == 1
    # The scheduler may attach the daily ledger itself to the existing context.
    with (
        single_provider_attempt(),
        combined_budget_execution((ledger, "profile_translation"), (ledger, "project_profile")),
    ):
        pass
    assert ledger.snapshot()["attempted"] == 2
    assert ledger.snapshot()["stageBreakdown"]["profile_translation"] == 1
    with combined_budget_execution((operation, "news_quickread"), (ledger, "news_quickread")):
        pass
    before = ledger.events.read_bytes()
    with (
        pytest.raises(ProviderBudgetError, match="exhausted"),
        combined_budget_execution((operation, "news_quickread"), (ledger, "news_quickread")),
    ):
        pytest.fail("Operation limit cannot be replaced by daily allowance")
    assert ledger.events.read_bytes() == before


def test_global_network_lock_across_calendar_rollover(daily_root):
    yesterday = daily.daily_ledger(10, now=datetime(2026, 9, 9, tzinfo=UTC))
    today = daily.daily_ledger(10, now=datetime(2026, 9, 10, tzinfo=UTC))
    with (
        yesterday.execution("scope_value"),
        pytest.raises(ProviderBudgetError, match="busy"),
        today.execution("find_project"),
    ):
        pytest.fail("Cross-day parallel network call")
    assert today.snapshot()["attempted"] == 0


def test_dispatch_after_midnight_does_not_double_charge_previous_day(daily_root):
    yesterday = daily.daily_ledger(1, now=datetime(2026, 9, 9, tzinfo=UTC))
    with yesterday.execution("project_profile"):
        pass
    today = daily.daily_ledger(100, now=datetime(2026, 9, 10, tzinfo=UTC))
    with combined_budget_execution((yesterday, "profile_translation"), (today, "project_profile")):
        pass
    assert yesterday.snapshot()["attempted"] == 1
    assert today.snapshot()["attempted"] == 1
    assert today.snapshot()["stageBreakdown"]["profile_translation"] == 1


@pytest.mark.asyncio
async def test_polling_unconfigured_never_initializes(daily_root, monkeypatch):
    monkeypatch.setattr(daily.AppSettingRepository, "get_by_key", AsyncMock(return_value=None))
    status = await daily.daily_budget_status(object())
    assert status["configured"] is False
    assert status["remaining"] == 0
    assert not daily_root.exists()


@pytest.mark.asyncio
async def test_config_validated_without_default_trial_budget(monkeypatch):
    for value in [True, 0, -1, "100", 100001]:
        monkeypatch.setattr(
            daily.AppSettingRepository,
            "get_by_key",
            AsyncMock(return_value=SimpleNamespace(value=json.dumps({"providerRequestLimit": value}))),
        )
        with pytest.raises(ProviderBudgetError, match="config_invalid"):
            await daily.configured_limit(object())
    monkeypatch.setattr(
        daily.AppSettingRepository,
        "get_by_key",
        AsyncMock(return_value=SimpleNamespace(value='{"providerRequestLimit":100}')),
    )
    assert await daily.configured_limit(object()) == 100


def test_corrupt_daily_state_never_reinitialized(daily_root):
    ledger = daily.daily_ledger(100)
    ledger.path.write_text("{}")
    before = ledger.events.read_bytes()
    with pytest.raises(ProviderBudgetError, match="invalid"):
        daily.daily_ledger(100)
    assert ledger.events.read_bytes() == before


def test_cache_reuse_has_no_dispatch_reservation(daily_root):
    ledger = daily.daily_ledger(100)
    ledger.record("cache_hit", "project_profile")
    assert daily.daily_ledger(100).snapshot()["attempted"] == 0
    assert daily.daily_ledger(100).snapshot()["remaining"] == 100


def test_daily_context_allows_every_registered_rardar_scene_but_not_legacy_expansion(daily_root, tmp_path):
    from app.services.rardar_llm_control import RardarLLMScene

    ledger = daily.daily_ledger(100)
    with selection_execution_budget(ledger):
        for scene in RardarLLMScene:
            resolved, stage = execution_budget(scene.value)
            assert resolved is ledger
            assert stage in ledger.stages
    legacy = ProviderBudgetLedger.initialize(
        tmp_path / "selection" / "provider-budget.json", "selection", task_id="selection-operation", limit=40
    )
    with selection_execution_budget(legacy), pytest.raises(ProviderBudgetError, match="scene_forbidden"):
        execution_budget("rardar_project_summary")
    assert ledger.snapshot()["attempted"] == 0
