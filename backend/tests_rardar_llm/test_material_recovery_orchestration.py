"""Persisted recovery through the scheduled worker, never paid test requests."""

import base64
import json
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.integrations.rardar import read_cache, serving_profiles, trending_boards, trending_metadata, trending_store
from app.integrations.rardar.project_identity import project_id_for_repository
from app.integrations.rardar.trending_periods import ZONE
from app.services import rardar_daily_refresh as refresh, rardar_llm_control, rardar_trending as service
from app.services.llm import daily_provider_budget
from tests_rardar_llm.test_rardar_trending_store import board, dated_board
from tests_rardar_selection.test_profile_cache_v2 import MARKDOWN, TREE, _project

ROUTE = "a" * 64


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    entries = {}
    requests = []
    model = AsyncMock(side_effect=AssertionError("recovery tests cannot call a Provider"))
    monkeypatch.setattr(rardar_llm_control, "call_rardar_structured", model)
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value=ROUTE))
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 3)
    monkeypatch.setattr(settings, "RARDAR_DAILY_MATERIAL_SLICES", 1)
    monkeypatch.setattr(settings, "RARDAR_BOARD_READINESS_MINUTES", 60)
    monkeypatch.setattr(settings, "RARDAR_BOARD_COMPENSATION_DELAY_MINUTES", 120)
    budget = AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 0}), {}))
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", budget)

    def response(request):
        requests.append(request.url.path)
        repository = "/".join(request.url.path.removeprefix("/repos/").split("/")[:2])
        entry = entries[repository]
        if request.url.path == f"/repos/{repository}":
            return httpx.Response(200, json=entry["metadata"])
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=TREE)
        return httpx.Response(
            200,
            json={
                "path": "README_ZH.md",
                "sha": entry["sha"],
                "encoding": "base64",
                "content": base64.b64encode(entry["markdown"].encode()).decode(),
            },
            headers={"etag": '"fixture"'},
        )

    @asynccontextmanager
    async def client(_token):
        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(response)
        ) as value:
            yield value

    monkeypatch.setattr(service, "github_material_client", client)
    read_cache.clear()
    return SimpleNamespace(
        target=tmp_path,
        entries=entries,
        requests=requests,
        model=model,
        budget=budget,
        response=response,
    )


def add(recovery, repository, identifier, *, markdown=MARKDOWN):
    project = _project().model_copy(
        update={
            "repository": repository,
            "githubRepositoryId": identifier,
            "htmlUrl": f"https://github.com/{repository}",
        }
    )
    metadata = {
        "id": identifier,
        "full_name": repository,
        "description": project.description,
        "default_branch": project.defaultBranch,
        "language": project.primaryLanguage,
        "topics": project.topics,
        "license": {"spdx_id": project.licenseSpdxId},
        "pushed_at": "2026-10-01T00:00:00Z",
        "stargazers_count": 1000,
    }
    recovery.entries[repository] = {"metadata": metadata, "markdown": markdown, "sha": "a" * 40}
    return project


async def seed(recovery, project, monkeypatch, *, partial=False):
    original = serving_profiles._valid_capabilities
    if partial:
        monkeypatch.setattr(serving_profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))
    try:
        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(recovery.response)
        ) as client:
            collected = await serving_profiles.collect_official_project_profile(
                project,
                "saved-source",
                recovery.target / "profile-cache",
                client=client,
                translate=True,
                allow_model_generation=False,
                model_route_identity=ROUTE,
                save_partial_introduction=True,
            )
    finally:
        monkeypatch.setattr(serving_profiles, "_valid_capabilities", original)
    fact = {"repository": project.repository, "githubRepositoryId": project.githubRepositoryId}
    trending_metadata.save(recovery.target, fact, recovery.entries[project.repository]["metadata"])
    store = recovery.target / "profile-cache" / "profile-store" / "v2" / str(project.githubRepositoryId)
    if store.exists():
        shutil.rmtree(store)  # only this isolated fixture's unfinished final-store simulation
    return collected


def history(recovery, repositories):
    trending_store.import_historical_evidence(
        recovery.target,
        {
            "period": "historical-all-days",
            "source": "github",
            "sourceUrl": "https://trendshift.io/github-trending-repositories",
            "fetchedAt": datetime.now(UTC).isoformat(),
            "entries": [{"repository": repo, "reportedAppearanceCount": 2} for repo in repositories],
        },
    )
    read_cache.clear()


async def work(recovery, progress):
    path = recovery.target / "progress.json"
    result = await service.historical_work(recovery.target, progress, lambda: service.atomic(path, progress))
    read_cache.clear()
    return result


