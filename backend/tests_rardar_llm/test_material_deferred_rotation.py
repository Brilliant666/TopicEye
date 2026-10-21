"""Synthetic saved projects through the real bounded daily orchestration."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import rardar_daily_refresh as refresh, rardar_trending as service
from tests_rardar_llm.test_daily_refresh_policy import at, io  # noqa: F401
from tests_rardar_llm.test_material_work_allowance import work  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("healthy_scope", ["today", "historical"])
async def test_three_deferred_today_projects_do_not_hide_fourth_healthy_project(
    work,  # noqa: F811
    io,  # noqa: F811
    monkeypatch,
    healthy_scope,
):
    healthy = work.projects[3 if healthy_scope == "today" else 4]
    work.projects[:] = [*work.projects[:3], healthy]
    original = service._collect_project_material
    cooled = set(work.today[:3])
    retry_at = datetime.now(UTC) + timedelta(hours=6)

    async def collect(*args):
        if args[1]["repository"] in cooled:
            work.calls.append(args[1]["repository"])
            # Existing content-bound cache response; no source/model dispatch.
            return SimpleNamespace(profile_retry_suppressed=True, profile_next_retry_at=retry_at)
        return await original(*args)

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    saved = work.target / "progress.json"

    async def material():
        return await service.historical_work(work.target, progress, lambda: service.atomic(saved, progress))

    result = await refresh.run_refresh(work.target, now=at(), trigger="automatic", material_work=material)
    assert result["materials"]["processed"] == 1
    assert result["materials"]["waitReason"] == "material_content_retry_deferred"
    assert result["materials"]["todayPending"] == 3
    assert result["providerCalls"] == result["materials"]["failed"] == 0
    assert work.calls.count(healthy["repository"]) == 1
    assert set(work.calls) == cooled | {healthy["repository"]}
    assert 1 < result["auditRound"]["materials"]["slices"] <= 3
    records = service.read_json(saved)["materialWork"]["projects"]
    assert all(record["failures"] == 0 for record in records.values())
    assert records[healthy["repository"]]["status"] == "completed"
    assert result["materials"]["historicalDailyNewProjectLimit"] == 3
    assert result["materials"]["historicalAdmitted"] == int(healthy_scope == "historical")
    assert len(records) == 4  # same records, no reset or replacement
