"""Growth display over immutable v1 captures; no network, database or model calls."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.integrations.rardar import trending_store as store
from app.services.llm.provider_budget import atomic
from tests_rardar_llm.test_rardar_trending_store import board


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 11, 14, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(store, "datetime", Clock)


def sources():
    """Reduced parsed-capture regression from the 2026-09-11 audit, not raw HTML."""
    github = board("github", ["ayghri/i-have-adhd", "only/github"], when="2026-09-11T12:30:00+00:00")
    trendshift = board(
        "trendshift", ["only/trendshift", "ayghri/i-have-adhd"], when="2026-09-11T13:30:00+00:00", day="2026-09-11"
    )
    github["entries"][0].update(totalStars=40030, reportedDelta=3882, reportedDeltaPeriod="GitHub reported stars today")
    trendshift["entries"][1].update(
        totalStars=40109,
        reportedDelta=None,
        trendshiftStarsGained=1924,
        trendshiftStarsGainedLabel="1.9k",
        trendshiftMetricPeriod="Trendshift daily (source-defined window)",
    )
    return [github, trendshift]


def overlap(snapshot):
    return next(p for p in snapshot["projects"] if p["repository"] == "ayghri/i-have-adhd")


def test_existing_v1_capture_restores_fields_without_mutation_or_union_change(tmp_path):
    result = store.publish_sources(tmp_path, sources())
    path = tmp_path / "trending-boards/generations" / f"{result['generationId']}.json"
    original = path.read_bytes()
    persisted = store.read_json(path)
    assert persisted["projection"]["projects"][0]["totalStars"] == 40030
    assert "trendshiftMetricPeriod" not in overlap(persisted["projection"])["appearances"][1]
    current = store.load_snapshot(tmp_path)
    project = overlap(current)
    assert current["metricSchemaVersion"] == 2
    assert project["totalStars"] == 40109
    assert project["totalStarsSource"] == {
        "source": "trendshift",
        "sourceDate": "2026-09-11",
        "fetchedAt": "2026-09-11T13:30:00+00:00",
        "status": "healthy",
    }
    trend = next(a for a in project["appearances"] if a["source"] == "trendshift")
    assert trend["trendshiftStarsGained"] == 1924
    assert trend["trendshiftStarsGainedLabel"] == "1.9k"
    assert trend["trendshiftMetricPeriod"] == "Trendshift daily (source-defined window)"
    assert trend["totalStars"] == 40109
    assert trend["sourceStatus"] == "healthy"
    assert {p["repository"] for p in current["projects"]} == {
        p["repository"] for p in persisted["projection"]["projects"]
    }
    assert path.read_bytes() == original
    assert not store.publish_sources(tmp_path, sources())["changed"]


@pytest.mark.parametrize("reverse", [False, True])
def test_total_priority_healthy_before_newer_cache_and_not_iteration(tmp_path, reverse):
    captures = sources()
    store.publish_sources(tmp_path, captures[::-1] if reverse else captures)
    store.publish_sources(tmp_path, [captures[0], {"source": "trendshift", "status": "failed"}])
    current = store.load_snapshot(tmp_path)
    assert overlap(current)["totalStars"] == 40030
    assert overlap(current)["totalStarsSource"]["source"] == "github"
    assert not overlap(current)["dualListed"]
    assert next(a for a in overlap(current)["appearances"] if a["source"] == "trendshift")["sourceStatus"] == "stale"
    assert len(current["projects"]) == 3


def test_equal_time_tie_uses_fixed_source_not_rank(tmp_path):
    captures = sources()
    captures[0]["fetchedAt"] = captures[1]["fetchedAt"]
    captures[0]["entries"].reverse()
    for rank, item in enumerate(captures[0]["entries"], 1):
        item["rank"] = rank
    captures[1]["entries"].reverse()
    for rank, item in enumerate(captures[1]["entries"], 1):
        item["rank"] = rank
    store.publish_sources(tmp_path, captures[::-1])
    assert overlap(store.load_snapshot(tmp_path))["totalStars"] == 40030


def test_old_source_date_loses_to_fresh_even_if_fetched_later(tmp_path):
    captures = sources()
    # At Sep 11 14:00 UTC, Sep 10 is the policy's due ended day, not stale.
    captures[1]["sourceDate"] = "2026-09-09"
    store.publish_sources(tmp_path, captures)
    project = overlap(store.load_snapshot(tmp_path))
    assert project["totalStars"] == 40030
    assert project["totalStarsSource"]["status"] == "healthy"


def test_all_stale_retains_latest_value_with_explicit_status(tmp_path):
    captures = sources()
    for capture in captures:
        capture["sourceDate"] = "2026-09-09"
    store.publish_sources(tmp_path, captures)
    project = overlap(store.load_snapshot(tmp_path))
    assert project["totalStars"] == 40109
    assert project["totalStarsSource"]["status"] == "stale"


@pytest.mark.parametrize("missing", [False, True])
def test_zero_is_preserved_and_missing_is_not_invented(tmp_path, missing):
    captures = sources()
    captures[0]["entries"][0].update(totalStars=None, reportedDelta=0)
    captures[1]["entries"][1].update(totalStars=0, trendshiftStarsGained=0)
    if missing:
        del captures[1]["entries"][1]["trendshiftStarsGained"]
    store.publish_sources(tmp_path, captures)
    project = overlap(store.load_snapshot(tmp_path))
    assert project["totalStars"] == 0
    assert project["appearances"][0]["reportedDelta"] == 0
    assert project["appearances"][1]["trendshiftStarsGained"] == (None if missing else 0)
    only = next(p for p in store.load_snapshot(tmp_path)["projects"] if p["repository"] == "only/trendshift")
    assert only["totalStars"] is None
    assert only["totalStarsSource"] is None


def test_pinned_current_detail_uses_same_latest_source_failure_as_list(tmp_path):
    initial = store.publish_sources(tmp_path, sources())
    store.publish_sources(
        tmp_path, [{"source": "github", "status": "failed"}, {"source": "trendshift", "status": "failed"}]
    )
    current = store.load_snapshot(tmp_path)
    pinned = store.load_snapshot(tmp_path, initial["generationId"])
    assert pinned["sources"] == current["sources"]
    assert overlap(pinned)["totalStarsSource"] == overlap(current)["totalStarsSource"]
    assert not overlap(pinned)["dualListed"]


def test_history_keeps_newest_capture_per_source_day_with_one_appearance(tmp_path):
    captures = sources()
    store.publish_sources(tmp_path, captures)
    newer = deepcopy(captures[1])
    newer["fetchedAt"] = "2026-09-11T13:50:00+00:00"
    newer["entries"][1].update(totalStars=40200, trendshiftStarsGained=1950)
    store.publish_sources(tmp_path, [captures[0], newer])
    project = overlap(store.historical_snapshot(tmp_path))
    assert project["historyAppearances"] == 2
    assert project["totalStars"] == 40200
    trend = next(a for a in project["appearances"] if a["source"] == "trendshift")
    assert trend["trendshiftStarsGained"] == 1950
    assert trend["fetchedAt"] == "2026-09-11T13:50:00+00:00"
    assert trend["trendshiftMetricPeriod"]
    assert project["firstSeenAt"] == "2026-09-11T12:30:00+00:00"
    assert project["lastSeenAt"] == "2026-09-11T13:50:00+00:00"


def test_history_first_and_last_seen_compare_absolute_time(tmp_path):
    first = board("github", ["fixture/time-order"], when="2026-09-11T10:00:00+08:00")
    last = board("github", ["fixture/time-order"], when="2026-09-11T03:00:00+00:00")
    first["entries"][0]["reportedDelta"] = 1
    last["entries"][0]["reportedDelta"] = 2
    store.publish_sources(tmp_path, [first])
    store.publish_sources(tmp_path, [last])
    project = store.historical_snapshot(tmp_path)["projects"][0]
    assert project["firstSeenAt"] == first["fetchedAt"]
    assert project["lastSeenAt"] == last["fetchedAt"]
    assert project["historyAppearances"] == 1


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("archive", [False, True])
def test_rardar_only_historical_total_uses_latest_window_without_overriding_external(
    tmp_path, monkeypatch, reverse, external, archive
):
    from app.services import rardar_trending as service
    from tests_rardar_selection.test_profile_cache_v2 import _project

    # Reduced facts from retained UI/UX Skill publications: original traversal
    # reached Aug 28 first although the displayed growth used Sep 9.
    repository = "nextlevelbuilder/ui-ux-pro-max-skill"
    publications = []
    for day, total, delta in [("2026-08-28", 121969, 612), ("2026-09-09", 126131, 320)]:
        ended = datetime.fromisoformat(f"{day}T08:00:00+08:00")
        fact = _project().model_copy(
            update={
                "repository": repository,
                "htmlUrl": f"https://github.com/{repository}",
                "windowStartedAt": ended - timedelta(days=1),
                "windowEndedAt": ended,
                "totalStars": total,
                "observedStarDelta": delta,
            }
        )
        publications.append(SimpleNamespace(project=fact, generationId=day, servingGenerationId=f"serving-{day}"))
    monkeypatch.setattr(
        service, "_retained_serving_details", lambda _target: iter(publications[::-1] if reverse else publications)
    )
    if archive:
        store.import_historical_evidence(
            tmp_path,
            {
                "source": "github",
                "sourceUrl": "https://trendshift.io/github-trending-repositories",
                "period": "historical-all-days",
                "fetchedAt": "2026-09-11T12:00:00+00:00",
                "entries": [{"repository": repository, "reportedAppearanceCount": 3, "totalStars": 127000}],
            },
        )
    if external:
        capture = board("github", [repository], when="2026-09-11T12:30:00+00:00")
        capture["entries"][0]["totalStars"] = 130000
        store.publish_sources(tmp_path, [capture])
    project = service._history_with_materials(tmp_path, {})["projects"][0]
    assert project["historicalRardarEvidence"][0]["totalStars"] == 126131
    assert project["totalStars"] == (130000 if external else 126131)
    if external:
        assert project["totalStarsSource"]["source"] == "github"
    else:
        assert not project.get("totalStarsSource")
        assert project["appearances"] == []
    if archive:
        assert project["historicalEvidence"][0]["reportedAppearanceCount"] == 3


def test_invalid_new_growth_metric_is_rejected_without_erasing_cache(tmp_path):
    captures = sources()
    store.publish_sources(tmp_path, captures)
    invalid = deepcopy(captures[1])
    invalid["entries"][1]["trendshiftStarsGained"] = -1
    store.publish_sources(tmp_path, [captures[0], invalid])
    project = overlap(store.load_snapshot(tmp_path))
    trend = next(a for a in project["appearances"] if a["source"] == "trendshift")
    assert trend["trendshiftStarsGained"] == 1924
    assert trend["sourceStatus"] == "stale"


def test_metric_projection_does_not_hide_invalid_persisted_v1_identity(tmp_path):
    from app.services.llm.provider_budget import digest

    installed = store.publish_sources(tmp_path, sources())
    root = tmp_path / "trending-boards"
    raw = store.read_json(root / "generations" / f"{installed['generationId']}.json")
    raw["projection"]["projects"][0]["repository"] = "forged/repo"
    identifier = "boards-" + digest(raw)
    atomic(root / "generations" / f"{identifier}.json", raw)
    with pytest.raises(ValueError, match="trending_projection_facts_invalid"):
        store.load_snapshot(tmp_path, identifier)