@pytest.mark.asyncio
async def test_corrupt_saved_source_is_item_local_and_never_becomes_a_paid_retry(recovery, monkeypatch):
    # The budget would permit a request; it is the verified integrity failure,
    # not an exhausted allowance, that must prevent paid/source fallback.
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 80}), {})),
    )
    bad = add(recovery, "recovery/a-invalid", 701)
    healthy = add(recovery, "recovery/b-complete", 702)
    await seed(recovery, bad, monkeypatch)
    await seed(recovery, healthy, monkeypatch)
    history(recovery, [bad.repository, healthy.repository])
    path = recovery.target / "profile-cache" / "readmes" / "701" / ("a" * 40 + ".json")
    polluted = json.loads(path.read_bytes())
    polluted["repository"] = "unrelated/unproven-owner"
    path.write_text(json.dumps(polluted), encoding="utf-8")
    before = len(recovery.requests)
    progress = {}
    result = await work(recovery, progress)
    assert result["cacheReassembled"] == 1 and result["providerRequests"] == 0
    assert len(recovery.requests) == before
    records = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"]
    assert records[bad.repository]["status"] == "invalid"
    assert records[bad.repository]["nextAction"] == "not_recoverable_without_new_input"
    assert records[healthy.repository]["status"] == "completed"
    assert service.saved_materials(recovery.target)[healthy.repository]["displayProfile"]
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["identity", "digest"])
async def test_invalid_metadata_isolated_before_qualification_and_paid_work(recovery, monkeypatch, damage):
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 80}), {})),
    )
    bad = add(recovery, "recovery/a-metadata", 751)
    healthy = add(recovery, "recovery/b-readable", 752)
    await seed(recovery, bad, monkeypatch)
    await seed(recovery, healthy, monkeypatch)
    value = board("github", [bad.repository, healthy.repository])
    for item, project in zip(value["entries"], [bad, healthy], strict=True):
        item.update(reportedDelta=250, githubRepositoryId=project.githubRepositoryId)
    if damage == "identity":
        value["entries"][0]["githubRepositoryId"] = 799
    else:
        path = trending_metadata._path(recovery.target, bad.repository)
        record = json.loads(path.read_bytes())
        record["payload"]["description"] = "Unbound changed content"
        path.write_text(json.dumps(record), encoding="utf-8")
    trending_store.publish_sources(recovery.target, [value])
    service.atomic(
        recovery.target / "trending-boards" / "material-work.json",
        {"_successfulChecks": {healthy.repository: {"sourceCheckedAt": datetime.now(UTC).isoformat()}}},
    )
    before = len(recovery.requests)
    progress = {}
    qualification = await service.historical_work(recovery.target, progress, lambda: None, qualification_only=True)
    assert qualification["qualification"]["today"]["zeroModelEligible"] == 1
    assert progress == {}  # qualification is read-only
    result = await work(recovery, progress)
    assert result["cacheReassembled"] == 1 and result["providerRequests"] == 0
    assert len(recovery.requests) == before
    records = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"]
    assert records[bad.repository]["status"] == "invalid"
    assert records[bad.repository]["nextAction"] == (
        "needs_identity_evidence" if damage == "identity" else "not_recoverable_without_new_input"
    )
    assert records[healthy.repository]["status"] == "completed"
    assert len(service.today()["projects"]) == 2  # facts are not removed
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_reuse_rotates_to_later_reassembly_without_spending_historical_admissions(recovery, monkeypatch):
    projects = [add(recovery, f"recovery/project-{index}", 710 + index) for index in range(4)]
    for project in projects[:3]:
        await seed(recovery, project, monkeypatch, partial=True)
    await seed(recovery, projects[3], monkeypatch)
    history(recovery, [p.repository for p in projects])
    progress = {}
    results = [await work(recovery, progress), await work(recovery, progress)]
    assert sum(value.get("cacheReassembled", 0) for value in results) == 1
    assert all(value["providerRequests"] == value["historicalNewAdmitted"] == 0 for value in results)
    materials = service.saved_materials(recovery.target)
    assert materials[projects[3].repository]["materialState"] == "complete"
    assert all(materials[p.repository]["materialState"] == "partial" for p in projects[:3])
    records = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"]
    assert all(record.get("cacheOnly") is True for record in records.values())
    assert all(record["providerRequests"] == record["failures"] == 0 for record in records.values())
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_exhausted_budget_still_checks_new_source_without_creating_a_content_failure(recovery):
    project = add(
        recovery,
        "unseen/english-source",
        730,
        markdown="# Evidence Tool\n\nA toolkit for organizing project evidence.\n\n## Usage\n\nRead the public sources.\n",
    )
    recovery.entries[project.repository]["metadata"]["description"] = "A toolkit for organizing project evidence."
    value = board("github", [project.repository])
    value["entries"][0]["reportedDelta"] = 250
    trending_store.publish_sources(recovery.target, [value])
    progress = {}
    result = await work(recovery, progress)
    assert result["providerRequests"] == result["failed"] == 0
    assert result["status"] == "pending" and result["waitReason"] == "daily_budget_exhausted"
    assert any(path.endswith("/contents/README_ZH.md") for path in recovery.requests)
    readme = recovery.target / "profile-cache" / "readmes" / "730" / ("a" * 40 + ".json")
    assert json.loads(readme.read_bytes())["markdown"] == recovery.entries[project.repository]["markdown"]
    assert trending_metadata.read(recovery.target, {"repository": project.repository})
    assert not list((recovery.target / "profile-cache" / "profile-attempts").rglob("*.json"))
    record = progress["materialWork"]["projects"][project.repository]
    assert record["nextAction"] == "defer_budget" and record["failures"] == 0
    assert service.today()["projects"][0]["repository"] == project.repository
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_eleven_compensation_runs_zero_model_recovery_when_daily_budget_is_exhausted(recovery, monkeypatch):
    project = add(
        recovery,
        "unseen/compensation-source",
        740,
        markdown="# Evidence Tool\n\nA toolkit for organizing project evidence.\n\n## Usage\n\nRead public sources.\n",
    )
    recovery.entries[project.repository]["metadata"]["description"] = "A toolkit for organizing project evidence."
    clock = datetime.now(ZONE).replace(hour=9, minute=0, second=0, microsecond=0)

    async def fetch(source, *, target_date):
        value = dated_board(source, [project.repository], target_date)
        value["entries"][0]["reportedDelta"] = 250
        return value

    monkeypatch.setattr(trending_boards, "fetch_board", AsyncMock(side_effect=fetch))
    budget_available = AsyncMock(return_value=False)
    monkeypatch.setattr(refresh, "material_budget_available", budget_available)
    progress = {}
    completed_work = []

    async def material():
        result = await work(recovery, progress)
        completed_work.append(result)
        return result

    async def qualify():
        return await service.historical_work(recovery.target, progress, lambda: None, qualification_only=True)

    first = await refresh.run_refresh(
        recovery.target, now=clock, trigger="automatic", material_work=material, material_qualification=qualify
    )
    assert first["materials"]["waitReason"] == "daily_budget_exhausted"
    generation = trending_store.load_snapshot(recovery.target)["generationId"]
    # Model a separately saved, interrupted stage becoming available. These are
    # real synthetic source/cache writes, not replacement business responses.
    recovery.entries[project.repository].update(markdown=MARKDOWN, sha="b" * 40)
    await seed(recovery, project, monkeypatch)
    second = await refresh.run_refresh(
        recovery.target,
        now=clock.replace(hour=11),
        trigger="automatic",
        material_work=material,
        material_qualification=qualify,
    )
    assert len(completed_work) == 2 and second["providerCalls"] == 0
    assert second["materials"]["processed"] + second["materials"]["refreshed"] > 0
    assert trending_store.load_snapshot(recovery.target)["generationId"] == generation
    item = service.detail(project_id_for_repository(project.repository), None, historical=True)
    assert item["profile"]["positioning"]
    state = service.read_json(
        recovery.target / "trending-boards" / "daily-refresh" / f"day-{clock.date().isoformat()}.json"
    )
    assert [entry["kind"] for entry in state["rounds"]] == ["main", "compensation"]
    assert state["materialQualification"]["scopes"]["today"]["zeroModelEligible"] == 1
    budget_available.assert_not_awaited()
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected_action", "expected_reason"),
    [
        ({"X-RateLimit-Remaining": "0"}, "retry_transient_later", "profile_source_rate_limited"),
        ({}, "not_recoverable_without_new_input", "source_access_denied"),
        ({"X-RateLimit-Remaining": "5"}, "not_recoverable_without_new_input", "source_access_denied"),
    ],
)
async def test_metadata_403_uses_rate_limit_evidence_and_persists_accurate_next_action(
    recovery, monkeypatch, headers, expected_action, expected_reason
):
    repository = "unseen/metadata-response"
    value = board("github", [repository])
    value["entries"][0]["reportedDelta"] = 250
    trending_store.publish_sources(recovery.target, [value])
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 80}), {})),
    )
    requests = []

    def denied(request):
        requests.append(request.url.path)
        assert request.url.path == f"/repos/{repository}"
        # The same text deliberately appears in every case. Classification must
        # depend on the trusted protocol evidence, not a guessed body keyword.
        return httpx.Response(403, headers=headers, json={"message": "API rate limit exceeded"})

    @asynccontextmanager
    async def client(_token):
        async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(denied)) as value:
            yield value

    monkeypatch.setattr(service, "github_material_client", client)
    progress = {}
    result = await work(recovery, progress)
    assert result["failed"] == 1 and result["providerRequests"] == 0
    saved = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"][repository]
    assert saved["status"] == "failed" and saved["stage"] == "source"
    assert saved["diagnostic"]["httpStatus"] == 403
    assert saved["nextAction"] == expected_action
    assert saved["reason"] == expected_reason
    assert saved["failures"] == 1 and saved["providerRequests"] == 0
    assert requests == [f"/repos/{repository}"]
    assert not list((recovery.target / "profile-cache" / "profile-attempts").rglob("*.json"))
    assert service.today()["projects"][0]["repository"] == repository
    recovery.model.assert_not_awaited()
