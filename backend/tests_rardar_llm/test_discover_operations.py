"""Admin entry uses isolated state and mocked Selection; no Provider requests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, rardar
from app.core.database import get_db
from app.schemas.rardar_discover_operations import DiscoverOperationRequest, DiscoverPrepareRequest
from app.services import rardar_discover_operations as ops


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(rardar.router)

    async def fake_db():
        yield object()

    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(rardar, "is_rardar_product", lambda: True)
    monkeypatch.setattr(rardar.settings, "CORS_ORIGINS", "http://127.0.0.1:3000")
    monkeypatch.setattr(auth, "get_user_for_token", AsyncMock(return_value=SimpleNamespace(id=1, role="admin")))
    monkeypatch.setattr(ops, "start_operation", AsyncMock(return_value={"id": "test", "status": "running"}))
    monkeypatch.setattr(ops, "prepare_operation", AsyncMock(return_value={"id": "plan"}))
    monkeypatch.setattr(ops, "latest_operation", lambda: None)
    monkeypatch.setattr(ops, "prepared_plan", lambda: None)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("suffix", ["", "/prepare"])
def test_admin_origin_and_no_side_effect_get(api, monkeypatch, suffix):
    path = "/rardar/discover/operations" + suffix
    payload = {"requestId": str(uuid4())}
    if not suffix:
        payload["planId"] = str(uuid4())
    assert api.post(path, json=payload).status_code == 401
    monkeypatch.setattr(auth, "get_user_for_token", AsyncMock(return_value=SimpleNamespace(id=2, role="user")))
    assert api.post(path, json=payload, headers={"Authorization": "Bearer test"}).status_code == 403
    monkeypatch.setattr(auth, "get_user_for_token", AsyncMock(return_value=SimpleNamespace(id=1, role="admin")))
    api.cookies.set(auth.settings.AUTH_COOKIE_NAME, "test")
    assert api.post(path, json=payload).status_code == 403
    assert api.get("/rardar/discover/operations").status_code == 200
    ops.start_operation.assert_not_awaited()
    ops.prepare_operation.assert_not_awaited()
    assert api.post(path, json=payload, headers={"Origin": "http://127.0.0.1:3000"}).status_code in {200, 202}


@pytest.mark.parametrize("field", ["candidateIds", "limit", "command", "budgetPath", "model", "source"])
def test_no_client_execution_configuration(api, field):
    payload = {"requestId": str(uuid4()), "planId": str(uuid4()), field: "forbidden"}
    assert (
        api.post("/rardar/discover/operations", json=payload, headers={"Authorization": "Bearer test"}).status_code
        == 422
    )
    ops.start_operation.assert_not_awaited()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    root = tmp_path / "operations"
    root.mkdir()
    monkeypatch.setattr(ops, "operation_root", lambda: root)
    monkeypatch.setattr(ops.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(data))
    source = SimpleNamespace(
        source_observation_set_id="source",
        manifest_sha256="a" * 64,
        today_generation_id="today",
        latest_capture_at="2026-09-09T00:00:00Z",
    )
    monkeypatch.setattr(ops.SelectionSourceAdapter, "from_config", lambda _: SimpleNamespace(load=lambda: source))
    monkeypatch.setattr(
        ops,
        "ServingProjectionLoader",
        lambda _: SimpleNamespace(load_today_with_etag=lambda: (SimpleNamespace(generationId="today"), "etag")),
    )
    monkeypatch.setattr(ops, "build_selection_source_from_today_mirror", lambda *a, **kw: object())
    monkeypatch.setattr(ops, "install_selection_source", lambda *a: None)
    monkeypatch.setattr(ops, "resolve_rardar_route_identity", AsyncMock(return_value="b" * 64))
    candidates = [SimpleNamespace(githubRepositoryId=i, repository=f"owner/repo{i}") for i in range(1, 9)]
    monkeypatch.setattr(ops, "build_candidate_universe", lambda _: (candidates, None))
    monkeypatch.setattr(ops, "recall_candidates", lambda *a, **kw: candidates)
    artifact = SimpleNamespace(
        sourceObservationSetId="previous",
        assessments=[
            SimpleNamespace(
                candidate=item, gate=object(), failureCode=None, valueFailureCode=None, copyFailureCode=None
            )
            for item in candidates[:6]
        ],
    )
    monkeypatch.setattr(
        ops, "SelectionServingLoader", lambda _: SimpleNamespace(validate_generation=lambda _=None: artifact)
    )
    return root


@pytest.mark.asyncio
async def test_prepare_freezes_and_does_not_initialize_budget(isolated):
    request = DiscoverPrepareRequest(requestId=uuid4())
    plan = await ops.prepare_operation(request, user_id=1)
    assert await ops.prepare_operation(request, user_id=1) == plan
    assert plan["candidateCount"] == 6
    assert plan["requestLimit"] == 40
    assert "routeIdentity" not in plan
    assert not list(isolated.rglob("provider-budget.json"))
    second = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=1)
    assert second["id"] == plan["id"]
    assert second["recallBatchId"] == plan["recallBatchId"]
    assert second["candidates"] == plan["candidates"]


@pytest.mark.asyncio
async def test_two_admin_tabs_share_plan_and_single_execution(isolated, monkeypatch):
    first = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=1)
    second = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=2)
    assert first["id"] == second["id"]
    run = AsyncMock(
        return_value={"publishedCount": 2, "changed": True, "selectionGenerationId": "selection", "cacheHits": 3}
    )
    monkeypatch.setattr(ops, "_run", run)
    one = await ops.start_operation(DiscoverOperationRequest(requestId=uuid4(), planId=first["id"]), user_id=1)
    await asyncio.gather(*list(ops._tasks))
    two = await ops.start_operation(DiscoverOperationRequest(requestId=uuid4(), planId=second["id"]), user_id=2)
    assert one["id"] == two["id"]
    run.assert_awaited_once()
    assert len(list(isolated.rglob("provider-budget.json"))) == 1


@pytest.mark.asyncio
async def test_superseded_unexecuted_plan_cannot_allocate_budget(isolated, monkeypatch):
    first = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=1)
    monkeypatch.setattr(ops, "resolve_rardar_route_identity", AsyncMock(return_value="c" * 64))
    second = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=2)
    assert second["id"] != first["id"]
    assert second["recallBatchId"] == first["recallBatchId"]
    with pytest.raises(ValueError, match="superseded"):
        await ops.start_operation(DiscoverOperationRequest(requestId=uuid4(), planId=first["id"]), user_id=1)
    assert not list(isolated.rglob("provider-budget.json"))


@pytest.mark.asyncio
async def test_duplicate_click_result_persists_and_next_batch_rotates(isolated, monkeypatch):
    plan = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=1)
    release = asyncio.Event()

    async def run(*args):
        await release.wait()
        return {"publishedCount": 2, "changed": True, "selectionGenerationId": "selection", "cacheHits": 3}

    monkeypatch.setattr(ops, "_run", run)
    request = DiscoverOperationRequest(requestId=uuid4(), planId=plan["id"])
    first = await ops.start_operation(request, user_id=1)
    assert ops.get_operation(first["id"])["status"] == "running"
    assert (await ops.start_operation(request, user_id=1))["id"] == first["id"]
    duplicate = DiscoverOperationRequest(requestId=uuid4(), planId=plan["id"])
    assert (await ops.start_operation(duplicate, user_id=1))["id"] == first["id"]
    release.set()
    await asyncio.gather(*list(ops._tasks))
    final = ops.get_operation(first["id"])
    assert final["status"] == "completed"
    assert final["result"]["publishedCount"] == 2
    assert final["providerCalls"] == 0
    assert ops.prepared_plan() is None
    monkeypatch.setattr(ops.settings, "RARDAR_DISCOVER_REQUEST_LIMIT", 50)
    assert ops._ledger(first["id"]).snapshot()["limit"] == 40
    assert (await ops.start_operation(duplicate, user_id=1))["id"] == first["id"]
    assert len(list(isolated.rglob("provider-budget.json"))) == 1
    next_plan = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=1)
    assert {7, 8}.issubset({item["githubRepositoryId"] for item in next_plan["candidates"]})
    assert next_plan["recallBatchId"] != plan["recallBatchId"]


@pytest.mark.asyncio
async def test_drift_rejects_before_budget_and_failure_is_safe(isolated, monkeypatch):
    plan = await ops.prepare_operation(DiscoverPrepareRequest(requestId=uuid4()), user_id=1)
    monkeypatch.setattr(ops, "resolve_rardar_route_identity", AsyncMock(return_value="c" * 64))
    with pytest.raises(ValueError):
        await ops.start_operation(DiscoverOperationRequest(requestId=uuid4(), planId=plan["id"]), user_id=1)
    assert not list(isolated.rglob("provider-budget.json"))
    monkeypatch.setattr(ops, "resolve_rardar_route_identity", AsyncMock(return_value="b" * 64))
    monkeypatch.setattr(ops, "_run", AsyncMock(side_effect=RuntimeError("sensitive response")))
    operation = await ops.start_operation(DiscoverOperationRequest(requestId=uuid4(), planId=plan["id"]), user_id=1)
    await asyncio.gather(*list(ops._tasks))
    final = ops.get_operation(operation["id"])
    assert final["status"] == "failed"
    assert "sensitive" not in str(final)
    assert final["providerCalls"] == 0


def test_interrupted_read_does_not_resume(isolated):
    identifier = str(uuid4())
    (isolated / identifier).mkdir()
    ops.atomic(isolated / identifier / "operation.json", {"id": identifier, "status": "running"})
    assert ops.get_operation(identifier)["status"] == "interrupted"
    assert not list(isolated.rglob("provider-budget.json"))
