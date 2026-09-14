"""Private persistence in disposable SQLite or explicitly isolated development PG.

No application startup, production PostgreSQL, source fetch or provider requests.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.models.rardar_find_run import RardarFindRun
from app.models.user import User
from app.schemas.rardar_find_runs import FindRun
from app.schemas.rardar_product import FindProjectRequest, FindProjectResponse, QuickProjectCandidate
from app.services.llm.find_operation import find_request_admission, find_request_event, reserve_find_request
from app.services.rardar_find_runs import FindRunError, FindRunService


@pytest_asyncio.fixture
async def sessions(tmp_path):
    configured = os.environ.get("RARDAR_FIND_TEST_POSTGRES")
    schema = None
    created = False
    if configured:
        url = make_url(configured)
        if (
            url.drivername != "postgresql+asyncpg"
            or url.database != "rardar_development"
            or url.username != "rardar_development_app"
            or url.host not in {"127.0.0.1", "localhost"}
            or url.port != 55433
            or url.query
        ):
            pytest.fail("Find PG tests require the dedicated local rardar_development database")
        schema = f"find_test_{uuid4().hex}"
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'private-find.db'}")
    try:
        async with engine.begin() as conn:
            if schema is not None:
                await conn.execute(CreateSchema(schema))
            await conn.run_sync(lambda sync: User.__table__.create(sync))
            await conn.run_sync(lambda sync: RardarFindRun.__table__.create(sync))
            await conn.execute(insert(User).values(id=1, email="one@example.invalid"))
            await conn.execute(insert(User).values(id=2, email="two@example.invalid"))
        created = True
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if schema is not None and created:
                # This exact UUID schema was created by this fixture. Never
                # truncate/drop public tables, other schemas or the database.
                async with engine.begin() as conn:
                    await conn.execute(DropSchema(schema, cascade=True))
        finally:
            await engine.dispose()


def request(text="Find a self hosted document tool"):
    return FindProjectRequest(requirement=text)


def result(*, state="ready", error=None):
    return FindProjectResponse(
        requirement=request().requirement,
        repositoryUrl=None,
        searchState="github_live",
        coverageLabel="Simulated isolated test search",
        sources=["https://github.com/example/docs"],
        quickCandidates=[],
        aiState=state,
        comparison={"candidates": [], "overallConclusion": "No sufficiently supported match in this test"}
        if state == "ready"
        else None,
        errorCode=error,
        promptVersion="rardar-find-project-v5",
        evidenceSources=[
            {
                "repository": "example/docs",
                "ref": "readme:old",
                "url": "https://github.com/example/docs/blob/frozen/README.md",
                "text": "Original version material: keep this exact evidence.",
                "kind": "readme",
            }
        ],
        model="mock-model",
        provider="mock-provider",
        cacheHit=True,
    )


def service(sessions, runner):
    return FindRunService(
        session_factory=sessions,
        config=SimpleNamespace(RARDAR_FIND_RUN_REQUEST_LIMIT=8, RARDAR_DAILY_OPERATIONS_ENABLED=False),
        runner=runner,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("state,error", [("ready", None), ("unavailable", "rardar_llm_invalid_output")])
async def test_saved_candidate_dates_survive_strict_response_readback(sessions, state, error):
    response = result(state=state, error=error)
    response.quickCandidates = [
        QuickProjectCandidate(
            githubRepositoryId=123,
            repository="example/docs",
            totalStars=20,
            updatedAt=datetime(2026, 9, 14, tzinfo=UTC),
            pushedAt=datetime(2026, 9, 13, tzinfo=UTC),
            htmlUrl="https://github.com/example/docs",
            preliminaryMatch="Documentation candidate",
            dataState="github_live",
        )
    ]
    runner = AsyncMock(return_value=response)
    svc = service(sessions, runner)
    created = await svc.create(1, request(), "date-readback-0001")
    executed = await svc.execute(1, created["runId"])
    fresh = service(sessions, runner)
    saved = await fresh.get(1, created["runId"])
    assert saved == executed
    # PostgreSQL JSON dates are strings; the real FastAPI response contract must
    # accept their JSON representation without weakening the product schema.
    restored = FindRun.model_validate(saved)
    assert restored.result.model_dump(mode="json") == response.model_dump(mode="json")
    assert runner.await_count == 1


async def paid_attempt(*, complete=True):
    async with find_request_admission():
        await reserve_find_request(scene="rardar_find_project_comparison", model="mock", daily=None)
        find_request_event("dispatched")
        if complete:
            find_request_event("completed")


@pytest.mark.asyncio
async def test_durable_result_new_service_readback_and_summary_privacy(sessions):
    calls = []

    async def runner(payload, *, config, operation_id, progress):
        calls.append(operation_id)
        # Running state is committed and independently readable before dispatch.
        saved = await svc.get(1, operation_id)
        assert saved["status"] == "running"
        await progress("comparison", result(state="unavailable", error="pending"))
        return result()

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "durable-key-00001")
    completed = await svc.execute(1, created["runId"])
    assert completed["status"] == "completed"
    assert completed["result"] == result().model_dump(mode="json")
    fresh = service(sessions, runner)
    assert await fresh.get(1, created["runId"]) == completed
    assert await fresh.by_key(1, "durable-key-00001") == completed
    assert await fresh.execute(1, created["runId"]) == completed
    recent = (await fresh.recent(1))["runs"]
    assert len(recent) == 1
    assert "result" not in recent[0] and "evidenceSources" not in recent[0] and "request" not in recent[0]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_ownership_is_checked_for_every_read_and_execute(sessions):
    async def runner(*args, **kwargs):
        raise AssertionError("unauthorized must not execute")

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "ownership-key-001")
    for action in (
        svc.get(2, created["runId"]),
        svc.by_key(2, "ownership-key-001"),
        svc.execute(2, created["runId"]),
    ):
        with pytest.raises(FindRunError) as error:
            await action
        assert error.value.status_code == 404
    assert (await svc.recent(2))["runs"] == []
    # Same key in a separate trusted user scope does not share private data.
    own = await svc.create(2, request("A different user's private requirement"), "ownership-key-001")
    assert own["runId"] != created["runId"]


@pytest.mark.asyncio
async def test_same_key_race_conflict_and_duplicate_execute_do_not_repeat_work(sessions):
    calls = []
    entered, release = asyncio.Event(), asyncio.Event()

    async def runner(*args, operation_id, **kwargs):
        calls.append(operation_id)
        entered.set()
        await release.wait()
        await paid_attempt()
        return result()

    svc = service(sessions, runner)
    rows = await asyncio.gather(*(svc.create(1, request(), "concurrent-key-01") for _ in range(5)))
    run_id = rows[0]["runId"]
    assert {row["runId"] for row in rows} == {run_id}
    with pytest.raises(FindRunError, match="find_idempotency_conflict"):
        await svc.create(1, request("different content same key"), "concurrent-key-01")
    first = asyncio.create_task(svc.execute(1, run_id))
    await entered.wait()
    assert (await svc.execute(1, run_id))["status"] == "running"
    # Lost initial response is recovered by key, not a new paid submission.
    assert (await svc.by_key(1, "concurrent-key-01"))["runId"] == run_id
    release.set()
    completed = await first
    assert completed["requestsUsed"] == len(calls) == 1
    assert (await svc.execute(1, run_id))["requestsUsed"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("used,status", [(0, "interrupted"), (1, "uncertain")])
async def test_expired_running_run_keeps_checkpoint_and_never_resumes(sessions, used, status):
    async def runner(*args, **kwargs):
        raise AssertionError("expired runs must not resume")

    svc = service(sessions, runner)
    created = await svc.create(1, request(), f"expired-key-0000{used}")
    checkpoint = result(state="unavailable", error="comparison_pending").model_dump(mode="json")
    async with sessions() as db:
        await db.execute(
            update(RardarFindRun)
            .where(RardarFindRun.run_id == created["runId"])
            .values(
                status="running",
                requests_used=used,
                execution_deadline=datetime.now(UTC) - timedelta(seconds=1),
                result_payload=checkpoint,
            )
        )
        await db.commit()
    resumed = await service(sessions, runner).execute(1, created["runId"])
    assert resumed["status"] == status
    assert resumed["result"] == checkpoint
    assert (await svc.recent(1))["runs"][0]["status"] == status


@pytest.mark.asyncio
async def test_cross_stage_run_limit_persisted_and_preserves_checkpoint(sessions):
    async def runner(*args, progress, **kwargs):
        await paid_attempt()
        await progress("comparison", result(state="unavailable", error="comparison_pending"))
        await paid_attempt()
        return result()

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "bounded-run-00001", request_limit=1)
    stopped = await svc.execute(1, created["runId"])
    assert stopped["status"] == "budget_stopped"
    assert stopped["requestsUsed"] == stopped["requestLimit"] == 1
    assert stopped["result"]["errorCode"] == "comparison_pending"
    assert stopped["errorCode"] == "find_run_request_limit"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,expected",
    [
        (result(state="insufficient_candidates"), "no_candidates"),
        (result(state="unavailable", error="invalid_output"), "failed"),
    ],
)
async def test_business_terminal_states_not_http_success(sessions, response, expected):
    async def runner(*args, **kwargs):
        return response

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "terminal-state-01")
    finished = await svc.execute(1, created["runId"])
    assert finished["status"] == expected
    assert finished["result"] == response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_timeout_after_dispatch_is_uncertain_not_validation_failure(sessions):
    async def runner(*args, **kwargs):
        await paid_attempt(complete=False)
        raise TimeoutError("simulated lost HTTP response")

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "uncertain-run-01")
    finished = await svc.execute(1, created["runId"])
    assert finished["status"] == "uncertain"
    assert finished["requestsUsed"] == 1


@pytest.mark.asyncio
async def test_final_save_failure_cannot_claim_saved_success(sessions, monkeypatch):
    from app.repositories.rardar_find_run_repo import FindRunRepository

    async def runner(*args, **kwargs):
        return result()

    original = FindRunRepository.checkpoint

    async def fail_final(self, run_id, token, **values):
        if values.get("status") == "completed":
            raise RuntimeError("simulated disk failure with sensitive diagnostics")
        return await original(self, run_id, token, **values)

    monkeypatch.setattr(FindRunRepository, "checkpoint", fail_final)
    svc = service(sessions, runner)
    created = await svc.create(1, request(), "save-failure-001")
    with pytest.raises(FindRunError, match="find_result_save_failed"):
        await svc.execute(1, created["runId"])
    assert (await svc.get(1, created["runId"]))["status"] != "completed"


@pytest.mark.asyncio
async def test_atomic_reserve_with_loaded_record(sessions):
    from app.repositories.rardar_find_run_repo import FindRunRepository

    svc = service(sessions, None)
    created = await svc.create(1, request(), "atomic-reserve-01")
    async with sessions() as db:
        repo = FindRunRepository(db)
        assert await repo.claim(1, created["runId"], "token", datetime.now(UTC) + timedelta(minutes=5))
        await db.commit()
    async with sessions() as db:
        repo = FindRunRepository(db)
        row = await repo.get(1, created["runId"])
        assert row.requests_used == 0
        assert await repo.reserve(created["runId"], "token", {"attempts": []})
        await db.commit()


@pytest.mark.asyncio
async def test_after_http_completed_local_timeout_is_not_upstream_uncertain(sessions):
    async def runner(*args, **kwargs):
        await paid_attempt()
        raise TimeoutError("local stage after visible HTTP response")

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "local-timeout-01")
    finished = await svc.execute(1, created["runId"])
    assert finished["status"] == "interrupted"
    assert finished["requestsUsed"] == 1


@pytest.mark.asyncio
async def test_real_router_auth_csrf_private_reads_and_untrusted_fields(sessions, monkeypatch):
    from app.api.v1 import auth, rardar

    calls = []

    async def runner(*args, **kwargs):
        calls.append("execute")
        return result()

    async def lookup(_db, token):
        return SimpleNamespace(id={"user-one": 1, "user-two": 2}[token]) if token in {"user-one", "user-two"} else None

    monkeypatch.setattr(rardar, "find_runs", service(sessions, runner))
    monkeypatch.setattr(rardar, "async_session", sessions)
    monkeypatch.setattr(rardar, "is_rardar_product", lambda: True)
    monkeypatch.setattr(auth, "get_user_for_token", lookup)
    app = FastAPI()
    app.include_router(rardar.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/rardar/find-runs")).status_code == 401
        assert (await client.get("/rardar/find-runs", headers={"Authorization": "Basic test"})).status_code == 401
        client.cookies.set(auth.settings.AUTH_COOKIE_NAME, "user-one")
        assert (await client.post("/rardar/find-runs", json=request().model_dump())).status_code == 403
        headers = {"Authorization": "Bearer user-one", "Idempotency-Key": "router-verified-01"}
        for extra in ({"owner": 2}, {"requestLimit": 1000}, {"runId": "fake"}):
            response = await client.post("/rardar/find-runs", headers=headers, json={**request().model_dump(), **extra})
            assert response.status_code == 422
        created = await client.post("/rardar/find-runs", headers=headers, json=request().model_dump())
        assert created.status_code == 200
        run_id = created.json()["runId"]
        assert calls == []  # Create commits identity but does not execute.
        for url in (f"/rardar/find-runs/{run_id}", "/rardar/find-runs", "/rardar/find-runs/by-key/router-verified-01"):
            read = await client.get(url, headers=headers)
            assert read.status_code == 200
            assert read.headers["cache-control"] == "private, no-store"
        assert calls == []
        other = {"Authorization": "Bearer user-two"}
        assert (await client.get(f"/rardar/find-runs/{run_id}", headers=other)).status_code == 404
        assert (await client.get("/rardar/find-runs", headers=other)).json() == {"runs": []}
        done = await client.post(f"/rardar/find-runs/{run_id}/execute", headers=headers)
        assert done.status_code == 200 and done.json()["status"] == "completed"
        await client.post(f"/rardar/find-runs/{run_id}/execute", headers=headers)
        assert calls == ["execute"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remaining,configured,operator_cap,expected",
    [(3, True, None, 3), (9, True, 2, 2), (0, False, None, 0), (50, True, 100, 8)],
)
async def test_run_cap_uses_server_and_remaining_daily_limit_without_reset(
    sessions, monkeypatch, remaining, configured, operator_cap, expected
):
    from app.services import rardar_find_runs as runs

    budget = AsyncMock(return_value={"remaining": remaining, "configured": configured})
    monkeypatch.setattr(runs, "daily_budget_status", budget)
    svc = service(sessions, None)
    svc.config.RARDAR_DAILY_OPERATIONS_ENABLED = True
    created = await svc.create(1, request(), "daily-bound-run-01", request_limit=operator_cap)
    assert created["requestLimit"] == expected
    budget.return_value = {"remaining": 100, "configured": True}
    retried = await svc.create(1, request(), "daily-bound-run-01", request_limit=100)
    assert retried["runId"] == created["runId"]
    assert retried["requestLimit"] == expected
    assert budget.await_count == 1


@pytest.mark.asyncio
async def test_partial_candidates_and_exact_evidence_remain_readable(sessions):
    response = result(state="unavailable", error="rardar_llm_invalid_output")
    response.quickCandidates = [
        QuickProjectCandidate(
            githubRepositoryId=12,
            repository="example/docs",
            totalStars=123,
            updatedAt=datetime.now(UTC),
            htmlUrl="https://github.com/example/docs",
            preliminaryMatch="Actual metadata retained in test",
            dataState="github_live",
        )
    ]

    async def runner(*args, **kwargs):
        return response

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "partial-visible-01")
    finished = await svc.execute(1, created["runId"])
    assert finished["status"] == "partial"
    assert finished["result"]["quickCandidates"][0]["repository"] == "example/docs"
    original_evidence = finished["result"]["evidenceSources"]
    response.evidenceSources[0].text = "Changed material must not replace old evidence"
    reread = await svc.get(1, created["runId"])
    assert reread["result"]["evidenceSources"] == original_evidence


@pytest.mark.asyncio
async def test_daily_unconfigured_zero_limit_still_permits_compatible_cache(sessions, monkeypatch):
    from app.services import rardar_find_runs as runs

    monkeypatch.setattr(runs, "daily_budget_status", AsyncMock(return_value={"remaining": 0, "configured": False}))

    async def cached_runner(*args, **kwargs):
        return result()  # No dispatch hook on already validated compatible cache.

    svc = service(sessions, cached_runner)
    svc.config.RARDAR_DAILY_OPERATIONS_ENABLED = True
    created = await svc.create(1, request(), "zero-cached-run-01")
    assert created["requestLimit"] == 0
    done = await svc.execute(1, created["runId"])
    assert done["status"] == "completed"
    assert done["requestsUsed"] == 0
    assert done["result"]["cacheHit"] is True


@pytest.mark.asyncio
async def test_known_http_failure_is_failed_not_uncertain(sessions):
    async def runner(*args, **kwargs):
        await paid_attempt(complete=False)
        find_request_event("failed")
        find_request_event("known_failed")
        return result(state="unavailable", error="rardar_llm_failed")

    svc = service(sessions, runner)
    created = await svc.create(1, request(), "known-http-fail-01")
    done = await svc.execute(1, created["runId"])
    assert done["status"] == "failed"
    assert done["requestsUsed"] == 1


@pytest.mark.asyncio
async def test_create_database_failure_is_sanitized(sessions, monkeypatch):
    from app.repositories.rardar_find_run_repo import FindRunRepository

    async def fail_insert(self, **values):
        raise OperationalError(
            "INSERT private_find", {"requirement": "private requirement"}, RuntimeError("database down")
        )

    monkeypatch.setattr(FindRunRepository, "add", fail_insert)
    svc = service(sessions, None)
    with pytest.raises(FindRunError, match="find_run_save_failed") as error:
        await svc.create(1, request(), "db-error-safe-001")
    assert error.value.status_code == 503
    assert str(error.value) == "find_run_save_failed"
    assert error.value.__suppress_context__
