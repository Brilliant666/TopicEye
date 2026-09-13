"""The full saved union and detail access survive the selected-growth view."""

from copy import deepcopy

import pytest

from app.core.config import settings
from app.integrations.rardar import trending_store as store
from app.integrations.rardar.trending_metrics import qualifying_today
from app.services import rardar_trending as service
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_llm.test_trending_primary_growth import appearance


@pytest.mark.parametrize(
    "gh,ts,selected", [(199, 900, False), (200, 1, True), (0, 900, False), (None, 200, True), (None, None, False)]
)
def test_boundary_and_primary_source(gh, ts, selected):
    snapshot = {
        "projects": [
            {
                "repository": "o/r",
                "totalStars": 1,
                "appearances": [appearance("github", gh), appearance("trendshift", ts)],
            }
        ],
        "sources": [],
    }
    original = deepcopy(snapshot)
    view = qualifying_today(snapshot, minimum=200)
    assert bool(view["projects"]) == selected
    assert view["unknownGrowthCount"] == int(gh is None and ts is None)
    assert snapshot == original


def test_entire_union_filtered_sorted_before_page_and_cached_state_preserved():
    snapshot = {
        "projects": [
            {"repository": f"o/r{i:02}", "totalStars": i, "appearances": [appearance("github", i * 10)]}
            for i in range(50)
        ],
        "sources": [{"status": "stale", "fetchedAt": "2026-09-12T00:00:00Z"}],
        "state": "ready",
    }
    view = qualifying_today(snapshot, minimum=200)
    assert len(view["projects"]) == 30
    assert [p["primaryGrowth"]["value"] for p in view["projects"]] == list(range(490, 199, -10))
    assert view["sources"] == snapshot["sources"]
    assert view["projects"][20]["displayRank"] == 21
    assert qualifying_today({**snapshot, "projects": []}, minimum=200)["state"] == "ready"
    assert qualifying_today({"state": "not_synced", "projects": []}, minimum=200)["state"] == "not_synced"


def test_real_service_filters_but_old_detail_is_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    source = board("github", ["o/low", "o/high"])
    source["entries"][0]["reportedDelta"] = 199
    source["entries"][1]["reportedDelta"] = 200
    result = store.publish_sources(tmp_path, [source])
    raw = store.load_snapshot(tmp_path)
    view = service.today()
    assert view["rawProjectCount"] == 2
    assert [p["repository"] for p in view["projects"]] == ["o/high"]
    low = next(p for p in raw["projects"] if p["repository"] == "o/low")
    assert service.detail(low["projectId"], result["generationId"])["primaryGrowth"]["value"] == 199
    assert len(store.load_snapshot(tmp_path)["projects"]) == 2
