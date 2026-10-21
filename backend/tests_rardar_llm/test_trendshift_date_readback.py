"""Synthetic legacy captures: real immutable publication/readback, no network."""

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.rardar import trending_store as store
from tests_rardar_llm.test_rardar_trending_store import board


def test_legacy_mismatched_snapshot_remains_readable_without_false_dual_badge(tmp_path):
    target = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    actual = datetime.now(UTC).date().isoformat()
    github = board("github", ["org/shared"])
    trendshift = board("trendshift", ["org/shared", "org/only"], day=actual)
    for source in (github, trendshift):
        source.update(targetPeriodDate=target, acquisitionMode="daily_snapshot")
    github["entries"][0]["reportedDelta"] = 250
    trendshift["entries"][0]["trendshiftStarsGained"] = 999
    trendshift["entries"][1]["trendshiftStarsGained"] = 220
    installed = store.publish_sources(tmp_path, [github, trendshift])
    path = tmp_path / "trending-boards/generations" / f"{installed['generationId']}.json"
    original = path.read_bytes()
    # Reproduce the old persisted contract; compatibility must not weaken its hash check.
    assert store.read_json(path)["projection"]["projects"][0]["dualListed"] is True
    loaded = store.load_snapshot(tmp_path)
    assert not loaded["projects"][0]["dualListed"]
    source = next(s for s in loaded["sources"] if s["source"] == "trendshift")
    assert source["status"] == "stale"
    assert source["errorCode"] == "trendshift_target_day_unverified"
    assert (source["sourceDate"], source["targetPeriodDate"]) == (actual, target)
    assert [p["primaryGrowth"]["value"] for p in loaded["projects"]] == [250, 220]
    assert path.read_bytes() == original


def test_date_failure_reason_survives_storage_and_old_capture_is_preserved(tmp_path):
    source = board("trendshift", ["org/retained"])
    installed = store.publish_sources(tmp_path, [source])
    failed = {"source": "trendshift", "status": "failed", "errorCode": "trendshift_date_action_missing"}
    checked = store.publish_sources(tmp_path, [failed])
    assert checked["generationId"] == installed["generationId"]
    loaded = store.load_snapshot(tmp_path)
    assert [p["repository"] for p in loaded["projects"]] == ["org/retained"]
    status = next(s for s in loaded["sources"] if s["source"] == "trendshift")
    assert status["errorCode"] == "trendshift_date_action_missing"
    assert status["status"] == "stale"


@pytest.mark.parametrize("unsafe", ["https://user:secret@proxy.invalid", {"secret": "value"}])
def test_source_failure_does_not_persist_arbitrary_error_text(tmp_path, unsafe):
    store.publish_sources(
        tmp_path,
        [board("github", ["org/retained"]), {"source": "trendshift", "status": "failed", "errorCode": unsafe}],
    )
    loaded = store.load_snapshot(tmp_path)
    source = next(s for s in loaded["sources"] if s["source"] == "trendshift")
    assert source["errorCode"] == "source_unavailable_or_invalid"
