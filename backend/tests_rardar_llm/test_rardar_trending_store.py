"""Real storage entrypoints, synthetic boards; no source or Provider requests."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.rardar import trending_store as store
from app.services.llm.provider_budget import atomic, digest


def board(source, repositories, *, when=None, day=None):
    when = when or datetime.now(UTC).isoformat()
    return {
        "source": source,
        "status": "healthy",
        "period": "daily",
        "sourceDate": day,
        "sourceUrl": "https://github.com/trending?since=daily" if source == "github" else "https://trendshift.io/",
        "fetchedAt": when,
        "entries": [
            {"repository": repo, "rank": index + 1, "description": "Actual fixture description", "totalStars": None}
            for index, repo in enumerate(repositories)
        ],
    }


def test_union_preserves_complete_boards_without_profiles_or_observation(tmp_path):
    github = [f"org/repo-{index}" for index in range(31)]
    trendshift = ["org/repo-0", "outside/new-project"]
    result = store.publish_sources(tmp_path, [board("github", github), board("trendshift", trendshift)])
    snapshot = store.load_snapshot(tmp_path)
    assert result["count"] == 32
    assert {p["repository"] for p in snapshot["projects"]} == set(github + trendshift)
    # With growth and total Stars unknown, the full union uses repository-name order.
    assert [p["repository"] for p in snapshot["projects"]] == sorted(set(github + trendshift))
    overlap = snapshot["projects"][0]
    assert overlap["dualListed"]
    assert len(overlap["appearances"]) == 2
    assert all(p["profile"] is None and p["totalStars"] is None for p in snapshot["projects"])
    assert not (tmp_path / "observations").exists()


def test_repeat_check_does_not_create_serving_or_inflate_appearance_count(tmp_path):
    first = board("github", ["org/repo"], day="2026-09-10")
    second = deepcopy(first)
    second["fetchedAt"] = (datetime.fromisoformat(first["fetchedAt"]) + timedelta(minutes=2)).isoformat()
    initial = store.publish_sources(tmp_path, [first])
    repeated = store.publish_sources(tmp_path, [second])
    assert not repeated["changed"]
    assert repeated["generationId"] == initial["generationId"]
    assert store.historical_snapshot(tmp_path)["projects"][0]["historyAppearances"] == 1


def test_failed_source_without_cache_is_visible_not_silent_success(tmp_path):
    store.publish_sources(tmp_path, [board("github", ["org/repo"]), {"source": "trendshift", "status": "failed"}])
    sources = {s["source"]: s for s in store.load_snapshot(tmp_path)["sources"]}
    assert set(sources) == {"github", "trendshift"}
    assert sources["trendshift"]["status"] == "failed"


def test_failed_source_keeps_cache_but_removes_dual_badge_then_recovers(tmp_path):
    captures = [board("github", ["org/repo"]), board("trendshift", ["org/repo"])]
    store.publish_sources(tmp_path, captures)
    assert store.load_snapshot(tmp_path)["projects"][0]["dualListed"]
    store.publish_sources(tmp_path, [captures[0], {"source": "trendshift", "status": "failed"}])
    partial = store.load_snapshot(tmp_path)
    assert len(partial["projects"]) == 1
    assert not partial["projects"][0]["dualListed"]
    assert {s["source"]: s["status"] for s in partial["sources"]}["trendshift"] == "stale"
    store.publish_sources(tmp_path, captures)
    assert store.load_snapshot(tmp_path)["projects"][0]["dualListed"]


def test_different_publisher_dates_never_get_dual_badge(tmp_path):
    store.publish_sources(
        tmp_path, [board("github", ["org/repo"], day="2026-09-10"), board("trendshift", ["org/repo"], day="2026-09-09")]
    )
    assert not store.load_snapshot(tmp_path)["projects"][0]["dualListed"]


def test_empty_parse_preserves_previous_content(tmp_path):
    store.publish_sources(tmp_path, [board("github", ["org/repo"])])
    store.publish_sources(tmp_path, [board("github", [])])
    assert [p["repository"] for p in store.load_snapshot(tmp_path)["projects"]] == ["org/repo"]


def test_modified_snapshot_hash_is_rejected(tmp_path):
    installed = store.publish_sources(tmp_path, [board("github", ["org/repo"])])
    path = tmp_path / "trending-boards" / "generations" / f"{installed['generationId']}.json"
    raw = store.read_json(path)
    raw["projection"]["projects"] = []
    atomic(path, raw)
    with pytest.raises(ValueError, match="trending_generation_integrity"):
        store.load_snapshot(tmp_path)


def test_internally_inconsistent_generation_is_rejected_even_with_valid_hash(tmp_path):
    installed = store.publish_sources(tmp_path, [board("github", ["org/repo"])])
    root = tmp_path / "trending-boards"
    raw = store.read_json(root / "generations" / f"{installed['generationId']}.json")
    raw["projection"]["projects"] = []
    identifier = "boards-" + digest(raw)
    atomic(root / "generations" / f"{identifier}.json", raw)
    with pytest.raises(ValueError):
        store.load_snapshot(tmp_path, identifier)


def test_generation_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError, match="trending_generation_invalid"):
        store.load_snapshot(tmp_path, "../current")


@pytest.mark.asyncio
async def test_exhausted_daily_budget_keeps_history_and_does_not_resolve_model(tmp_path, monkeypatch):
    from app.services import rardar_llm_control, rardar_trending
    from app.services.llm import daily_provider_budget

    store.publish_sources(tmp_path, [board("github", ["org/repo"])])
    monkeypatch.setattr(rardar_trending, "saved_materials", lambda _target: {})
    ledger = SimpleNamespace(snapshot=lambda: {"remaining": 0})
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", AsyncMock(return_value=(ledger, {})))
    route = AsyncMock(side_effect=AssertionError("must not resolve model"))
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", route)
    result = await rardar_trending.historical_work(tmp_path, {}, lambda: None)
    assert result["waitReason"] == "daily_budget_exhausted"
    assert result["checked"] == 1
    route.assert_not_awaited()
    assert len(store.historical_snapshot(tmp_path)["projects"]) == 1


@pytest.mark.asyncio
async def test_saved_profile_reuse_is_read_only_and_tampering_is_omitted(tmp_path):
    from app.services import rardar_trending
    from tests_rardar_llm.test_managed_materials import seed
    from tests_rardar_selection.test_profile_cache_v2 import _project

    path = await seed(tmp_path)
    original = path.read_bytes()
    materials = rardar_trending.saved_materials(tmp_path)
    assert _project().repository.lower() in materials
    assert materials[_project().repository.lower()]["profile"]["summary"]
    assert "totalStars" not in materials[_project().repository.lower()]
    assert path.read_bytes() == original
    raw = store.read_json(path)
    raw["profile"]["repository"] = "forged/repository"
    atomic(path, raw)
    assert rardar_trending.saved_materials(tmp_path) == {}


@pytest.mark.asyncio
async def test_compatible_history_never_allocates_model_budget(tmp_path, monkeypatch):
    from app.services import rardar_trending
    from app.services.llm import daily_provider_budget
    from tests_rardar_llm.test_managed_materials import seed
    from tests_rardar_selection.test_profile_cache_v2 import _project

    await seed(tmp_path)
    store.publish_sources(tmp_path, [board("github", [_project().repository])])
    budget = AsyncMock(side_effect=AssertionError("cached material must not need budget"))
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", budget)
    result = await rardar_trending.historical_work(tmp_path, {}, lambda: None)
    assert result["reused"] == 1
    assert result["processed"] == 0
    assert result["remaining"] == 0
    budget.assert_not_awaited()
