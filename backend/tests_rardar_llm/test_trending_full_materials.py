"""Original Profile fidelity and shared board/history reads, using synthetic IO only."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.integrations.rardar import trending_store as store
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
from app.integrations.rardar.serving import ServingProjectionLoader, clear_serving_cache
from app.services import rardar_trending as service
from tests_rardar_adapter.test_serving import _install_two, _root
from tests_rardar_llm.test_managed_materials import seed
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import _project


@pytest.mark.asyncio
async def test_shared_display_preserves_every_original_profile_and_evidence_field(tmp_path):
    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    material = service.saved_materials(tmp_path)[_project().repository.lower()]
    assert material["displayProfile"] == record.profile.model_dump(mode="json")
    assert material["displayEvidence"] == record.evidence.model_dump(mode="json")
    assert material["displayProfile"]["capabilities"][0]["title"]
    assert material["displayProfile"]["capabilities"][0]["evidenceRefs"]
    assert material["displayProfile"]["selectedSections"]
    assert material["profile"]["limitations"] is None  # no fabricated empty analysis
    assert not {"rank", "totalStars", "observedStarDelta", "windowEndedAt"} & material.keys()
    loaded = service.load_saved_project_profile(tmp_path, _project().repository)
    assert loaded == (record.profile, record.evidence)


@pytest.mark.asyncio
async def test_newly_exposed_claims_and_path_bindings_are_not_unchecked(tmp_path):
    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    invalid = record.profile.model_copy(update={"productFormsZh": ["Unsupported product form"]})
    with pytest.raises(ValueError, match="historical_profile_reference_invalid"):
        service.project_material(invalid, record.evidence)
    invalid = record.profile.model_copy(update={"readmeBlobSha": "f" * 40})
    with pytest.raises(ValueError, match="historical_profile_binding_invalid"):
        service.project_material(invalid, record.evidence)


@pytest.mark.asyncio
async def test_today_and_history_read_new_material_without_source_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    installed = store.publish_sources(tmp_path, [board("github", [_project().repository])])
    before = (tmp_path / "trending-boards" / "current.json").read_bytes()
    assert service.today()["projects"][0]["displayProfile"] is None
    await seed(tmp_path)
    today, history = service.today(), service.history()
    first, second = today["projects"][0], history["projects"][0]
    assert first["displayProfile"] == second["displayProfile"]
    assert first["displayEvidence"] == second["displayEvidence"]
    assert today["generationId"] == installed["generationId"]
    assert (tmp_path / "trending-boards" / "current.json").read_bytes() == before
    detail = service.detail(first["projectId"], installed["generationId"])
    historical = service.detail(first["projectId"], None, historical=True)
    assert detail["displayProfile"] == historical["displayProfile"] == first["displayProfile"]
    assert detail["displayProfile"]["generationId"] == "fixture"  # no rebinding to board
    assert detail["appearances"][0]["reportedDelta"] is None


@pytest.mark.asyncio
async def test_known_repository_id_conflict_never_inherits_another_reading(tmp_path):
    await seed(tmp_path)
    source = board("github", [_project().repository])
    source["entries"][0]["githubRepositoryId"] = _project().githubRepositoryId + 1
    store.publish_sources(tmp_path, [source])
    projected = store.apply_materials(store.load_snapshot(tmp_path), service.saved_materials(tmp_path))
    assert projected["projects"][0]["displayProfile"] is None
    assert projected["projects"][0]["profile"] is None


@pytest.mark.asyncio
async def test_cache_store_timestamp_does_not_promote_older_profile(tmp_path):
    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    newer = record.profile.model_copy(update={"generatedAt": record.profile.generatedAt + timedelta(days=1)})
    # An independently validated published interpretation is newer than an
    # envelope copied/migrated later; generatedAt, not storedAt, decides.
    from unittest.mock import patch

    published = SimpleNamespace(profile=newer, evidence=record.evidence, project=_project())
    with patch.object(service, "_retained_serving_details", return_value=iter([published])):
        result = service.saved_materials(tmp_path)[_project().repository.lower()]
    assert result["displayProfile"]["generatedAt"] == newer.generatedAt.isoformat().replace("+00:00", "Z")
    assert result["material"]["sourceKind"] == "published_serving"


def test_retained_publication_is_read_through_source_manifest_and_not_current_only(tmp_path, monkeypatch):
    root = _root(tmp_path)
    _install_two(root)
    loader = ServingProjectionLoader(root)
    old, _ = loader.load_today_with_etag("fixture-explosion-a")
    current, _ = loader.load_today_with_etag()
    assert old.generationId != current.generationId
    # Keep the actual retained source pointer but remove current as a fixture
    # of migration to boards; no manufactured trusted pointer is introduced.
    (root / "serving" / "current.json").unlink()
    clear_serving_cache()
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(root))
    materials = service.saved_materials(root)
    assert old.exactRanked[0].repository.lower() in materials
    snapshot = service.history()
    row = next(p for p in snapshot["projects"] if p["repository"] == old.exactRanked[0].repository.lower())
    assert row["displayProfile"] is not None
    assert row["appearances"] == []
    assert not row["dualListed"]
    evidence = next(e for e in row["historicalRardarEvidence"] if e["sourceGeneration"] == old.generationId)
    assert evidence["rank"] == old.exactRanked[0].rank
    assert evidence["windowEndedAt"] == old.exactRanked[0].windowEndedAt.isoformat()
    assert service.today()["projects"] == []  # archive never inserted into Today


def test_corrupt_retained_publication_does_not_become_healthy_material(tmp_path):
    root = _root(tmp_path)
    _install_two(root)
    for path in (root / "serving" / "sources").glob("*.json"):
        pointer = json.loads(path.read_bytes())
        target = root / "serving" / "generations" / pointer["servingGenerationId"] / "manifest.json"
        target.write_bytes(b"{}")
    clear_serving_cache()
    assert service.saved_materials(root) == {}


def test_known_source_repository_identity_stays_bound_inside_board_generation(tmp_path):
    source = board("github", ["public/project"])
    source["entries"][0]["githubRepositoryId"] = 123
    installed = store.publish_sources(tmp_path, [source])
    root = tmp_path / "trending-boards"
    record = store.read_json(root / "generations" / f"{installed['generationId']}.json")
    record["projection"]["projects"][0]["githubRepositoryId"] = 456
    generation = f"boards-{store.digest(record)}"
    store.atomic(root / "generations" / f"{generation}.json", record)
    with pytest.raises(ValueError, match="trending_projection_facts_invalid"):
        store.load_snapshot(tmp_path, generation)


@pytest.mark.asyncio
async def test_today_newcomer_and_historical_backlog_share_bounded_work(tmp_path, monkeypatch):
    from app.services import rardar_llm_control
    from app.services.llm import daily_provider_budget

    store.publish_sources(tmp_path, [board("github", ["current/new-repo"])])
    store.import_historical_evidence(
        tmp_path,
        {
            "source": "github",
            "period": "historical-all-days",
            "sourceUrl": "https://trendshift.io/github-trending-repositories",
            "fetchedAt": datetime.now(UTC).isoformat(),
            "entries": [{"repository": "archive/huge-project", "reportedAppearanceCount": 30, "totalStars": 1000000}],
        },
    )
    monkeypatch.setattr(service, "saved_materials", lambda _: {})
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 1)
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 20}), {})),
    )
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    original = httpx.AsyncClient

    def response(request):
        name = request.url.path.removeprefix("/repos/")
        return httpx.Response(
            200, json={"full_name": name, "id": 123 if name.startswith("current") else 456, "default_branch": "main"}
        )

    monkeypatch.setattr(
        service.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(response))
    )
    collector = AsyncMock(
        return_value=SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")
    )
    monkeypatch.setattr(service, "collect_official_project_profile", collector)
    monkeypatch.setattr(service, "project_material", lambda *_: {"profile": {"summary": "fixture"}})
    progress = {}
    first = await service.historical_work(tmp_path, progress, lambda: None)
    assert first["processed"] == 1
    assert first["checkedToday"] == first["checkedHistorical"] == 1
    assert collector.await_args.args[0].repository == "current/new-repo"
    second = await service.historical_work(tmp_path, progress, lambda: None)
    assert second["processed"] == 0  # same day's allowance was not reset
    assert collector.await_count == 1
    # Normal next-day progress, persistent rotation; not a new Provider ledger.
    await service.historical_work(tmp_path, {}, lambda: None)
    assert collector.await_args.args[0].repository == "archive/huge-project"


@pytest.mark.asyncio
async def test_explicit_one_project_reuses_saved_reading_without_budget_or_outbound(tmp_path, monkeypatch):
    from app.services.llm import daily_provider_budget

    store.publish_sources(tmp_path, [board("github", [_project().repository])])
    await seed(tmp_path)
    budget = AsyncMock(side_effect=AssertionError("healthy reading must not resolve budget"))
    collector = AsyncMock(side_effect=AssertionError("healthy reading must not collect"))
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", budget)
    monkeypatch.setattr(service, "_collect_project_material", collector)
    identifier = service.project_id_for_repository(_project().repository)
    assert await service.generate_project_material(tmp_path, identifier) == {
        "status": "reused",
        "projectId": identifier,
        "providerCalls": 0,
    }
    budget.assert_not_awaited()
    collector.assert_not_awaited()
    with pytest.raises(LookupError, match="trending_project_not_found"):
        await service.generate_project_material(tmp_path, "not-a-managed-project")


@pytest.mark.asyncio
async def test_explicit_one_project_enters_existing_budget_collector_and_then_reuses(tmp_path, monkeypatch):
    from app.services import rardar_daily_operations, rardar_llm_control
    from app.services.llm import daily_provider_budget

    store.publish_sources(tmp_path, [board("github", [_project().repository]), board("trendshift", ["other/member"])])
    budget = AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 20}), {}))
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", budget)
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="existing-route"))
    monkeypatch.setattr(rardar_daily_operations, "operation_root", lambda: tmp_path / "existing-operations")

    async def collect(target, project, generation, _client, route):
        assert project["repository"] == _project().repository.lower()
        assert generation.startswith("boards-")
        assert route == "existing-route"
        # Simulated processing persists a real schema-valid, evidence-bound
        # synthetic record. No runtime data or actual Provider is accessed.
        path = await seed(target)
        record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
        return SimpleNamespace(profile=record.profile, evidence=record.evidence, profile_cache_state="rebuilt")

    collector = AsyncMock(side_effect=collect)
    monkeypatch.setattr(service, "_collect_project_material", collector)
    identifier = service.project_id_for_repository(_project().repository)
    first = await service.generate_project_material(tmp_path, identifier)
    assert first["status"] == "processed"
    assert first["providerCalls"] == 0  # fixture collector, not a real model claim
    assert collector.await_count == 1
    second = await service.generate_project_material(tmp_path, identifier)
    assert second["status"] == "reused"
    assert budget.await_count == collector.await_count == 1
    assert not (tmp_path / "trending-boards" / "material-work.json").exists()


@pytest.mark.asyncio
async def test_explicit_one_project_budget_exhaustion_does_not_collect(tmp_path, monkeypatch):
    from app.services.llm import daily_provider_budget

    store.publish_sources(tmp_path, [board("github", ["outside/new"])])
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 0}), {})),
    )
    collector = AsyncMock(side_effect=AssertionError("exhausted budget must not collect"))
    monkeypatch.setattr(service, "_collect_project_material", collector)
    result = await service.generate_project_material(tmp_path, service.project_id_for_repository("outside/new"))
    assert result == {"status": "pending", "waitReason": "daily_budget_exhausted", "providerCalls": 0}
    collector.assert_not_awaited()
