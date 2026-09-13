"""Real work ordering with simulated collection, preserving the daily allowance."""

import pytest

from app.core.config import settings
from app.integrations.rardar import historical_daily
from app.services import rardar_trending as service
from tests_rardar_llm.test_material_work_allowance import work  # noqa: F401


@pytest.mark.asyncio
async def test_actual_today_then_daily_review_then_bounded_history(work, monkeypatch):  # noqa: F811
    # A formerly listed low-growth item must not claim Today's admission.
    work.projects[1]["appearances"][0]["reportedDelta"] = 199
    work.projects[2]["appearances"][0]["reportedDelta"] = 0
    work.projects[3]["appearances"][0]["reportedDelta"] = None
    selected = work.projects[6]
    monkeypatch.setattr(historical_daily, "read_latest", lambda _: {"projectIds": [selected["projectId"]]})
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 1)
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    assert work.calls == [work.today[0], selected["repository"]]
    assert result["checkedToday"] == 1
    assert result["historicalNewAdmitted"] == 1
    assert progress["materialWork"]["projects"][selected["repository"]]["scope"] == "historical"
    assert not set(work.today[1:]) & set(work.calls)
