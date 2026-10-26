"""Real persisted board -> daily worker -> shared readers; synthetic source, no Provider."""

import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.integrations.rardar import read_cache, trending_metadata, trending_store
from app.services import rardar_llm_control, rardar_trending as service
from app.services.llm import daily_provider_budget
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import MARKDOWN, TREE


@pytest.fixture
def source(tmp_path, monkeypatch):
    repository = "unseen-org/evidence-tool"
    calls = []
    state = {"failed": False, "markdown": MARKDOWN, "sha": "a" * 40}

    def response(request):
        calls.append(request.url.path)
        if state["failed"]:
            return httpx.Response(503)
        if request.url.path == f"/repos/{repository}":
            return httpx.Response(
                200,
                json={
                    "id": 771234,
                    "full_name": repository,
                    "default_branch": "main",
                    "description": "把公开仓库证据整理成可验证、可交付的项目地图。",
                    "language": "TypeScript",
                    "topics": [],
                    "license": {"spdx_id": "MIT"},
                    "pushed_at": "2026-10-24T00:00:00Z",
                    "stargazers_count": 400,
                },
            )
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=TREE)
        return httpx.Response(
            200,
            json={
                "path": "README_ZH.md",
                "sha": state["sha"],
                "encoding": "base64",
                "content": base64.b64encode(state["markdown"].encode()).decode(),
            },
            headers={"etag": '"sample"'},
        )

    @asynccontextmanager
    async def client(_token):
        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(response)
        ) as value:
            yield value

    monkeypatch.setattr(service, "github_material_client", client)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="a" * 64))
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(
            return_value=(
                SimpleNamespace(snapshot=lambda: {"remaining": 80}),
                {},
            )
        ),
    )
    value = board("github", [repository])
    value["entries"][0]["reportedDelta"] = 250
    trending_store.publish_sources(tmp_path, [value])
    read_cache.clear()
    return SimpleNamespace(target=tmp_path, repository=repository, calls=calls, state=state)


async def run(source, progress):
    path = source.target / "progress.json"
    result = await service.historical_work(source.target, progress, lambda: service.atomic(path, progress))
    read_cache.clear()
    return result


@pytest.mark.asyncio
async def test_automatic_unseen_project_persists_and_reads_in_all_live_consumers(source):
    progress = {}
    result = await run(source, progress)
    assert result["providerRequests"] == 0
    assert result["processed"] == 1
    today = service.today()["projects"][0]
    detail = service.detail(today["projectId"], today.get("generationId"))
    service.publish_history_review(source.target, now=datetime.now(UTC), trigger="manual_initialization")
    historical = service.history()["projects"][0]
    assert today["repository"] == source.repository
    assert today["profile"]["positioning"] == detail["profile"]["positioning"] == historical["profile"]["positioning"]
    assert service.load_saved_project_profile(source.target, source.repository) is not None
    assert "displayEvidence" not in today and "displayEvidence" not in historical
    assert detail["displayEvidence"]["githubRepositoryId"] == 771234
    assert (
        service.read_json(source.target / "progress.json")["materialWork"]["projects"][source.repository]["nextAction"]
        == "reuse_healthy"
    )
    count = len(source.calls)
    repeated = await run(source, progress)
    assert repeated["providerRequests"] == 0 and repeated["processed"] == 0
    assert len(source.calls) == count


@pytest.mark.asyncio
async def test_transient_source_failure_recovers_at_next_legal_daily_opportunity(source):
    source.state["failed"] = True
    first = await run(source, {})
    assert first["failed"] == 1 and first["providerRequests"] == 0
    original = trending_store.load_snapshot(source.target)["generationId"]
    assert service.today()["projects"][0]["profile"] is None
    source.state["failed"] = False
    # New daily progress, same durable source/cache/attempt stores. No deletion,
    # fake clock or reset of a model ledger is involved in this simulation.
    second = await run(source, {})
    assert second["processed"] == 1 and second["providerRequests"] == 0
    assert trending_store.load_snapshot(source.target)["generationId"] == original
    item = service.today()["projects"][0]
    assert item["profile"]["summary"] and item["profile"]["positioning"]
    assert item["materialAttempt"]["nextAction"] == "reuse_healthy"


@pytest.mark.asyncio
async def test_new_board_metrics_and_metadata_stars_reuse_the_same_material(source):
    await run(source, {})
    material = service.saved_materials(source.target)[source.repository]
    original = material["displayProfile"]
    record = trending_metadata.read(source.target, {"repository": source.repository})
    revision = trending_metadata.content_revision(source.target, {"repository": source.repository})
    trending_metadata.save(
        source.target,
        {"repository": source.repository},
        {
            "id": record["githubRepositoryId"],
            "full_name": record["repository"],
            "description": record["description"],
            "language": record["language"],
            "topics": record["topics"],
            "license": {"spdx_id": record["license"]},
            "default_branch": revision["content"]["defaultBranch"],
            "stargazers_count": 999,
        },
    )
    updated = board("github", [source.repository])
    updated["entries"][0].update(reportedDelta=300, totalStars=999)
    trending_store.publish_sources(source.target, [updated])
    read_cache.clear()
    calls = len(source.calls)
    result = await run(source, {})
    assert result["processed"] == result["providerRequests"] == 0
    assert len(source.calls) == calls
    current = service.today()["projects"][0]
    assert current["profile"]["summary"] == original["identitySummaryZh"]
    assert (
        service.saved_materials(source.target)[source.repository]["displayProfile"]["generatedAt"]
        == original["generatedAt"]
    )
