"""Refocused scheduler/admin entry wiring against isolated files and mock IO."""

import asyncio
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
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
from app.services.llm.provider_budget import ProviderBudgetError
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


@pytest.fixture
def waiting_history(isolated, monkeypatch):
    """Real daily/work-slice orchestration, with only IO/reservation simulated."""
    from app.services import rardar_llm_control

    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 3)
    monkeypatch.setattr(trending_boards, "fetch_boards", AsyncMock(return_value=[board("github", ["org/a"])]))
    ledger = SimpleNamespace(snapshot=lambda: {"remaining": 20}, execution_lock=isolated / "provider.lock", requests=0)
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", AsyncMock(return_value=(ledger, {})))
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    original = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            **kwargs,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"full_name": "org/a", "id": 1, "default_branch": "main"})
            ),
        ),
    )

    @contextmanager
    def reserve(*_args, **_kwargs):
        ledger.requests += 1
        yield

    monkeypatch.setattr(daily_provider_budget, "combined_budget_execution", reserve)
    monkeypatch.setattr(service, "project_material", lambda *_: {"profile": {"summary": "fixture"}})
    return ledger


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["interactive_request_waiting", "provider_request_busy", "pre_window_background_limit"]
)
async def test_same_day_zero_request_waits_do_not_exhaust_history_allowance(
    isolated, waiting_history, monkeypatch, reason
):
    waiting = True

    def policy(*_args, **_kwargs):
        if waiting:
            daily_provider_budget._yield_work(reason)

    monkeypatch.setattr(daily_provider_budget, "_check_work_policy", policy)

    async def collect(*_args, **_kwargs):
        async with daily_provider_budget.managed_budget_execution(
            None, (waiting_history, {}), scene="rardar_project_profile"
        ):
            return SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")

    collector = AsyncMock(side_effect=collect)
    monkeypatch.setattr(service, "collect_official_project_profile", collector)
    for _ in range(4):
        result = await daily.run_daily_operations()
        assert result["modules"]["historical_hot"]["waitReason"] == reason
        assert result["modules"]["historical_hot"]["failed"] == 0
        assert waiting_history.requests == 0
    waiting = False
    result = await daily.run_daily_operations()
    assert result["modules"]["historical_hot"]["processed"] == 1
    assert waiting_history.requests == 1
    assert collector.await_count == 5


@pytest.mark.asyncio
async def test_paid_work_yield_retains_admission_and_intermediate_cache(isolated, waiting_history, monkeypatch):
    monkeypatch.setattr(daily_provider_budget, "_check_work_policy", lambda *_args, **_kwargs: None)
    cache = isolated / "saved-stage.json"

    async def collect(*_args, **_kwargs):
        # A paid intermediate stage survives the first yield; resume must reuse it.
        if not cache.exists():
            async with daily_provider_budget.managed_budget_execution(
                None, (waiting_history, {}), scene="rardar_project_profile"
            ):
                store.atomic(cache, {"validatedStage": True})
        else:
            assert store.read_json(cache) == {"validatedStage": True}
            async with daily_provider_budget.managed_budget_execution(
                None, (waiting_history, {}), scene="rardar_project_profile"
            ):
                pass
        daily_provider_budget._yield_work("interactive_request_waiting")

    collector = AsyncMock(side_effect=collect)
    monkeypatch.setattr(service, "collect_official_project_profile", collector)
    for _ in range(3):
        await daily.run_daily_operations()
    assert waiting_history.requests == 3
    assert collector.await_count == 3  # normal paid continuation is not a failed retry
    state = next(daily.operation_root().glob("*-refocus-v1.json"))
    record = store.read_json(state)["progress"]["historical"]["materialWork"]["projects"]["org/a"]
    assert record["providerRequests"] == 3
    assert record["failures"] == 0
    assert record["status"] == "yielded"
    assert store.read_json(cache) == {"validatedStage": True}


