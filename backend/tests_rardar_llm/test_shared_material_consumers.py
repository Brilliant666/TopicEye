"""Actual immutable material/board/Find stores across proven repository aliases.

Only public synthetic source bodies and a disposable SQLite user are used.
The production route functions and strict saved-envelope reader are unchanged.
"""

import base64
from copy import deepcopy
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1 import rardar as api
from app.core.config import settings
from app.integrations.rardar import historical_daily, project_identity, read_cache, trending_metadata, trending_store
from app.integrations.rardar.serving_profiles import collect_official_project_profile
from app.integrations.rardar.trending_periods import ZONE
from app.schemas.rardar_product import FindEvidenceSource
from app.services import rardar_trending as service
from tests_rardar_llm.test_find_runs import (
    request as find_request,
    result as find_result,
    service as find_service,
    sessions as _sessions,
)
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import MARKDOWN, _handler, _project

find_sessions = _sessions


@pytest.fixture(autouse=True)
def fresh_reads():
    read_cache.clear()
    yield
    read_cache.clear()


async def _seed(target, repository=None, identifier=None, *, markdown=None):
    project = _project()
    if repository is not None:
        project = project.model_copy(
            update={
                "repository": repository,
                "githubRepositoryId": identifier,
                "htmlUrl": f"https://github.com/{repository}",
            }
        )
    handle = _handler([], sha="b" * 40 if markdown is not None else "a" * 40)

    def source(request):
        result = handle(request)
        payload = result.json()
        if markdown is not None and isinstance(payload, dict) and "content" in payload:
            payload["content"] = base64.b64encode(markdown.encode()).decode()
            return httpx.Response(200, json=payload)
        return result

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(source)) as client:
        collected = await collect_official_project_profile(
            project,
            "synthetic-source-before-rename",
            target / "profile-cache",
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )
    assert collected.profile is not None
    return project


def _metadata(target, original, current=None):
    return trending_metadata.save(
        target,
        {"repository": original.repository, "githubRepositoryId": original.githubRepositoryId},
        {
            "full_name": current or original.repository,
            "id": original.githubRepositoryId,
            "default_branch": "main",
            "description": "A public evidence-backed architecture documentation tool.",
            "stargazers_count": 100,
        },
    )


def _publish(target, projects):
    source = board(
        "github", [project.repository if hasattr(project, "repository") else project for project in projects]
    )
    for row, project in zip(source["entries"], projects, strict=True):
        row.update(reportedDelta=250, reportedDeltaPeriod="daily")
        if hasattr(project, "githubRepositoryId"):
            row["githubRepositoryId"] = project.githubRepositoryId
    return trending_store.publish_sources(target, [source])


