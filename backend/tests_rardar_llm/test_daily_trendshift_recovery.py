"""Synthetic historical receipts through real daily orchestration and storage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.rardar import trending_store as store
from app.services import rardar_daily_refresh as refresh, rardar_trending as service
from app.services.llm.provider_budget import digest
from tests_rardar_llm.test_daily_refresh_policy import at, io  # noqa: F401


@pytest.mark.asyncio
async def test_old_healthy_homepage_receipt_is_not_reused_as_ended_day(io):  # noqa: F811
    target, fetch = io
    await refresh.run_refresh(target, now=at(), trigger="automatic")
    path = target / "trending-boards/daily-refresh/period-2026-09-11.json"
    cycle = store.read_json(path)
    receipt = cycle["sources"]["trendshift"]
    # Reproduce a valid old receipt, not a corrupted hash or a real source fetch.
    receipt["result"].update(acquisitionMode="daily_snapshot", sourceDate="2026-09-12")
    receipt["digest"] = digest(receipt["result"])
    cycle["publishedReceipts"]["trendshift"] = receipt["digest"]
    store.atomic(path, cycle)
    fetch.reset_mock()
    result = await refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert result["automaticRound"] == "compensation"
    assert result["requestedSources"] == ["trendshift"]
    assert result["providerCalls"] == 0
    fetch.assert_awaited_once_with("trendshift", target_date="2026-09-11")
    saved = store.read_json(path)["sources"]["trendshift"]["result"]
    assert saved["sourceDate"] == saved["targetPeriodDate"] == "2026-09-11"
    assert saved["acquisitionMode"] == "ended_utc_day"
    assert (await refresh.run_refresh(target, now=at(12), trigger="automatic"))["reason"] == "daily_round_limit"


@pytest.mark.asyncio
async def test_homepage_fallback_cannot_be_saved_as_healthy_target_day(io):  # noqa: F811
    target, fetch = io
    normal = fetch.side_effect

    async def fallback(source, **kwargs):
        result = await normal(source, **kwargs)
        if source == "trendshift":
            result.update(acquisitionMode="daily_snapshot", sourceDate="2026-09-12")
        return result

    fetch.side_effect = fallback
    result = await refresh.run_refresh(target, now=at(), trigger="automatic")
    assert result["status"] == "partial"
    assert result["providerCalls"] == 0
    source = next(s for s in store.load_snapshot(target)["sources"] if s["source"] == "trendshift")
    assert source["status"] == "failed"
    assert source["errorCode"] == "trendshift_target_day_unverified"
    receipt = store.read_json(target / "trending-boards/daily-refresh/period-2026-09-11.json")["sources"]["trendshift"]
    assert receipt["status"] == "failed"
    assert receipt["result"]["sourceDate"] == "2026-09-12"


@pytest.mark.asyncio
async def test_old_receipt_integrity_is_checked_before_date_recovery(io):  # noqa: F811
    target, fetch = io
    await refresh.run_refresh(target, now=at(), trigger="automatic")
    path = target / "trending-boards/daily-refresh/period-2026-09-11.json"
    cycle = store.read_json(path)
    cycle["sources"]["trendshift"]["result"].update(acquisitionMode="daily_snapshot", sourceDate="2026-09-12")
    store.atomic(path, cycle)  # deliberately retain wrong digest
    fetch.reset_mock()
    with pytest.raises(ValueError, match="daily_source_receipt_integrity"):
        await refresh.run_refresh(target, now=at(11), trigger="automatic")
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovered_source_rechecks_actual_new_today_admission(io, monkeypatch):  # noqa: F811
    from app.services import rardar_llm_control
    from app.services.llm import daily_provider_budget

    target, fetch = io
    normal = fetch.side_effect
    recovering = False

    async def source(key, **kwargs):
        if key == "trendshift" and not recovering:
            return {"source": key, "status": "failed", "errorCode": "trendshift_date_action_missing"}
        value = await normal(key, **kwargs)
        value["entries"][0]["reportedDelta" if key == "github" else "trendshiftStarsGained"] = 250
        return value

    fetch.side_effect = source
    original = {"attempts": {"history/a": 2, "history/b": 2, "history/c": 2, "github/project": 2}}
    progress_path = target / "material-progress.json"
    store.atomic(progress_path, original)
    collector = AsyncMock(return_value=SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="hit"))
    monkeypatch.setattr(service, "_collect_project_material", collector)
    monkeypatch.setattr(
        service, "project_material", lambda *_: {"profile": {"summary": "用于管理任务并查看日志的工具。"}}
    )
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 50}), {})),
    )
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="fixture-route"))
    await refresh.run_refresh(
        target,
        now=at(),
        trigger="automatic",
        material_work=AsyncMock(
            return_value={
                "status": "partial",
                "waitReason": "historical_daily_limit_reached",
                "todayPending": 0,
            }
        ),
    )
    recovering = True
    qualifications = []

    async def qualify():
        result = await service.historical_work(
            target,
            store.read_json(progress_path),
            lambda: pytest.fail("qualification wrote progress"),
            qualification_only=True,
        )
        qualifications.append(result["qualification"]["today"]["admissionEligible"])
        return result

    async def work():
        progress = store.read_json(progress_path)
        return await service.historical_work(target, progress, lambda: store.atomic(progress_path, progress))

    result = await refresh.run_refresh(
        target, now=at(11), trigger="automatic", material_work=work, material_qualification=qualify
    )
    assert qualifications == [0, 1]
    assert result["requestedSources"] == ["trendshift"]
    assert result["materials"]["refreshed"] == 1
    assert collector.await_count == 1
    assert collector.call_args.args[1]["repository"] == "trendshift/project"
    assert result["providerCalls"] == 0
    assert store.read_json(progress_path)["attempts"] == original["attempts"]
