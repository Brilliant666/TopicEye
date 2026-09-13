"""Daily historical selection: persisted members, no Star rank or provider IO."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from random import Random

import pytest

from app.integrations.rardar import historical_daily as daily
from app.integrations.rardar.project_identity import project_id_for_repository
from app.integrations.rardar.trending_periods import ZONE
from app.services.llm.provider_budget import atomic, digest


def projects(count):
    return [
        {
            "id": project_id_for_repository(f"owner/project-{index}"),
            "repository": f"owner/project-{index}",
            "githubRepositoryId": index + 1,
            "totalStars": index * 100,
            "profile": {"summary": "真实的项目介绍"},
        }
        for index in range(count)
    ]


def at(day="2026-09-13", hour=9):
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=ZONE)


def test_ten_days_63_candidates_recent_seven_successful_dates_and_oldest_fallback(tmp_path):
    history = []
    candidates = projects(63)
    for offset in range(10):
        # A skipped calendar day is not a successful publication day.
        now = at("2026-12-27") + timedelta(days=offset * 2)
        value = daily.publish(tmp_path, candidates, now=now, trigger="main")
        assert len(value["projectIds"]) == len(set(value["projectIds"])) == 8
        recent = {identifier for batch in history[-7:] for identifier in batch["projectIds"]}
        fresh = {project["id"] for project in candidates} - recent
        assert len(set(value["projectIds"]) - recent) == min(len(fresh), 8)
        if len(fresh) < 8:
            assert fresh <= set(value["projectIds"])
            assert value["fallbackCount"] == 8 - len(fresh)
            last = {identifier: batch["date"] for batch in history for identifier in batch["projectIds"]}
            chosen_old = set(value["projectIds"]) & recent
            remaining_old = recent - chosen_old
            assert max(last[item] for item in chosen_old) <= min(last[item] for item in remaining_old)
        history.append(value)
    assert history[-1]["date"].startswith("2027-01")
    assert len(list((tmp_path / "historical-daily").glob("20*.json"))) == 10


@pytest.mark.parametrize("count", [0, 1, 7, 8])
def test_ten_days_small_empty_and_full_sets_never_fill_or_mutate_same_day(tmp_path, count):
    rows = projects(count)
    for offset in range(10):
        now = at("2026-01-27") + timedelta(days=offset)
        batch = daily.publish(tmp_path, rows, now=now, trigger="main")
        assert len(batch["projectIds"]) == count
        assert daily.publish(tmp_path, projects(63), now=now.replace(hour=11), trigger="compensation") == batch
        assert daily.read_for_date(tmp_path, now.date().isoformat()) == batch


def test_same_day_survives_input_order_star_profile_candidate_changes_and_restart(tmp_path):
    rows = projects(20)
    first = daily.publish(tmp_path, rows, now=at(), trigger="main")
    changed = [{**row, "totalStars": 10**10, "profile": {"summary": "更新后的介绍"}} for row in reversed(rows)]
    assert daily.publish(tmp_path, changed + projects(80)[20:], now=at(hour=11), trigger="compensation") == first
    assert daily.publish(tmp_path, [], now=at(hour=23), trigger="manual") == first
    # Fresh imports/readers and devices read precisely the persisted selection.
    assert daily.read_latest(tmp_path) == first
    assert daily.read_latest(tmp_path, now=at("2026-09-14", 0)) == first
    assert daily.publish(tmp_path, projects(80), now=at("2026-09-14", 8), trigger="main") == first
    assert not (tmp_path / "historical-daily" / "2026-09-14.json").exists()


def test_selection_is_star_independent_and_not_input_order_dependent(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "SystemRandom", lambda: Random(713))
    rows = projects(63)
    first = daily.publish(tmp_path / "a", rows, now=at(), trigger="main")
    changed = [{**row, "totalStars": 10**9 - index} for index, row in enumerate(reversed(rows))]
    second = daily.publish(tmp_path / "b", changed, now=at(), trigger="main")
    assert first["projectIds"] == second["projectIds"]
    assert first["projectIds"] != [row["id"] for row in rows[:8]]


def test_concurrent_publications_commit_one_order_and_one_day(tmp_path):
    def run(index):
        return daily.publish(tmp_path, projects(63 + index), now=at(), trigger="main")

    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(run, range(4)))
    assert all(value == values[0] for value in values)
    assert len(list((tmp_path / "historical-daily").glob("20*.json"))) == 1


def test_invalid_or_failed_next_publication_preserves_previous_and_does_not_backfill(tmp_path, monkeypatch):
    first = daily.publish(tmp_path, projects(10), now=at(), trigger="main")
    with pytest.raises(ValueError, match="identity_mismatch"):
        daily.publish(tmp_path, [{**projects(1)[0], "id": "wrong"}], now=at("2026-09-15"), trigger="main")
    assert daily.read_latest(tmp_path) == first

    def fail(*args):
        raise OSError("simulated disk write failure")

    monkeypatch.setattr(daily, "atomic", fail)
    with pytest.raises(OSError):
        daily.publish(tmp_path, projects(10), now=at("2026-09-15"), trigger="main")
    assert daily.read_latest(tmp_path) == first
    assert daily.publish(tmp_path, projects(20), now=at("2026-09-12"), trigger="catchup") == first
    assert daily.read_for_date(tmp_path, "2026-09-14") is None


def test_reads_are_readonly_and_only_initial_manual_can_publish_before_nine(tmp_path):
    target = tmp_path / "never-created"
    assert daily.read_latest(target) is None
    assert daily.read_for_date(target, "2026-09-13") is None
    assert not target.exists()
    assert daily.publish(target, projects(8), now=at(hour=8), trigger="main") is None
    first = daily.publish(target, projects(8), now=at(hour=8), trigger="manual_initialization")
    assert first["trigger"] == "manual_initialization"
    assert daily.publish(target, projects(9), now=at("2026-09-14", 8), trigger="manual_initialization") == first


def test_corruption_and_unsafe_date_fail_closed(tmp_path):
    batch = daily.publish(tmp_path, projects(8), now=at(), trigger="main")
    path = tmp_path / "historical-daily" / "2026-09-13.json"
    atomic(path, {"schemaVersion": 1, "batch": {**batch, "projectIds": []}, "digest": digest(batch)})
    with pytest.raises(ValueError, match="digest_mismatch"):
        daily.read_latest(tmp_path)
    with pytest.raises(ValueError):
        daily.read_for_date(tmp_path, "../anything")


def test_naive_time_and_duplicate_numeric_identity_rejected(tmp_path):
    with pytest.raises(ValueError, match="timezone_required"):
        daily.publish(tmp_path, projects(8), now=datetime(2026, 9, 13, 9), trigger="main")
    row = projects(1)[0]
    with pytest.raises(ValueError, match="duplicate_identity"):
        daily.publish(tmp_path, [row, {**row, "githubRepositoryId": 999}], now=at(), trigger="main")
