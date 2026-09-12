"""Daily policy and real receipt/publication entry; isolated data, no network."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.integrations.rardar import trending_boards, trending_periods as periods, trending_store as store
from app.services import rardar_daily_refresh as refresh, rardar_trending as service
from app.services.llm.provider_budget import file_lock
from tests_rardar_llm.test_rardar_trending_store import board


@pytest.fixture(autouse=True)
def policy(monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_BOARD_READINESS_MINUTES", 60)
    monkeypatch.setattr(settings, "RARDAR_BOARD_COMPENSATION_DELAY_MINUTES", 120)
    monkeypatch.setattr(settings, "RARDAR_DAILY_MATERIAL_SLICES", 6)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-09-12T00:30:00+08:00", "2026-09-10"),
        ("2026-09-12T07:59:59+08:00", "2026-09-10"),
        ("2026-09-12T08:00:00+08:00", "2026-09-10"),
        ("2026-09-12T08:59:59+08:00", "2026-09-10"),
        ("2026-09-12T09:00:00+08:00", "2026-09-11"),
        ("2026-09-13T00:00:00+08:00", "2026-09-11"),
        ("2026-10-01T09:00:00+08:00", "2026-09-30"),
        ("2027-01-01T09:00:00+08:00", "2026-12-31"),
        ("2028-03-01T09:00:00+08:00", "2028-02-29"),
    ],
)
def test_due_period_uses_ended_utc_day_and_readiness(now, expected):
    result = periods.due_period(datetime.fromisoformat(now))
    assert result["sourceDate"] == expected
    start, end = (datetime.fromisoformat(result[k]) for k in ("startAt", "endAt"))
    assert end - start == timedelta(days=1)
    assert start.hour == end.hour == 0
    assert start.astimezone(periods.ZONE).hour == end.astimezone(periods.ZONE).hour == 8
    assert datetime.fromisoformat(result["readyAt"]) <= datetime.fromisoformat(now)


def test_schedule_clock_is_host_independent_and_rejects_naive():
    now = datetime(2026, 12, 31, 2, tzinfo=UTC)
    expected = periods.schedule_plan(now)
    assert [p["runDate"] for p in expected] == ["2027-01-01", "2027-01-02", "2027-01-03"]
    for offset in (-8, 0, 8, 13):
        assert periods.schedule_plan(now.astimezone(timezone(timedelta(hours=offset)))) == expected
    for plan in expected:
        assert datetime.fromisoformat(plan["mainAt"]).astimezone(periods.ZONE).hour == 9
        assert datetime.fromisoformat(plan["compensationAt"]).astimezone(periods.ZONE).hour == 11
    with pytest.raises(ValueError, match="requires_timezone"):
        periods.due_period(datetime(2026, 9, 12))


def at(hour=9, *, day=12):
    return datetime(2026, 9, day, hour, tzinfo=periods.ZONE)


@pytest.fixture
def io(tmp_path, monkeypatch):
    async def fetch(source, *, target_date):
        value = board(source, [f"{source}/project"], when=at().isoformat(), day=None)
        return {**value, "targetPeriodDate": target_date, "acquisitionMode": "daily_snapshot"}

    fetcher = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(trending_boards, "fetch_board", fetcher)
    monkeypatch.setattr(service, "saved_materials", lambda _: {})
    monkeypatch.setattr(service, "refresh_metadata", AsyncMock(return_value={"checked": 2, "providerCalls": 0}))
    monkeypatch.setattr(refresh, "material_budget_available", AsyncMock(return_value=True))
    return tmp_path, fetcher


def day_state(target):
    return store.read_json(target / "trending-boards/daily-refresh/day-2026-09-12.json")


@pytest.mark.asyncio
async def test_main_then_completed_compensation_is_zero_io(io):
    target, fetch = io
    material = AsyncMock(return_value={"status": "completed", "remaining": 0})
    first = await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    assert first["sourceRequests"] == 2
    assert first["automaticRound"] == "main"
    assert first["targetPeriod"]["sourceDate"] == "2026-09-11"
    assert first["providerCalls"] == 0
    for hour in (9, 10, 11, 12, 23):
        again = await refresh.run_refresh(target, now=at(hour), trigger="automatic", material_work=material)
        assert again["status"] == "skipped"
    assert fetch.await_count == 2
    material.assert_awaited_once()
    assert len(day_state(target)["rounds"]) == 1


@pytest.mark.asyncio
async def test_compensation_fetches_only_failed_source_and_stops_at_two(io):
    target, fetch = io
    normal = fetch.side_effect

    async def fail_trendshift(source, **kwargs):
        if source == "trendshift":
            return {"source": source, "status": "failed", "errorCode": "network"}
        return await normal(source, **kwargs)

    fetch.side_effect = fail_trendshift
    first = await refresh.run_refresh(target, now=at(), trigger="automatic")
    assert first["status"] == "partial"
    second = await refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert second["requestedSources"] == ["trendshift"]
    assert second["automaticRound"] == "compensation"
    third = await refresh.run_refresh(target, now=at(12), trigger="automatic")
    assert third["reason"] == "daily_round_limit"
    assert fetch.await_count == 3
    assert len(day_state(target)["rounds"]) == 2


@pytest.mark.asyncio
async def test_publication_retry_reuses_saved_receipts(io, monkeypatch):
    target, fetch = io
    publish = refresh.publish_sources
    calls = 0

    def transient(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("isolated publication failure")
        return publish(*args, **kwargs)

    monkeypatch.setattr(refresh, "publish_sources", transient)
    first = await refresh.run_refresh(target, now=at(), trigger="automatic")
    assert first["status"] == "partial"
    second = await refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert second["sourceRequests"] == 0
    assert second["changed"] and second["status"] == "updated"
    assert len(store.load_snapshot(target)["projects"]) == 2
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_only_materials_resume_and_budget_wait_does_not_refetch(io):
    target, fetch = io
    material = AsyncMock(
        side_effect=[
            {"status": "pending", "waitReason": "interactive_request_waiting", "remaining": 1},
            {"status": "completed", "remaining": 0},
        ]
    )
    await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    result = await refresh.run_refresh(target, now=at(11), trigger="automatic", material_work=material)
    assert result["sourceRequests"] == 0
    assert material.await_count == 2
    assert fetch.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["daily_budget_exhausted", "daily_budget_not_configured", "material_retry_limit_reached"]
)
async def test_nonresumable_material_wait_has_no_compensation(io, reason):
    target, fetch = io
    material = AsyncMock(return_value={"status": "pending", "waitReason": reason, "remaining": 1})
    await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    result = await refresh.run_refresh(target, now=at(11), trigger="automatic", material_work=material)
    assert result["reason"] == "nothing_to_compensate"
    material.assert_awaited_once()
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_manual_receipts_reused_by_automatic_without_model_side_effect(io):
    target, fetch = io
    manual = await refresh.run_refresh(target, now=at())
    again = await refresh.run_refresh(target, now=at(10))
    assert manual["sourceRequests"] == 2 and again["sourceRequests"] == 0
    material = AsyncMock(return_value={"status": "completed"})
    automatic = await refresh.run_refresh(target, now=at(10), trigger="automatic", material_work=material)
    assert automatic["sourceRequests"] == 0
    assert fetch.await_count == 2
    material.assert_awaited_once()
    with pytest.raises(ValueError, match="cannot_generate"):
        await refresh.run_refresh(target, now=at(), material_work=material)


@pytest.mark.asyncio
async def test_wrong_dated_200_is_not_healthy_receipt(io):
    target, fetch = io
    normal = fetch.side_effect

    async def wrong(source, **kwargs):
        value = await normal(source, **kwargs)
        if source == "trendshift":
            value.update(acquisitionMode="ended_utc_day", sourceDate="2026-09-12")
        return value

    fetch.side_effect = wrong
    result = await refresh.run_refresh(target, now=at(), trigger="automatic")
    assert result["status"] == "partial"
    assert [p["repository"] for p in store.load_snapshot(target)["projects"]] == ["github/project"]
    state = store.read_json(target / "trending-boards/daily-refresh/period-2026-09-11.json")
    assert state["sources"]["trendshift"]["status"] == "failed"


@pytest.mark.asyncio
async def test_crash_resume_keeps_main_and_does_not_refetch_completed_source(io):
    target, fetch = io
    normal = fetch.side_effect

    async def interrupted(source, **kwargs):
        if source == "trendshift":
            raise asyncio.CancelledError()
        return await normal(source, **kwargs)

    fetch.side_effect = interrupted
    with pytest.raises(asyncio.CancelledError):
        await refresh.run_refresh(target, now=at(), trigger="automatic")
    assert day_state(target)["rounds"][0]["status"] == "running"
    fetch.side_effect = normal
    result = await refresh.run_refresh(target, now=at(10), trigger="automatic")
    assert result["automaticRound"] == "main"
    assert result["requestedSources"] == ["trendshift"]
    assert len(day_state(target)["rounds"]) == 1


@pytest.mark.asyncio
async def test_writer_lock_prevents_manual_and_automatic_overlap(io):
    target, fetch = io
    lock = target / "trending-boards/daily-refresh/writer.lock"
    lock.parent.mkdir(parents=True)
    with file_lock(lock, blocking=False):
        for trigger in ("manual", "automatic"):
            result = await refresh.run_refresh(target, now=at(), trigger=trigger)
            assert result["reason"] == "already_running"
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_next_day_same_members_do_not_reuse_previous_period_receipt(io):
    target, fetch = io
    first = await refresh.run_refresh(target, now=at(), trigger="automatic")
    second = await refresh.run_refresh(target, now=at(day=13), trigger="automatic")
    assert first["targetPeriod"]["sourceDate"] == "2026-09-11"
    assert second["targetPeriod"]["sourceDate"] == "2026-09-12"
    assert second["sourceRequests"] == 2 and fetch.await_count == 4
    assert (target / "trending-boards/daily-refresh/period-2026-09-12.json").exists()


@pytest.mark.asyncio
async def test_compensation_checks_budget_before_resuming_materials(io, monkeypatch):
    target, fetch = io
    material = AsyncMock(return_value={"status": "pending", "waitReason": "interactive_request_waiting"})
    await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    budget = AsyncMock(return_value=False)
    monkeypatch.setattr(refresh, "material_budget_available", budget)
    result = await refresh.run_refresh(target, now=at(11), trigger="automatic", material_work=material)
    assert result["reason"] == "nothing_to_compensate"
    budget.assert_awaited_once()
    material.assert_awaited_once()
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_one_main_can_advance_multiple_bounded_material_slices(io):
    target, fetch = io
    material = AsyncMock(
        side_effect=[
            {"status": "partial", "waitReason": "next_scheduled_pass", "visited": 3, "remaining": 4},
            {"status": "partial", "waitReason": "work_slice_exhausted", "providerRequests": 1, "remaining": 1},
            {"status": "completed", "visited": 1, "remaining": 0},
        ]
    )
    result = await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    assert result["materials"]["status"] == "completed"
    assert material.await_count == 3 and fetch.await_count == 2
    assert day_state(target)["materialSlices"] == 3
    assert result["materials"]["visited"] == 4
    assert result["materials"]["providerRequests"] == 1


@pytest.mark.asyncio
async def test_material_no_progress_stops_without_busy_loop(io):
    target, fetch = io
    material = AsyncMock(return_value={"status": "partial", "waitReason": "next_scheduled_pass", "visited": 0})
    await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    material.assert_awaited_once()
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_permanently_unsupported_source_does_not_make_endless_compensation(io):
    target, fetch = io
    normal = fetch.side_effect

    async def unsupported(source, **kwargs):
        if source == "trendshift":
            return {"source": source, "status": "failed", "errorCode": "history_unsupported", "retryable": False}
        return await normal(source, **kwargs)

    fetch.side_effect = unsupported
    first = await refresh.run_refresh(target, now=at(), trigger="automatic")
    assert first["count"] == 1
    result = await refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert result["reason"] == "nothing_to_compensate"
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_tampered_receipt_cannot_be_reused_for_publication(io):
    target, fetch = io
    await refresh.run_refresh(target, now=at(), trigger="automatic")
    pointer = (target / "trending-boards/current.json").read_bytes()
    path = target / "trending-boards/daily-refresh/period-2026-09-11.json"
    receipt = store.read_json(path)
    receipt["sources"]["github"]["result"]["entries"][0]["repository"] = "forged/repository"
    store.atomic(path, receipt)
    with pytest.raises(ValueError, match="receipt_integrity"):
        await refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert fetch.await_count == 2
    assert (target / "trending-boards/current.json").read_bytes() == pointer


def dated_sources(day="2026-09-11"):
    period = periods.source_period(day)
    fetched = datetime.fromisoformat(period["readyAt"]).isoformat()
    github = {
        **board("github", ["shared/project"], when=fetched),
        "targetPeriodDate": day,
        "acquisitionMode": "daily_snapshot",
    }
    trendshift = {
        **board("trendshift", ["shared/project"], when=fetched, day=day),
        "targetPeriodDate": day,
        "acquisitionMode": "ended_utc_day",
        "sourceTimezone": "UTC",
        "periodStartAt": period["startAt"],
        "periodEndAt": period["endAt"],
    }
    github["entries"][0].update(reportedDelta=0, reportedDeltaPeriod="stars today (source-defined)")
    trendshift["entries"][0].update(trendshiftStarsGained=15, trendshiftMetricPeriod="source UTC date")
    return [github, trendshift]


def set_read_clock(monkeypatch, value):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return value.astimezone(tz or UTC)

    monkeypatch.setattr(store, "datetime", Clock)


def test_current_snapshot_stales_at_due_period_not_shanghai_midnight(tmp_path, monkeypatch):
    store.publish_sources(tmp_path, dated_sources())
    for value in (at(23), at(0, day=13), at(8, day=13), at(9, day=13) - timedelta(seconds=1)):
        set_read_clock(monkeypatch, value)
        snapshot = store.load_snapshot(tmp_path)
        assert {s["status"] for s in snapshot["sources"]} == {"healthy"}
        assert snapshot["projects"][0]["dualListed"]
    set_read_clock(monkeypatch, at(9, day=13))
    snapshot = store.load_snapshot(tmp_path)
    assert {s["status"] for s in snapshot["sources"]} == {"stale"}
    assert not snapshot["projects"][0]["dualListed"]


def test_historical_generation_keeps_its_saved_source_health(tmp_path, monkeypatch):
    old = store.publish_sources(tmp_path, dated_sources())["generationId"]
    store.publish_sources(tmp_path, dated_sources("2026-09-12"))
    set_read_clock(monkeypatch, at(9, day=14))
    assert {s["status"] for s in store.load_snapshot(tmp_path)["sources"]} == {"stale"}
    historical = store.load_snapshot(tmp_path, old)
    assert {s["status"] for s in historical["sources"]} == {"healthy"}
    assert historical["projects"][0]["dualListed"]
    assert historical["sources"][1]["sourceDate"] == "2026-09-11"


def test_same_target_period_dual_badge_does_not_fabricate_shared_metric_window(tmp_path, monkeypatch):
    store.publish_sources(tmp_path, dated_sources())
    set_read_clock(monkeypatch, at())
    project = store.load_snapshot(tmp_path)["projects"][0]
    assert project["dualListed"]
    github, trendshift = project["appearances"]
    assert github["sourceDate"] is None
    assert "periodStartAt" not in github and "periodEndAt" not in github
    assert github["reportedDelta"] == 0
    assert github["targetPeriodDate"] == trendshift["targetPeriodDate"] == "2026-09-11"
    assert trendshift["sourceDate"] == "2026-09-11"
    assert trendshift["trendshiftStarsGained"] == 15
    assert trendshift["periodStartAt"] == "2026-09-11T00:00:00+00:00"
    assert trendshift["periodEndAt"] == "2026-09-12T00:00:00+00:00"


@pytest.mark.asyncio
async def test_compensation_preserves_successful_source_checked_and_fetched_times(io):
    target, fetch = io
    normal = fetch.side_effect

    async def transient(source, **kwargs):
        if source == "trendshift":
            return {"source": source, "status": "failed", "errorCode": "network"}
        return await normal(source, **kwargs)

    fetch.side_effect = transient
    await refresh.run_refresh(target, now=at(), trigger="automatic")
    receipt_path = target / "trending-boards/daily-refresh/period-2026-09-11.json"
    github_before = store.read_json(receipt_path)["sources"]["github"]
    fetch.side_effect = normal
    result = await refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert result["requestedSources"] == ["trendshift"]
    receipts = store.read_json(receipt_path)["sources"]
    assert receipts["github"] == github_before
    sources = {s["source"]: s for s in store.load_snapshot(target)["sources"]}
    assert sources["github"]["checkedAt"] == github_before["checkedAt"]
    assert sources["github"]["fetchedAt"] == github_before["result"]["fetchedAt"]
    assert sources["trendshift"]["checkedAt"] == at(11).astimezone(UTC).isoformat()


@pytest.mark.asyncio
async def test_fetch_source_identity_cannot_fill_another_source_slot(io):
    target, fetch = io
    normal = fetch.side_effect

    async def wrong_identity(source, **kwargs):
        if source == "github":
            return await normal("trendshift", **kwargs)
        return {"source": "trendshift", "status": "failed", "errorCode": "network"}

    fetch.side_effect = wrong_identity
    await refresh.run_refresh(target, now=at(), trigger="automatic")
    receipt_path = target / "trending-boards/daily-refresh/period-2026-09-11.json"
    assert store.read_json(receipt_path)["sources"]["github"]["status"] == "failed"
    assert store.load_snapshot(target)["projects"] == []


@pytest.mark.asyncio
async def test_started_round_freezes_source_period_across_shanghai_midnight(io, monkeypatch):
    target, fetch = io
    before = at(23) + timedelta(minutes=59)
    after = at(0, day=13) + timedelta(minutes=1)
    clock = before
    normal = fetch.side_effect

    async def crosses_midnight(source, **kwargs):
        nonlocal clock
        clock = after
        return await normal(source, **kwargs)

    monkeypatch.setattr(refresh, "instant", lambda now=None: clock.astimezone(UTC))
    fetch.side_effect = crosses_midnight
    result = await refresh.run_refresh(target, trigger="automatic")
    assert result["targetPeriod"]["sourceDate"] == "2026-09-11"
    assert [c.kwargs["target_date"] for c in fetch.await_args_list] == ["2026-09-11", "2026-09-11"]
    state = day_state(target)
    assert state["rounds"][0]["targetSourceDate"] == "2026-09-11"
    assert state["rounds"][0]["completedAt"] == after.astimezone(UTC).isoformat()
    assert not (target / "trending-boards/daily-refresh/day-2026-09-13.json").exists()
