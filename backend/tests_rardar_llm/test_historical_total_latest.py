"""Historical cumulative facts: actual source dates, safe cache fallback, no IO on GET."""

from copy import deepcopy

from app.integrations.rardar import trending_metadata as metadata, trending_store as store
from app.integrations.rardar.trending_metrics import select_historical_total
from app.services.llm.provider_budget import atomic, digest
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_llm.test_trending_metadata import project, response


def test_late_historical_fetch_does_not_beat_newer_source_and_decline_is_valid():
    rows = [
        {"source": "trendshift", "sourceDate": "2026-09-10", "fetchedAt": "2026-09-13T10:00:00Z", "totalStars": 900},
        {"source": "trendshift", "sourceDate": "2026-09-12", "fetchedAt": "2026-09-13T01:00:00Z", "totalStars": 800},
    ]
    value = {}
    select_historical_total(value, rows)
    assert value["totalStars"] == 800
    assert value["totalStarsSource"]["sourceDate"] == "2026-09-12"
    assert value["totalStarsSource"]["observedAt"] is None
    assert value["totalStarsSource"]["timeKind"] == "source_date"
    rows[1]["totalStars"] = 0
    select_historical_total(value, rows)
    assert value["totalStars"] == 0
    rows[1]["totalStars"] = None
    select_historical_total(value, rows)
    assert value["totalStars"] == 900
    select_historical_total(value, [{**rows[0], "totalStars": None}])
    assert value["totalStars"] is None


def test_metadata_latest_decline_zero_null_retains_time_and_today_unchanged(tmp_path):
    meta = {**response(), "stargazers_count": 100, "description": "真实仓库介绍"}
    metadata.save(tmp_path, project(), meta)
    meta["stargazers_count"] = 80
    metadata.save(tmp_path, project(), meta)
    historical = metadata.apply({"kind": "historical", "projects": [project()]}, tmp_path)["projects"][0]
    assert historical["totalStars"] == 80
    assert historical["description"] == "真实仓库介绍"
    assert historical["totalStarsSource"]["source"] == "github_metadata"
    assert metadata.apply({"projects": [project()]}, tmp_path)["projects"][0]["totalStars"] == 123
    meta["stargazers_count"] = 0
    zero = metadata.save(tmp_path, project(), meta)
    meta["stargazers_count"] = None
    missing = metadata.save(tmp_path, project(), meta)
    assert missing["totalStars"] == 0
    assert missing["totalStarsFetchedAt"] == zero["totalStarsFetchedAt"]


def test_legacy_metadata_is_read_without_inventing_stars(tmp_path):
    saved = metadata.save(tmp_path, project(), response())
    for key in ("description", "totalStars", "totalStarsFetchedAt"):
        saved.pop(key)
    atomic(metadata._path(tmp_path, "owner/repo"), {"schemaVersion": 1, "payload": saved, "digest": digest(saved)})
    result = metadata.apply({"kind": "historical", "projects": [project()]}, tmp_path)["projects"][0]
    assert result["totalStars"] == 123
    assert "totalStarsSource" not in result


def test_metadata_does_not_carry_star_fallback_across_repository_identity(tmp_path):
    unknown_id = {**project(), "githubRepositoryId": None}
    metadata.save(tmp_path, unknown_id, {**response(), "stargazers_count": 400})
    metadata.save(tmp_path, unknown_id, {**response(), "id": 43, "stargazers_count": None})
    assert metadata.read(tmp_path, unknown_id)["totalStars"] is None


def test_history_keeps_old_valid_value_when_latest_archive_omits_it(tmp_path):
    record = {
        "source": "github",
        "sourceUrl": "https://trendshift.io/github-trending-repositories",
        "period": "historical-all-days",
        "fetchedAt": "2026-09-10T00:00:00Z",
        "entries": [{"repository": "owner/repo", "reportedAppearanceCount": 1, "totalStars": 50}],
    }
    store.import_historical_evidence(tmp_path, record)
    newer = deepcopy(record)
    newer["fetchedAt"] = "2026-09-11T00:00:00Z"
    newer["entries"][0]["totalStars"] = None
    store.import_historical_evidence(tmp_path, newer)
    result = store.historical_snapshot(tmp_path)["projects"][0]
    assert result["totalStars"] == 50
    assert result["totalStarsSource"]["fetchedAt"] == record["fetchedAt"]
    assert result["totalStarsSource"]["timeKind"] == "unknown"


def test_history_ignores_growth_but_preserves_original_capture(tmp_path):
    source = board("github", ["owner/repo"])
    source["entries"][0].update(totalStars=12, reportedDelta=5)
    store.publish_sources(tmp_path, [source])
    before = {path: path.read_bytes() for path in (tmp_path / "trending-boards/captures").glob("*.json")}
    history = store.historical_snapshot(tmp_path)["projects"][0]
    assert "reportedDelta" not in history["appearances"][0]
    assert store.load_snapshot(tmp_path)["projects"][0]["primaryGrowth"]["value"] == 5
    assert all(path.read_bytes() == original for path, original in before.items())