def _app(target, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(target))
    monkeypatch.setattr(api, "is_rardar_product", lambda: True)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    original = httpx.AsyncClient.send

    async def guarded(client, request, *args, **kwargs):
        if not isinstance(client._transport, httpx.ASGITransport):
            raise AssertionError("consumer GET must not fetch a source or call a Provider")
        return await original(client, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", guarded)
    return app


@pytest.mark.asyncio
async def test_scoped_material_alias_reads_original_envelope_without_rewriting_it(tmp_path):
    original = await _seed(tmp_path)
    _metadata(tmp_path, original)
    before = service.saved_materials(tmp_path, repositories={original.repository})[original.repository]
    envelope = next((tmp_path / "profile-cache" / "profile-store" / "v2").glob("*/*.json"))
    immutable = envelope.read_bytes()
    renamed = "renamed-team/evidence-tool"
    assert service.saved_materials(tmp_path, repositories={renamed}) == {}
    _metadata(tmp_path, original, renamed)
    after = service.saved_materials(tmp_path, repositories={renamed})
    assert set(after) == {original.repository, renamed}
    assert after[renamed] == before
    assert after[renamed]["displayProfile"]["repository"] == original.repository
    assert after[renamed]["displayEvidence"] == before["displayEvidence"]
    assert envelope.read_bytes() == immutable


@pytest.mark.asyncio
async def test_actual_today_and_detail_routes_share_material_through_old_and_new_urls(tmp_path, monkeypatch):
    original = await _seed(tmp_path)
    _metadata(tmp_path, original)
    renamed = "renamed-team/evidence-tool"
    _metadata(tmp_path, original, renamed)
    new_project = original.model_copy(update={"repository": renamed})
    published = _publish(tmp_path, [new_project, "fresh-project/no-ai-yet"])
    app = _app(tmp_path, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/v1/rardar/trending-today")
        assert response.status_code == 200
        cards = {row["repository"]: row for row in response.json()["projects"]}
        assert set(cards) == {renamed, "fresh-project/no-ai-yet"}
        card = cards[renamed]
        assert card["displayCard"]["positioningZh"]
        assert "displayEvidence" not in card and "displayProfile" not in card
        old_id = project_identity.project_id_for_repository(original.repository)
        new_id = project_identity.project_id_for_repository(renamed)
        details = []
        for identifier in (old_id, new_id):
            detail = await client.get(
                f"/api/v1/rardar/trending-projects/{identifier}", params={"generation": published["generationId"]}
            )
            assert detail.status_code == 200
            value = detail.json()
            assert value["repository"] == renamed
            assert value["displayProfile"]["repository"] == original.repository
            assert value["displayProfile"]["positioningZh"] == card["displayCard"]["positioningZh"]
            details.append(value)
        assert details[0] == details[1]
        missing = await client.get(
            f"/api/v1/rardar/trending-projects/{cards['fresh-project/no-ai-yet']['projectId']}",
            params={"generation": published["generationId"]},
        )
        assert missing.status_code == 200
        assert missing.json()["displayProfile"] is None
        assert missing.json()["repositoryUrl"] == "https://github.com/fresh-project/no-ai-yet"


@pytest.mark.asyncio
async def test_daily_eight_eligible_projects_do_not_count_a_proven_alias_twice(tmp_path, monkeypatch):
    original = await _seed(tmp_path)
    _metadata(tmp_path, original)
    renamed = "renamed-team/evidence-tool"
    _metadata(tmp_path, original, renamed)
    alternatives = [
        await _seed(tmp_path, f"different/project-{index}", original.githubRepositoryId + index + 1)
        for index in range(7)
    ]
    all_rows = [original, original.model_copy(update={"repository": renamed}), *alternatives]
    _publish(tmp_path, all_rows)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    batch = service.publish_history_review(tmp_path, now=datetime(2026, 10, 26, 9, tzinfo=ZONE), trigger="main")
    assert batch["eligibleCount"] == 8
    assert len(batch["projectIds"]) == 8
    assert len({row["githubRepositoryId"] for row in batch["identities"]}) == 8
    assert (
        service.publish_history_review(tmp_path, now=datetime(2026, 10, 26, 11, tzinfo=ZONE), trigger="compensation")
        == batch
    )


@pytest.mark.asyncio
async def test_saved_history_batch_stays_original_after_rename_but_both_detail_urls_work(tmp_path, monkeypatch):
    original = await _seed(tmp_path)
    _metadata(tmp_path, original)
    _publish(tmp_path, [original])
    batch = service.publish_history_review(tmp_path, now=datetime(2026, 10, 26, 9, tzinfo=ZONE), trigger="main")
    stored = (tmp_path / "historical-daily" / "2026-10-26.json").read_bytes()
    renamed = "renamed-team/evidence-tool"
    _metadata(tmp_path, original, renamed)
    _publish(tmp_path, [original.model_copy(update={"repository": renamed})])
    app = _app(tmp_path, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        view = await client.get("/api/v1/rardar/historical-hot")
        assert view.status_code == 200
        selected = view.json()
        assert selected["dailyReview"]["projectIds"] == batch["projectIds"]
        assert selected["publishedAt"] == batch["publishedAt"]
        assert selected["projects"][0]["displayCard"]["positioningZh"]
        for identifier in (
            project_identity.project_id_for_repository(original.repository),
            project_identity.project_id_for_repository(renamed),
        ):
            detail = await client.get(f"/api/v1/rardar/historical-projects/{identifier}")
            assert detail.status_code == 200
            assert detail.json()["displayProfile"]["repository"] == original.repository
    assert (tmp_path / "historical-daily" / "2026-10-26.json").read_bytes() == stored
    assert historical_daily.read_for_date(tmp_path, "2026-10-26") == batch


@pytest.mark.asyncio
async def test_current_shared_material_changes_cannot_rewrite_saved_find_result(tmp_path, monkeypatch, find_sessions):
    original = await _seed(tmp_path)
    _metadata(tmp_path, original)
    _publish(tmp_path, [original])
    response = find_result()
    response.evidenceSources = [
        FindEvidenceSource(
            repository=original.repository,
            ref="readme:source-before-rename",
            url=f"https://github.com/{original.repository}/blob/frozen/README.md",
            text="Frozen original source for the historical Find comparison.",
            kind="readme",
        )
    ]
    runner = AsyncMock(return_value=response)
    durable = find_service(find_sessions, runner)
    created = await durable.create(1, find_request(), "shared-consumer-frozen-find-01", request_limit=0)
    saved = await durable.execute(1, created["runId"])
    immutable = deepcopy(saved)
    renamed = "renamed-team/evidence-tool"
    _metadata(tmp_path, original, renamed)
    # Persist a later validated current-name material as well as updating the
    # name index. The historical Find must still expose its frozen input.
    await _seed(
        tmp_path,
        renamed,
        original.githubRepositoryId,
        markdown=MARKDOWN + "\n## 使用限制\n输出文档需要使用者先核对证据；静态资料核对不等于已运行验证。\n",
    )
    _publish(tmp_path, [original.model_copy(update={"repository": renamed})])
    app = _app(tmp_path, monkeypatch)
    app.dependency_overrides[api._find_user_id] = lambda: 1
    fresh = find_service(find_sessions, AsyncMock(side_effect=AssertionError("readback must not regenerate Find")))
    monkeypatch.setattr(api, "find_runs", fresh)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.get("/api/v1/rardar/trending-today")).status_code == 200
        detail = await client.get(
            f"/api/v1/rardar/trending-projects/{project_identity.project_id_for_repository(renamed)}",
            params={"generation": trending_store.load_snapshot(tmp_path)["generationId"]},
        )
        assert detail.status_code == 200
        assert detail.json()["displayProfile"]["repository"] == renamed
        readback = await client.get(f"/api/v1/rardar/find-runs/{created['runId']}")
        assert readback.status_code == 200
        assert readback.json()["result"] == immutable["result"]
    assert await fresh.get(1, created["runId"]) == immutable
    assert runner.await_count == 1
    assert saved["requestsUsed"] == 0
