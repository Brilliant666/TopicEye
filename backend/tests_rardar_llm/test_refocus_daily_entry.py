"""Refocused scheduler/admin entry wiring against isolated files and mock IO."""

import asyncio
import threading
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import rardar
from app.core.config import settings
from app.integrations.rardar import trending_boards, trending_store as store
from app.schemas.rardar_today_operations import TodayOperationRequest
from app.services import rardar_daily_operations as daily, rardar_today_operations as ops, rardar_trending as service
from app.services.llm import daily_provider_budget
from tests_rardar_llm.test_rardar_trending_store import board


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", True)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "daily")
    monkeypatch.setattr(ops, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(daily, "_execution_paused", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "saved_materials", lambda _target: {})
    return tmp_path / "data"


@pytest.mark.asyncio
async def test_scheduler_fetches_both_boards_despite_exhausted_models(isolated, monkeypatch):
    fetch = AsyncMock(return_value=[board("github", ["org/a"]), board("trendshift", ["org/b"])])
    monkeypatch.setattr(trending_boards, "fetch_boards", fetch)
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 0}), {})),
    )
    retired = AsyncMock(side_effect=AssertionError("retired work must not run"))
    for name in ("_news_refresh", "_news_enhance", "_discover", "_inventory"):
        monkeypatch.setattr(daily, name, retired)
    result = await daily.run_daily_operations()
    assert result["modules"]["today"]["count"] == 2
    assert result["modules"]["today"]["providerCalls"] == 0
    assert result["modules"]["historical_hot"]["waitReason"] == "daily_budget_exhausted"
    assert result["modules"]["discover"]["status"] == "paused"
    assert result["modules"]["news_refresh"]["status"] == "paused"
    assert result["modules"]["find"]["interactivePriority"]
    fetch.assert_awaited_once()
    retired.assert_not_called()
    assert len(store.load_snapshot(isolated)["projects"]) == 2


@pytest.mark.asyncio
async def test_scheduler_source_failure_preserves_previous_board(isolated, monkeypatch):
    store.publish_sources(isolated, [board("github", ["org/a"]), board("trendshift", ["org/b"])])
    monkeypatch.setattr(trending_boards, "fetch_boards", AsyncMock(side_effect=ValueError("invalid source")))
    monkeypatch.setattr(service, "historical_work", AsyncMock(return_value={"status": "completed", "reused": 0}))
    before = (isolated / "trending-boards/current.json").read_bytes()
    result = await daily.run_daily_operations()
    assert result["modules"]["today"]["status"] == "failed"
    assert result["modules"]["today"]["oldResultPreserved"]
    assert (isolated / "trending-boards/current.json").read_bytes() == before


@pytest.mark.asyncio
async def test_historical_admission_is_saved_before_network_and_rotates_next_day(isolated, monkeypatch):
    from app.services import rardar_llm_control

    store.publish_sources(isolated, [board("github", ["org/a", "org/b"])])
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 1)
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 10}), {})),
    )
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    saved, requested = [], []
    progress = {}

    def response(request):
        repository = request.url.path.removeprefix("/repos/")
        assert saved[-1]["attempts"][repository] == 1
        assert repository in store.read_json(isolated / "trending-boards/material-work.json")
        requested.append(repository)
        return httpx.Response(503)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(response))
    )
    first = await service.historical_work(isolated, progress, lambda: saved.append(deepcopy(progress)))
    assert first["failed"] == 1
    assert requested == ["org/a"]
    await service.historical_work(isolated, progress, lambda: saved.append(deepcopy(progress)))
    assert requested == ["org/a"]  # same-day resume cannot reset allowance
    progress = {}  # next day's operation state; rotation remains on disk
    await service.historical_work(isolated, progress, lambda: saved.append(deepcopy(progress)))
    assert requested == ["org/a", "org/b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_metadata", [None, {}, [], {"full_name": "org/a", "id": 1}])
async def test_historical_one_failure_does_not_block_next_project(isolated, monkeypatch, failed_metadata):
    from app.services import rardar_llm_control

    store.publish_sources(isolated, [board("github", ["org/a", "org/b"])])
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 3)
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 10}), {})),
    )
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    original = httpx.AsyncClient

    def response(request):
        if request.url.path.endswith("/a"):
            return httpx.Response(503) if failed_metadata is None else httpx.Response(200, json=failed_metadata)
        return httpx.Response(200, json={"full_name": "org/b", "id": 2, "default_branch": "main"})

    monkeypatch.setattr(
        service.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(response))
    )
    collector = AsyncMock(return_value=SimpleNamespace(profile=object(), evidence=object()))
    monkeypatch.setattr(service, "collect_official_project_profile", collector)
    monkeypatch.setattr(service, "project_material", lambda *_: {"profile": {"summary": "fixture"}})
    result = await service.historical_work(isolated, {}, lambda: None)
    assert result["failed"] == 1
    assert result["processed"] == 1
    assert collector.await_args.args[0].repository == "org/b"


def test_historical_archive_is_not_forged_daily_appearances(isolated):
    record = {
        "source": "github",
        "period": "historical-all-days",
        "sourceUrl": "https://trendshift.io/github-trending-repositories",
        "fetchedAt": datetime.now(UTC).isoformat(),
        "entries": [{"repository": f"archive/project-{i}", "reportedAppearanceCount": i + 1} for i in range(25)],
    }
    assert store.import_historical_evidence(isolated, record)["changed"]
    assert not store.import_historical_evidence(isolated, record)["changed"]
    result = store.historical_snapshot(isolated)
    assert len(result["projects"]) == 25
    for row in result["projects"]:
        assert row["historyAppearances"] == 0
        assert row["appearances"] == []
        assert row["historicalEvidence"][0]["sourceDate"] is None
    assert store.load_snapshot(isolated)["state"] == "not_synced"


def test_new_get_routes_only_read_saved_data(isolated, monkeypatch):
    installed = store.publish_sources(
        isolated, [board("github", ["outside/new"]), board("trendshift", ["outside/new"])]
    )
    identifier = store.load_snapshot(isolated)["projects"][0]["projectId"]
    fetch = AsyncMock(side_effect=AssertionError("GET must not fetch"))
    monkeypatch.setattr(trending_boards, "fetch_boards", fetch)
    app = FastAPI()
    app.include_router(rardar.router)
    with TestClient(app) as client:
        for path in (
            "/trending-today",
            "/historical-hot",
            f"/trending-projects/{identifier}?generation={installed['generationId']}",
            f"/historical-projects/{identifier}",
        ):
            assert client.get("/rardar" + path).status_code == 200, path
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_today_executor_uses_dualboard_path_and_duplicate_operation(isolated, monkeypatch):
    release = threading.Event()
    calls = []

    async def refresh():
        calls.append(1)
        assert await asyncio.to_thread(release.wait, 10)
        return {"status": "updated", "changed": True, "providerCalls": 0, "generationId": "fixture"}

    monkeypatch.setattr(service, "refresh_boards", refresh)
    request = TodayOperationRequest(requestId=uuid4())
    first = await ops.start_operation(request, user_id=1)
    try:
        duplicate = await ops.start_operation(TodayOperationRequest(requestId=uuid4()), user_id=1)
        assert duplicate["id"] == first["id"]
    finally:
        release.set()
        await asyncio.gather(*list(ops._tasks))
    final = ops.get_operation(first["id"])
    assert final["status"] == "updated"
    assert final["providerCalls"] == 0
    assert len(calls) == 1
