"""A historical name is not proof that two numeric repositories are one."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.integrations.rardar import trending_store as store
from app.schemas.rardar_product import SharedProjectInsightRequest
from app.services import rardar_project_insights as insights, rardar_trending as service
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_llm.test_shared_material_consumers import _metadata, _seed
from tests_rardar_selection.test_profile_cache_v2 import _project

REPOSITORY = "example/reused-name"


def captures(target, old_id, new_id):
    for day, identifier, stars in [(24, old_id, 1000), (25, new_id, 9000)]:
        source = board("github", [REPOSITORY], when=f"2026-10-{day}T01:00:00+00:00", day=f"2026-10-{day}")
        source["entries"][0].update(githubRepositoryId=identifier, totalStars=stars, reportedDelta=250)
        store.publish_sources(target, [source])


@pytest.mark.asyncio
async def test_reused_name_does_not_transfer_history_stars_or_shared_material(tmp_path, monkeypatch):
    project = await _seed(tmp_path, REPOSITORY, 42)
    _metadata(tmp_path, project)
    captures(tmp_path, 42, 43)
    originals = {p.name: p.read_bytes() for p in (tmp_path / "trending-boards/captures").glob("*.json")}
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    raw = store.historical_snapshot(tmp_path)["projects"][0]
    assert raw["identityState"] == "needs_identity_evidence"
    assert raw["identityRepositoryIds"] == [42, 43]
    assert raw["githubRepositoryId"] is raw["totalStars"] is raw["historyAppearances"] is None
    assert {row["githubRepositoryId"] for row in raw["appearances"]} == {42, 43}
    assert raw["unresolvedAppearances"] == 2
    detail = service.detail(project_id := service.project_id_for_repository(REPOSITORY), None, historical=True)
    assert detail["profile"] is detail["displayProfile"] is detail["displayEvidence"] is None
    assert detail["githubRepositoryId"] is detail["totalStars"] is None
    qualification = await service.historical_work(tmp_path, {}, lambda: None, qualification_only=True)
    assert qualification["qualification"]["today"]["zeroModelEligible"] == 0
    denied = AsyncMock(side_effect=AssertionError("unresolved identity must not fetch or call a model"))
    monkeypatch.setattr(insights, "collect_project_evidence", denied)
    monkeypatch.setattr(insights, "_explain_project_with_evidence", denied)
    request = SharedProjectInsightRequest(generationId=detail["generationId"], context="historical_hot")
    read = await insights.read_project_insight(project_id, request)
    started = await insights.start_project_insight(project_id, request)
    assert read.state == started.state == "unavailable"  # not a Provider/budget wait
    assert read.errorCode == started.errorCode == "repository_identity_evidence_required"
    denied.assert_not_awaited()
    assert {p.name: p.read_bytes() for p in (tmp_path / "trending-boards/captures").glob("*.json")} == originals
    # Today's explicitly versioned facts remain exactly the new source, not a
    # fabricated old/new identity merge or a rewritten historical capture.
    current = store.load_snapshot(tmp_path)["projects"][0]
    assert current["githubRepositoryId"] == 43 and current["totalStars"] == 9000


@pytest.mark.parametrize("old_id", [None, 42])
def test_consistent_numeric_identity_keeps_legacy_name_history_readable(tmp_path, old_id):
    captures(tmp_path, old_id, 42)
    value = store.historical_snapshot(tmp_path)["projects"][0]
    assert value.get("identityState") is None
    assert value["githubRepositoryId"] == 42
    assert value["historyAppearances"] == 2 and value["totalStars"] == 9000


@pytest.mark.asyncio
@pytest.mark.parametrize("capture_old", [False, True])
async def test_legacy_serving_cannot_restore_stars_or_material_to_conflicting_name(tmp_path, monkeypatch, capture_old):
    project = await _seed(tmp_path, REPOSITORY, 42)
    _metadata(tmp_path, project)
    if capture_old:
        captures(tmp_path, 42, 43)
    else:
        source = board("github", [REPOSITORY], when="2026-10-25T01:00:00+00:00", day="2026-10-25")
        source["entries"][0].update(githubRepositoryId=43, totalStars=9000, reportedDelta=250)
        store.publish_sources(tmp_path, [source])
    fact = _project().model_copy(
        update={"repository": REPOSITORY, "githubRepositoryId": 42, "htmlUrl": f"https://github.com/{REPOSITORY}"}
    )
    retained = SimpleNamespace(
        generationId="retained-source", servingGenerationId="retained-serving", exactRanked=[fact]
    )
    monkeypatch.setattr(service, "_retained_serving_snapshots", lambda *_a, **_kw: [retained])
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    detail = service.detail(service.project_id_for_repository(REPOSITORY), None, historical=True)
    assert detail["identityState"] == "needs_identity_evidence"
    assert detail["identityRepositoryIds"] == [42, 43]
    assert detail["githubRepositoryId"] is detail["totalStars"] is detail["profile"] is None
    assert detail["historicalRardarEvidence"][0]["githubRepositoryId"] == 42


@pytest.mark.asyncio
async def test_old_name_only_history_does_not_follow_a_conflicting_known_metadata_identity(tmp_path, monkeypatch):
    project = await _seed(tmp_path, REPOSITORY, 42)
    _metadata(tmp_path, project)
    captures(tmp_path, None, 43)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    row = store.historical_snapshot(tmp_path)["projects"][0]
    assert row["identityState"] == "needs_identity_evidence"
    assert row["identityRepositoryIds"] == [42, 43]
    assert row["githubRepositoryId"] is row["totalStars"] is None
    detail = service.detail(service.project_id_for_repository(REPOSITORY), None, historical=True)
    assert detail["profile"] is None


def test_same_day_source_identity_disagreement_is_read_only_uncertainty_not_dual_listing(tmp_path):
    sources = []
    for source, identifier in [("github", 42), ("trendshift", 43)]:
        value = board(source, [REPOSITORY], when="2026-10-25T01:00:00+00:00", day="2026-10-25")
        value["entries"][0].update(githubRepositoryId=identifier, totalStars=1000 * identifier, reportedDelta=250)
        sources.append(value)
    publication = store.publish_sources(tmp_path, sources)
    path = tmp_path / "trending-boards/generations" / f"{publication['generationId']}.json"
    original = path.read_bytes()
    value = store.load_snapshot(tmp_path)["projects"][0]
    assert value["identityState"] == "needs_identity_evidence"
    assert value["identityRepositoryIds"] == [42, 43]
    assert value["githubRepositoryId"] is value["totalStars"] is None
    assert not value["dualListed"]
    assert {row["githubRepositoryId"] for row in value["appearances"]} == {42, 43}
    # Keep the existing source-primary growth and >=200 semantics. A name-level
    # uncertainty notice does not invent growth or silently delete source facts.
    assert value["primaryGrowth"]["value"] == 250
    assert value["primaryGrowth"]["source"] == "github"
    assert path.read_bytes() == original


@pytest.mark.asyncio
async def test_new_bound_identity_failure_hides_current_overlay_not_pinned_historical_result(tmp_path, monkeypatch):
    project = await _seed(tmp_path, REPOSITORY, 42)
    _metadata(tmp_path, project)
    captures(tmp_path, 42, 42)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    current = store.load_snapshot(tmp_path)
    generations = tmp_path / "trending-boards/generations"
    old = next(p.stem for p in generations.glob("*.json") if p.stem != current["generationId"])
    service.atomic(
        tmp_path / "trending-boards/material-work.json",
        {
            "_attempts": {
                REPOSITORY: {
                    "status": "invalid",
                    "stage": "source",
                    "nextAction": "needs_identity_evidence",
                    "reason": "repository_identity_mismatch",
                    "sourceGeneration": current["generationId"],
                    "checkedAt": "2026-10-26T01:00:00+00:00",
                }
            }
        },
    )
    identifier = service.project_id_for_repository(REPOSITORY)
    latest = service.detail(identifier, current["generationId"])
    assert latest["identityState"] == "needs_identity_evidence"
    assert latest["profile"] is latest["githubRepositoryId"] is latest["totalStars"] is None
    pinned = service.detail(identifier, old)
    assert pinned["profile"] and pinned["githubRepositoryId"] == 42
    assert pinned.get("identityState") is None
    next_source = board("github", [REPOSITORY], when="2026-10-26T01:00:00+00:00", day="2026-10-26")
    next_source["entries"][0].update(githubRepositoryId=42, totalStars=9500, reportedDelta=300)
    store.publish_sources(tmp_path, [next_source])
    next_current = service.detail(identifier, None)
    assert next_current["identityState"] == "needs_identity_evidence"
    assert next_current["profile"] is None  # a new board date is not new identity proof
    assert service.detail(identifier, old)["profile"]  # no mutation of the pinned original
