"""Isolated operator API and execution tests: no database or provider access."""

import asyncio
import json
from contextlib import asynccontextmanager
from contextvars import Context
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, rardar
from app.core.database import get_db
from app.schemas.rardar_news_operations import NewsOperationRequest
from app.services import rardar_news_operation_lock as locks, rardar_news_operations as ops
from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    execution_budget,
    news_execution_budget,
)


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
    with TestClient(app) as client:
        yield client


def payload(action="refresh"):
    return {"action": action, "requestId": str(uuid4())}


def test_anonymous_and_non_admin_cannot_start(api, monkeypatch):
    assert api.post("/rardar/hotspot-news/operations", json=payload()).status_code == 401
    monkeypatch.setattr(auth, "get_user_for_token", AsyncMock(return_value=SimpleNamespace(id=2, role="user")))
    assert (
        api.post(
            "/rardar/hotspot-news/operations", json=payload(), headers={"Authorization": "Bearer test"}
        ).status_code
        == 403
    )
    ops.start_operation.assert_not_awaited()


def test_cookie_requires_trusted_origin(api):
    api.cookies.set(auth.settings.AUTH_COOKIE_NAME, "test")
    for headers in (
        {},
        {"Origin": "https://attacker.invalid"},
        {"Origin": rardar.settings.cors_origins[0], "Sec-Fetch-Site": "cross-site"},
    ):
        assert api.post("/rardar/hotspot-news/operations", json=payload(), headers=headers).status_code == 403
    assert (
        api.post(
            "/rardar/hotspot-news/operations", json=payload(), headers={"Origin": rardar.settings.cors_origins[0]}
        ).status_code
        == 202
    )


@pytest.mark.parametrize("field", ["budgetPath", "requestLimit", "model", "url", "command", "runId"])
def test_extra_control_parameters_rejected(api, field):
    assert (
        api.post(
            "/rardar/hotspot-news/operations",
            json={**payload(), field: "forbidden"},
            headers={"Authorization": "Bearer test"},
        ).status_code
        == 422
    )
    ops.start_operation.assert_not_awaited()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(ops, "operation_root", lambda: tmp_path)
    monkeypatch.setattr(locks, "operation_root", lambda: tmp_path)

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(ops, "async_session", session)
    return tmp_path


class Result:
    status = "completed"

    def model_dump(self, **_kwargs):
        return {"status": self.status}


@pytest.mark.asyncio
async def test_refresh_deduplicates_clicks_and_never_initializes_budget(isolated, monkeypatch):
    release = asyncio.Event()

    async def refresh(_db):
        await release.wait()
        return Result()

    refresh_mock = AsyncMock(side_effect=refresh)
    monkeypatch.setattr(ops, "refresh_hotspot_news", refresh_mock)
    monkeypatch.setattr(ops, "enhance_hotspot_news", AsyncMock(side_effect=AssertionError("model path")))
    request = NewsOperationRequest(**payload())
    first = await ops.start_operation(request, user_id=1)
    try:
        same = await ops.start_operation(request, user_id=1)
        another = await ops.start_operation(NewsOperationRequest(**payload("enhance")), user_id=1)
        assert first["id"] == same["id"] == another["id"]
        assert first["requestLimit"] == 0
        assert list(isolated.rglob("provider-budget.json")) == []
    finally:
        release.set()
        await asyncio.gather(*list(ops._tasks))
    refresh_mock.assert_awaited_once()
    assert ops.get_operation(first["id"])["status"] == "completed"
    assert (await ops.start_operation(request, user_id=1))["id"] == first["id"]
    refresh_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_enhancement_freezes_page_and_keeps_same_budget_on_retry(isolated, monkeypatch):
    page = SimpleNamespace(items=[SimpleNamespace(id=11), SimpleNamespace(id=22)])
    load = AsyncMock(return_value=(page, "etag"))
    monkeypatch.setattr(ops, "load_hotspot_news", load)
    captured = []

    async def enhance(_db, *, frozen_page):
        assert frozen_page is page
        captured.append(execution_budget("rardar_news_quickread")[0].path)
        return Result()

    monkeypatch.setattr(ops, "enhance_hotspot_news", enhance)
    request = NewsOperationRequest(**payload("enhance"), source="hacker-news", page=2)
    first = await ops.start_operation(request, user_id=1)
    await asyncio.gather(*list(ops._tasks))
    before = captured[0].read_bytes()
    assert first["itemIds"] == [11, 22]
    assert load.await_args.kwargs["page"] == 2
    assert (await ops.start_operation(request, user_id=1))["id"] == first["id"]
    assert captured[0].read_bytes() == before
    assert len(captured) == 1


def test_interrupted_status_is_read_only_and_never_restarts(isolated):
    identifier = str(uuid4())
    path = isolated / identifier / "operation.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"id": identifier, "status": "running", "startedAt": "2020-01-01T00:00:00+00:00"}))
    before = path.read_bytes()
    assert ops.get_operation(identifier)["status"] == "interrupted"
    assert path.read_bytes() == before
    assert not ops._tasks


@pytest.mark.asyncio
async def test_budget_context_isolated_between_concurrent_tasks(tmp_path, monkeypatch):
    for key in ("RARDAR_LLM_TASK_ID", "RARDAR_LLM_RUN_ID", "RARDAR_LLM_BUDGET_PATH", "RARDAR_LLM_BUDGET_LIMIT"):
        monkeypatch.delenv(key, raising=False)
    ledgers = [
        ProviderBudgetLedger.initialize(
            tmp_path / str(i) / "budget.json", f"run-{i}", task_id=ops.QUICK_READ_TASK_ID, limit=2
        )
        for i in range(2)
    ]

    async def bound(ledger):
        with news_execution_budget(ledger):
            await asyncio.sleep(0)
            assert execution_budget("rardar_news_quickread")[0] is ledger
        assert execution_budget("rardar_news_quickread") is None

    await asyncio.gather(*(bound(ledger) for ledger in ledgers))


def test_writer_excludes_independent_cli_context(isolated):
    def cli_attempt():
        with locks.news_writer():
            pytest.fail("concurrent CLI writer entered")

    with locks.news_writer():
        with locks.news_writer():
            pass  # Existing business helpers intentionally share the owner.
        with pytest.raises(ProviderBudgetError, match="provider_budget_busy"):
            Context().run(cli_attempt)


@pytest.mark.asyncio
async def test_cancelled_enhancement_preserves_ledger_and_does_not_retry(isolated, monkeypatch):
    page = SimpleNamespace(items=[SimpleNamespace(id=11)])
    monkeypatch.setattr(ops, "load_hotspot_news", AsyncMock(return_value=(page, "etag")))
    entered = asyncio.Event()
    saved_results = []

    async def enhance(_db, *, frozen_page):
        ledger = execution_budget("rardar_news_quickread")[0]
        with ledger.execution("news_quickread"):
            saved_results.append(frozen_page.items[0].id)
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ops, "enhance_hotspot_news", enhance)
    request = NewsOperationRequest(**payload("enhance"))
    first = await ops.start_operation(request, user_id=1)
    await entered.wait()
    budget = next(isolated.rglob("provider-budget.json"))
    before = budget.read_bytes()
    tasks = list(ops._tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert ops.get_operation(first["id"])["status"] == "interrupted"
    assert (await ops.start_operation(request, user_id=1))["status"] == "interrupted"
    assert budget.read_bytes() == before
    assert saved_results == [11]