@pytest.mark.asyncio
async def test_wait_release_preserves_previous_paid_attempt_then_resumes_cache(isolated, waiting_history, monkeypatch):
    monkeypatch.setattr(daily_provider_budget, "_check_work_policy", lambda *_args, **_kwargs: None)
    calls = 0

    async def collect(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            async with daily_provider_budget.managed_budget_execution(
                None, (waiting_history, {}), scene="rardar_project_profile"
            ):
                store.atomic(isolated / "saved-stage.json", {"validatedStage": True})
            daily_provider_budget._yield_work("interactive_request_waiting")
        assert store.read_json(isolated / "saved-stage.json") == {"validatedStage": True}
        if calls < 4:
            daily_provider_budget._yield_work("provider_request_busy")
        return SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="hit")

    monkeypatch.setattr(service, "collect_official_project_profile", collect)
    for _ in range(3):
        await daily.run_daily_operations()
        path = next(daily.operation_root().glob("*-refocus-v1.json"))
        records = store.read_json(path)["progress"]["historical"]["materialWork"]["projects"]
        assert list(records) == ["org/a"]
        assert records["org/a"]["providerRequests"] == 1
        assert records["org/a"]["failures"] == 0
    final = await daily.run_daily_operations()
    assert final["modules"]["historical_hot"]["refreshed"] == 1
    assert waiting_history.requests == 1
    final_record = store.read_json(path)["progress"]["historical"]["materialWork"]["projects"]["org/a"]
    assert final_record["providerRequests"] == 1
    assert final_record["status"] == "completed"


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
async def test_unconfigured_budget_is_pending_not_material_failure(isolated, monkeypatch):
    monkeypatch.setattr(trending_boards, "fetch_boards", AsyncMock(return_value=[board("github", ["org/a"])]))
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(side_effect=ProviderBudgetError("provider_daily_budget_unconfigured")),
    )
    result = await daily.run_daily_operations()
    assert result["modules"]["today"]["count"] == 1
    assert result["modules"]["historical_hot"]["status"] == "pending"
    assert result["modules"]["historical_hot"]["waitReason"] == "daily_budget_not_configured"


@pytest.mark.asyncio
async def test_old_rebound_reading_is_checked_without_repeated_daily_work(isolated, monkeypatch):
    from app.services import rardar_llm_control

    store.publish_sources(isolated, [board("github", ["org/a"])])
    now = datetime.now(UTC)
    profile = {"summary": "saved", "generatedAt": (now - timedelta(days=40)).isoformat(), "sourceGeneration": "old"}
    project = {"repository": "org/a", "profile": profile, "totalStars": 10}
    monkeypatch.setattr(
        service, "historical_snapshot", lambda *_args, **_kwargs: {"projects": [project], "generationId": "current"}
    )
    budget = AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 10}), {}))
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", budget)
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    original = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            **kwargs,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"full_name": "org/a", "id": 1, "default_branch": "main"})
            ),
        ),
    )
    collector = AsyncMock(
        return_value=SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebound")
    )
    monkeypatch.setattr(service, "collect_official_project_profile", collector)
    monkeypatch.setattr(service, "project_material", lambda *_: {"profile": {**profile, "sourceGeneration": "current"}})
    first = await service.historical_work(isolated, {}, lambda: None)
    assert first["processed"] == 0
    assert first["refreshed"] == 1
    assert first["remaining"] == 0

    class NextDay(datetime):
        @classmethod
        def now(cls, tz=None):
            return now + timedelta(days=1)

    monkeypatch.setattr(service, "datetime", NextDay)
    second = await service.historical_work(isolated, {}, lambda: None)
    assert second["remaining"] == 0
    assert second["processed"] == second["refreshed"] == 0
    collector.assert_awaited_once()
    budget.assert_awaited_once()
    assert profile["sourceGeneration"] == "old"
    assert profile["generatedAt"] == (now - timedelta(days=40)).isoformat()
    project["profile"] = {**profile, "summary": "changed reading"}
    await service.historical_work(isolated, {}, lambda: None)
    assert collector.await_count == 2  # a changed saved reading does not inherit the check


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

    store.import_historical_evidence(
        isolated,
        {
            "source": "github",
            "period": "historical-all-days",
            "sourceUrl": "https://trendshift.io/github-trending-repositories",
            "fetchedAt": datetime.now(UTC).isoformat(),
            "entries": [{"repository": repo, "reportedAppearanceCount": 1} for repo in ("org/a", "org/b")],
        },
    )
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
        assert saved[-1]["materialWork"]["projects"][repository]["status"] == "running"
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
    assert requested == ["org/a", "org/a"]  # admitted project may retry, not admit a new one
    await service.historical_work(isolated, progress, lambda: saved.append(deepcopy(progress)))
    assert requested == ["org/a", "org/a"]  # two genuine failures retain the retry boundary
    progress = {}  # next day's operation state; rotation remains on disk
    await service.historical_work(isolated, progress, lambda: saved.append(deepcopy(progress)))
    assert requested == ["org/a", "org/a", "org/b"]


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
    collector = AsyncMock(
        return_value=SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")
    )
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
