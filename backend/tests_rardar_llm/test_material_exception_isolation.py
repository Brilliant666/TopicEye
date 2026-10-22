"""Offline replay of the observed running-record escape, not a recovered traceback."""

# ruff: noqa: F811 -- imported pytest fixtures are requested by name below.

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.services import rardar_trending as service
from tests_rardar_llm.test_material_work_allowance import work  # noqa: F401
from tests_rardar_llm.test_refocus_daily_entry import isolated  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, TypeError, KeyError])
async def test_unexpected_item_failure_is_durable_and_next_item_continues(work, monkeypatch, error_type):
    work.projects[:] = work.projects[:2]
    original = service._collect_project_material
    bad, good = (project["repository"] for project in work.projects)
    saved = work.target / "progress.json"

    async def collect(*args):
        if args[1]["repository"] == bad:
            work.calls.append(bad)
            raise error_type("Authorization: private-secret; provider body")
        return await original(*args)

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    first = await service.historical_work(work.target, progress, lambda: service.atomic(saved, progress))
    assert first["failed"] == first["processed"] == 1
    assert first["providerRequests"] == 0
    records = service.read_json(saved)["materialWork"]["projects"]
    assert records[bad]["status"] == "failed"
    assert records[bad]["failures"] == 1
    assert records[bad]["diagnostic"]["errorClass"] == error_type.__name__
    frames = records[bad]["diagnostic"]["applicationFrames"]
    assert any(frame["function"] == "historical_work" for frame in frames)
    assert records[good]["status"] == "completed"
    assert "private-secret" not in json.dumps(records)
    assert "provider body" not in json.dumps(records)

    await service.historical_work(work.target, progress, lambda: service.atomic(saved, progress))
    final = await service.historical_work(work.target, progress, lambda: service.atomic(saved, progress))
    assert work.calls.count(bad) == 2
    assert work.calls.count(good) == 1
    assert final["waitReason"] == "material_retry_limit_reached"
    assert final["failedAttempts"] == 2
    assert final["providerRequests"] == 0


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed_as_project_failure(work, monkeypatch):
    work.projects[:] = work.projects[:2]
    visited = []

    async def collect(*args):
        visited.append(args[1]["repository"])
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    with pytest.raises(asyncio.CancelledError):
        await service.historical_work(work.target, progress, lambda: None)
    assert len(visited) == 1
    record = progress["materialWork"]["projects"][visited[0]]
    assert record["failures"] == record["providerRequests"] == 0


@pytest.mark.asyncio
async def test_memory_exhaustion_is_not_treated_as_recoverable_item_failure(work, monkeypatch):
    work.projects[:] = work.projects[:2]
    collect = AsyncMock(side_effect=MemoryError("allocation failed"))
    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    with pytest.raises(MemoryError):
        await service.historical_work(work.target, progress, lambda: None)
    collect.assert_awaited_once()
    record = progress["materialWork"]["projects"][work.today[0]]
    assert record["failures"] == record["providerRequests"] == 0


@pytest.mark.asyncio
async def test_unknown_exception_code_is_not_written_to_progress(work, monkeypatch):
    work.projects[:] = work.projects[:1]
    error = RuntimeError("private exception message")
    error.code = "Authorization: private-code"
    monkeypatch.setattr(service, "_collect_project_material", AsyncMock(side_effect=error))
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    assert result["failed"] == 1
    record = progress["materialWork"]["projects"][work.today[0]]
    assert record["errorCode"] == "RuntimeError"
    assert "private-code" not in json.dumps(progress)
    assert "private exception" not in json.dumps(progress)


@pytest.mark.asyncio
async def test_failed_success_digest_is_not_counted_completed_or_removed_from_pending(work, monkeypatch):
    work.projects[:] = work.projects[:2]
    original = service._digest
    digest_calls = 0

    def digest(value):
        nonlocal digest_calls
        digest_calls += 1
        if digest_calls == 1:
            raise TypeError("invalid profile digest input")
        return original(value)

    monkeypatch.setattr(service, "_digest", digest)
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    assert result["failed"] == result["processed"] == result["remaining"] == 1
    records = progress["materialWork"]["projects"]
    assert records[work.today[0]]["status"] == "failed"
    assert records[work.today[1]]["status"] == "completed"
    rotation = service.read_json(work.target / "trending-boards/material-work.json")
    assert work.today[0] not in rotation["_successfulChecks"]


@pytest.mark.asyncio
async def test_unsafe_profile_cache_rejection_remains_failure_without_blocking_next_item(work, monkeypatch):
    work.projects[:] = work.projects[:2]
    original = service._collect_project_material

    async def collect(*args):
        if args[1]["repository"] == work.today[0]:
            # Same fixed rejection emitted by serving_profiles cache checks;
            # not claimed to be the lost production exception.
            raise RuntimeError("rardar_profile_cache_unsafe")
        return await original(*args)

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    assert result["failed"] == result["processed"] == 1
    assert result["providerRequests"] == 0
    record = progress["materialWork"]["projects"][work.today[0]]
    assert record["status"] == "failed"
    assert record["diagnostic"]["errorClass"] == "RuntimeError"
    rotation = service.read_json(work.target / "trending-boards/material-work.json")
    assert work.today[0] not in rotation["_successfulChecks"]


@pytest.mark.asyncio
async def test_durable_progress_write_failure_stops_work_instead_of_claiming_success(work):
    work.projects[:] = work.projects[:2]
    saves = 0

    def save():
        nonlocal saves
        saves += 1
        if saves >= 2:
            raise OSError("private storage failure")

    with pytest.raises(OSError, match="private storage failure"):
        await service.historical_work(work.target, {}, save)
    assert work.calls == [work.today[0]]


@pytest.mark.asyncio
async def test_outer_material_failure_keeps_safe_diagnostic_in_saved_daily_result(isolated, monkeypatch):
    from app.services import rardar_daily_operations as daily, rardar_daily_refresh as refresh

    monkeypatch.setattr(
        service, "historical_work", AsyncMock(side_effect=RuntimeError("Authorization: private-secret"))
    )

    async def run_refresh(*_args, material_work, **_kwargs):
        material = await material_work()
        return {"status": "completed", "materials": material}

    monkeypatch.setattr(refresh, "run_refresh", run_refresh)
    result = await service.run_daily_refocus()
    material = result["modules"]["historical_hot"]
    assert material["status"] == "failed"
    assert material["errorCode"] == "historical_material_failed"
    assert material["diagnostic"]["errorClass"] == "RuntimeError"
    assert material["diagnostic"]["stage"] == "orchestration"
    assert any(frame["function"] == "material_work" for frame in material["diagnostic"]["applicationFrames"])
    assert result["status"] == "partial"
    saved = service.read_json(daily.operation_root() / "latest.json")
    assert saved["modules"]["historical_hot"] == material
    assert "private-secret" not in json.dumps(saved)
