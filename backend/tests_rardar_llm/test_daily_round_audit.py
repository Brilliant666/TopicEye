"""Synthetic round metrics through real receipt persistence; no external IO."""

from unittest.mock import AsyncMock

import pytest

from app.services import rardar_daily_refresh as refresh
from tests_rardar_llm.test_daily_refresh_policy import at, day_state, io, policy  # noqa: F401


def slice_result(processed, failed, requests, reused, remaining):
    return {
        "status": "partial", "waitReason": "next_scheduled_pass",
        "processed": processed, "refreshed": 0, "failed": failed,
        "providerRequests": requests, "visited": processed + failed,
        "reused": reused, "todayPending": 2, "historicalPending": remaining - 2,
        "remaining": remaining,
    }


@pytest.mark.asyncio
async def test_round_delta_cumulative_and_last_scan_are_distinct(io, monkeypatch):  # noqa: F811
    target, fetch = io
    monkeypatch.setattr(refresh.settings, "RARDAR_DAILY_MATERIAL_SLICES", 2)
    material = AsyncMock(side_effect=[
        slice_result(2, 1, 3, 10, 15), slice_result(1, 2, 2, 12, 14),
        slice_result(3, 0, 3, 14, 11), slice_result(2, 1, 2, 17, 9),
    ])
    main = await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    compensation = await refresh.run_refresh(target, now=at(11), trigger="automatic", material_work=material)
    first, second = main["auditRound"], compensation["auditRound"]
    assert first["roundKind"] == "main"
    assert second["roundKind"] == "compensation"
    assert first["materials"]["round"] == {
        "processed": 3, "refreshed": 0, "failedAttempts": 3, "providerRequests": 5, "visited": 6,
    }
    assert second["materials"]["round"]["processed"] == 5
    assert second["materials"]["round"]["failedAttempts"] == 1
    assert second["materials"]["cumulative"]["processed"] == 8
    assert second["materials"]["cumulative"]["failedAttempts"] == 4
    assert second["materials"]["snapshot"]["reused"] == 17  # never 10+12+14+17
    assert second["materials"]["snapshot"]["historicalPending"] == 7
    assert second["materials"]["snapshot"]["waitReason"] == "next_scheduled_pass"
    assert second["materials"]["slices"] == second["materials"]["sliceLimit"] == 2
    assert compensation["materials"]["status"] == "partial"
    assert main["providerCalls"] == compensation["providerCalls"] == 5
    assert second["generationId"] == first["generationId"]
    assert fetch.await_count == 2
    assert second["sourceRequests"] == 0
    assert material.await_count == 4
    assert day_state(target)["materialTotals"]["processed"] == 8
    assert len(day_state(target)["rounds"]) == 2


@pytest.mark.asyncio
async def test_missing_slice_fields_remain_unknown_and_no_work_is_known_zero(io):  # noqa: F811
    target, _ = io
    material = AsyncMock(return_value={"status": "completed"})
    result = await refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    audit = result["auditRound"]["materials"]
    assert all(value is None for value in audit["round"].values())
    assert audit["snapshot"]["reused"] is None
    assert audit["snapshot"]["remaining"] is None
    assert audit["slices"] == 1


@pytest.mark.asyncio
async def test_no_material_callback_does_not_invent_snapshot(io):  # noqa: F811
    target, _ = io
    result = await refresh.run_refresh(target, now=at(), trigger="automatic")
    audit = result["auditRound"]["materials"]
    assert set(audit["round"].values()) == {0}
    assert set(audit["cumulative"].values()) == {None}
    assert set(audit["snapshot"].values()) == {None}
    assert audit["slices"] == 0
