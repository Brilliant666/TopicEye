"""Local admin entry: isolated state, no network, database or model requests."""

import asyncio
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, rardar
from app.core.database import get_db
from app.integrations.rardar.sync import RardarSyncError
from app.schemas.rardar_today_operations import TodayOperationRequest
from app.services import rardar_today_operations as ops


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
    monkeypatch.setattr(ops, "latest_operation", lambda: None)
    monkeypatch.setattr(ops, "last_successful_sync_at", lambda: None)
    with TestClient(app) as client:
        yield client


def test_admin_and_origin_protection_and_readonly_get(api, monkeypatch):
    path = "/rardar/today/operations"
    payload = {"requestId": str(uuid4())}
    assert api.post(path, json=payload).status_code == 401
    assert api.get(path).status_code == 401
    monkeypatch.setattr(auth, "get_user_for_token", AsyncMock(return_value=SimpleNamespace(id=2, role="user")))
    assert api.post(path, json=payload, headers={"Authorization": "Bearer test"}).status_code == 403
    monkeypatch.setattr(auth, "get_user_for_token", AsyncMock(return_value=SimpleNamespace(id=1, role="admin")))
    api.cookies.set(auth.settings.AUTH_COOKIE_NAME, "test")
    assert api.post(path, json=payload).status_code == 403
    assert api.post(path, json=payload, headers={"Origin": "https://attacker.invalid"}).status_code == 403
    assert api.get(path).status_code == 200
    ops.start_operation.assert_not_awaited()
    assert api.post(path, json=payload, headers={"Origin": "http://127.0.0.1:3000"}).status_code == 202


@pytest.mark.parametrize("field", ["host", "remoteRoot", "target", "command", "generateProfiles", "budgetPath"])
def test_client_cannot_supply_execution_configuration(api, field):
    assert (
        api.post(
            "/rardar/today/operations",
            json={"requestId": str(uuid4()), field: "forbidden"},
            headers={"Authorization": "Bearer test"},
        ).status_code
        == 422
    )
    ops.start_operation.assert_not_awaited()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(ops, "operation_root", lambda: tmp_path)
    monkeypatch.setattr(ops.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "data"))
    current = SimpleNamespace(generationId="real-generation", window=None, syncedAt=datetime(2026, 9, 9, tzinfo=UTC))
    monkeypatch.setattr(
        ops, "ServingProjectionLoader", lambda _: SimpleNamespace(load_today_with_etag=lambda: (current, "etag"))
    )
    return tmp_path


@dataclass
class Result:
    changed: bool = False
    outcome: str = "unchanged"
    upstream_window: dict | None = None


@pytest.mark.asyncio
async def test_duplicate_clicks_share_thread_lock_result_and_no_budget(isolated, monkeypatch):
    orphan = str(uuid4())
    (isolated / orphan).mkdir()
    ops.atomic(isolated / orphan / "operation.json", {"id": orphan, "status": "running"})
    release = threading.Event()
    calls = []

    def sync():
        calls.append(1)
        assert release.wait(10)
        return Result()

    monkeypatch.setattr(ops, "_sync", sync)
    request = TodayOperationRequest(requestId=uuid4())
    first = await ops.start_operation(request, user_id=1)
    try:
        assert ops.get_operation(first["id"])["status"] == "running"
        assert ops.get_operation(orphan)["status"] == "interrupted"
        assert (await ops.start_operation(request, user_id=1))["id"] == first["id"]
        assert (await ops.start_operation(TodayOperationRequest(requestId=uuid4()), user_id=1))["id"] == first["id"]
    finally:
        release.set()
        await asyncio.gather(*list(ops._tasks))
    final = ops.get_operation(first["id"])
    assert final["status"] == "unchanged"
    assert final["providerCalls"] == 0
    assert final["result"]["syncedAt"].startswith("2026-09-09")
    assert ops.last_successful_sync_at() is None  # A check is not a new synchronization.
    assert (await ops.start_operation(request, user_id=1))["id"] == first["id"]
    assert calls == [1]
    assert not list(isolated.rglob("*budget*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["rardar_sync_remote_unavailable", "rardar_sync_remote_rejected"])
async def test_failure_is_safe_and_previous_sync_record_preserved(isolated, monkeypatch, code):
    ops.atomic(isolated / "last-successful-sync.json", {"completedAt": "old"})

    def fail():
        raise RardarSyncError(code, "sensitive SSH diagnostic must not escape")

    monkeypatch.setattr(ops, "_sync", fail)
    first = await ops.start_operation(TodayOperationRequest(requestId=uuid4()), user_id=1)
    await asyncio.gather(*list(ops._tasks))
    result = ops.get_operation(first["id"])
    assert result["status"] == "failed"
    assert result["errorCode"] == code
    assert "sensitive" not in str(result)
    assert ops.last_successful_sync_at() == "old"


def test_orphaned_running_operation_is_interrupted_without_state_mutation(isolated):
    identifier = str(uuid4())
    folder = isolated / identifier
    folder.mkdir()
    path = folder / "operation.json"
    ops.atomic(path, {"id": identifier, "status": "running"})
    before = path.read_bytes()
    assert ops.get_operation(identifier)["status"] == "interrupted"
    assert path.read_bytes() == before


def test_shared_cli_sync_is_explicitly_model_disabled(monkeypatch, isolated):
    from scripts import rebuild_rardar_serving

    seen = {}

    def provider(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(rebuild_rardar_serving, "real_profile_provider", provider)
    monkeypatch.setattr(ops, "sync_rardar_intelligence", lambda **kwargs: seen.update(kwargs))
    ops._sync()
    assert seen["allow_model_generation"] is False
    assert seen["check_published"] is True
    assert seen["host"] == ops.settings.RARDAR_TODAY_SOURCE_HOST
