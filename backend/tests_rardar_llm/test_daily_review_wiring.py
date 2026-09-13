"""Real daily entry, simulated sources and materials; no Provider or network."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.integrations.rardar import trending_boards, trending_store as store
from app.services import rardar_daily_refresh as refresh
from tests_rardar_llm.test_rardar_trending_store import board


@pytest.mark.asyncio
async def test_history_publishes_despite_both_sources_failing_and_no_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(trending_boards, "fetch_board", AsyncMock(side_effect=TimeoutError()))
    review = AsyncMock(return_value={"date": "2026-09-13", "projectIds": ["saved-id"]})
    result = await refresh.run_refresh(
        tmp_path, now=datetime(2026, 9, 13, 1, tzinfo=UTC), trigger="automatic", review_work=review
    )
    assert review.await_count == 1
    assert result["historyReview"]["status"] == "published"
    assert result["providerCalls"] == 0
    assert result["status"] == "partial"


@pytest.mark.asyncio
async def test_failed_local_review_gets_compensation_without_source_refetch(tmp_path, monkeypatch):
    from app.services import rardar_trending as service

    async def fetch(source, **kwargs):
        value = board(source, ["o/r"])
        value["targetPeriodDate"] = kwargs["target_date"]
        return value

    fetch_mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(trending_boards, "fetch_board", fetch_mock)
    monkeypatch.setattr(service, "saved_materials", lambda _: {})
    monkeypatch.setattr(service, "refresh_metadata", AsyncMock(return_value={"failed": [], "pending": 0}))
    review = AsyncMock(side_effect=[ValueError("local"), {"date": "2026-09-13", "projectIds": []}])
    first = await refresh.run_refresh(
        tmp_path, now=datetime(2026, 9, 13, 1, tzinfo=UTC), trigger="automatic", review_work=review
    )
    assert first["historyReview"]["status"] == "failed"
    second = await refresh.run_refresh(
        tmp_path, now=datetime(2026, 9, 13, 3, tzinfo=UTC), trigger="automatic", review_work=review
    )
    assert second["historyReview"]["status"] == "published"
    assert second["automaticRound"] == "compensation"
    assert fetch_mock.await_count == 2
    assert len(store.load_snapshot(tmp_path)["projects"]) == 1


def test_daily_review_get_never_creates_batch(tmp_path, monkeypatch):
    from app.services import rardar_trending as service

    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    assert service.history()["projects"] == []
    assert not (tmp_path / "historical-daily").exists()
