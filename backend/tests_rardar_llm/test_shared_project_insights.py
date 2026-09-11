"""Explicitly mocked Provider responses exercise the real insight adapter."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import rardar as api
from app.schemas.rardar_product import SharedProjectInsightRequest, SharedProjectInsightStatus
from app.services import rardar_product, rardar_project_insights as service
from app.services.llm.daily_provider_budget import ProviderWorkYield
from tests_rardar_llm.test_product import _evidence, _insight, _metadata


@pytest.fixture
def setup(monkeypatch, tmp_path):
    service._RUNNING.clear()
    service._LAST_STATE.clear()
    monkeypatch.setattr(service.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    project = {
        "projectId": "new-project",
        "repository": "fixture/repository",
        "githubRepositoryId": None,
        "description": "A real repository fixture",
        "generationId": "boards-one",
    }
    evidence = service._stable_evidence(_evidence())
    calls = []

    async def route():
        return "route-one"

    async def model(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(value=_insight(), metadata=_metadata())

    monkeypatch.setattr(service, "_project", lambda identifier, request: dict(project))
    monkeypatch.setattr(service, "_material_evidence", lambda project, **kwargs: evidence)
    monkeypatch.setattr(service, "resolve_rardar_route_identity", route)
    monkeypatch.setattr(rardar_product, "call_rardar_structured", model)
    return project, evidence, calls


def request(context="trending", generation="boards-one"):
    return SharedProjectInsightRequest(generationId=generation, context=context)


@pytest.mark.asyncio
async def test_new_board_project_uses_existing_engine_and_cross_context_saved_result(setup, monkeypatch):
    project, evidence, calls = setup
    first = await service.start_project_insight("new-project", request())
    assert first.state == "ready" and len(calls) == 1
    assert first.result.githubRepositoryId is None  # no legacy numeric membership gate
    monkeypatch.setattr(service, "collect_project_evidence", lambda *args: pytest.fail("GET must not collect"))
    service._LAST_STATE.clear()  # process-local LLM/status cache is not the saved result
    second = await service.read_project_insight("new-project", request("historical_hot", "history"))
    assert second.state == "ready" and second.result.cacheHit
    assert second.result.generationId == "boards-one"  # original result provenance is not rewritten
    third = await service.start_project_insight("new-project", request("historical_hot", "history"))
    assert third.result.cacheHit and len(calls) == 1


@pytest.mark.asyncio
async def test_reads_without_material_do_not_collect_or_call_model(setup, monkeypatch):
    monkeypatch.setattr(service, "_material_evidence", lambda project, **kwargs: None)
    monkeypatch.setattr(service, "collect_project_evidence", lambda *args: pytest.fail("no GET network"))
    result = await service.read_project_insight("new-project", request())
    assert result.state == "unprocessed" and not setup[2]


def test_saved_analysis_evidence_can_be_read_after_ttl_without_changing_collection_ttl(setup):
    from app.services import rardar_project_evidence as materials

    project = setup[0]
    facts = service._facts(project)
    revision = materials._canonical_digest(
        {"repository": project["repository"], **facts, "includeReadmeBody": False, "readmeOnly": False}
    )
    evidence = _evidence()
    evidence = replace(evidence, digest=materials._canonical_digest(evidence.payload))
    materials._persist_evidence(project["repository"], revision, facts, evidence, {})
    path = next(materials._persistent_root().glob(f"*/{revision}.json"))
    saved = json.loads(path.read_bytes())
    saved.pop("checksum")
    saved["collectedAt"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    service.atomic(path, {**saved, "checksum": materials._canonical_digest(saved)})
    assert materials.read_saved_project_evidence(project["repository"], facts) is None
    old = materials.read_saved_project_evidence(project["repository"], facts, allow_stale=True)
    assert old is not None and old.digest == evidence.digest and old.cache_hit
    changed = {**facts, "description": "Changed actual repository description"}
    assert materials.read_saved_project_evidence(project["repository"], changed, allow_stale=True) is None


@pytest.mark.asyncio
async def test_material_and_route_changes_do_not_expose_old_healthy_result(setup, monkeypatch):
    await service.start_project_insight("new-project", request())
    evidence = replace(setup[1], payload={**setup[1].payload, "description": "Changed actual content"})
    monkeypatch.setattr(service, "_material_evidence", lambda project, **kwargs: service._stable_evidence(evidence))
    assert (await service.read_project_insight("new-project", request())).state == "unprocessed"
    monkeypatch.setattr(service, "_material_evidence", lambda project, **kwargs: setup[1])

    async def route():
        return "route-changed"

    monkeypatch.setattr(service, "resolve_rardar_route_identity", route)
    assert (await service.read_project_insight("new-project", request())).state == "unprocessed"


def test_only_observation_changes_preserve_material_identity(setup):
    evidence = setup[1]
    one = replace(
        evidence,
        payload={
            **evidence.payload,
            "generationId": "one",
            "generatedAt": "old",
            "evidenceDigest": "a" * 64,
            "totalStars": 10,
        },
    )
    two = replace(
        evidence,
        payload={
            **evidence.payload,
            "generationId": "two",
            "generatedAt": "new",
            "evidenceDigest": "b" * 64,
            "totalStars": 20,
        },
    )
    assert service._stable_evidence(one).digest == service._stable_evidence(two).digest


def test_semantic_nested_fields_and_evidence_names_are_never_removed(setup):
    first = {
        **setup[1].payload,
        "evidenceIndex": {"rank": "rank means priority", "digest": "SHA-256"},
        "readme": {"generatedAt": "a real example field", "stars": "astronomy units"},
    }
    second = {**first, "evidenceIndex": {"rank": "rank means dimension", "digest": "SHA-256"}}
    normalized = service._without_observation_context(first)
    assert normalized["readme"] == first["readme"]
    assert normalized["evidenceIndex"] == first["evidenceIndex"]
    assert service.digest(normalized) != service.digest(service._without_observation_context(second))


@pytest.mark.asyncio
async def test_read_route_or_material_errors_are_safe_product_states(setup, monkeypatch):
    async def broken_route():
        raise RuntimeError("sensitive-config-detail-must-not-escape")

    monkeypatch.setattr(service, "resolve_rardar_route_identity", broken_route)
    result = await service.read_project_insight("new-project", request())
    assert result.state == "unavailable" and result.errorCode == "project_insight_route_unavailable"
    assert "sensitive" not in result.model_dump_json()

    def broken_material(project, **kwargs):
        raise ValueError("bad local projection")

    monkeypatch.setattr(service, "_material_evidence", broken_material)
    result = await service.read_project_insight("new-project", request())
    assert result.errorCode == "project_insight_material_invalid"


@pytest.mark.asyncio
async def test_corrupt_or_invalid_reference_saved_result_never_displayed(setup):
    await service.start_project_insight("new-project", request())
    path = await service._cache_path(setup[0], setup[1])
    value = json.loads(path.read_text())
    value["result"]["analysis"]["conclusionSummary"]["evidenceRefs"] = ["invented:ref"]
    value["digest"] = service.digest(value["result"])
    service.atomic(path, value)
    assert (await service.read_project_insight("new-project", request())).state == "unprocessed"


@pytest.mark.asyncio
async def test_duplicate_submit_shares_running_task_and_waiting_is_not_failure(setup, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def slow(project, payload):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return SharedProjectInsightStatus(state="waiting", errorCode="interactive_request_waiting")

    monkeypatch.setattr(service, "_execute", slow)
    first = asyncio.create_task(service.start_project_insight("new-project", request()))
    await entered.wait()
    second = asyncio.create_task(service.start_project_insight("new-project", request("historical_hot")))
    assert (await service.read_project_insight("new-project", request())).state == "running"
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second)
    assert calls == 1 and all(result.state == "waiting" for result in results)


@pytest.mark.asyncio
async def test_browser_cancellation_does_not_cancel_paid_work_or_duplicate_it(setup, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    original = rardar_product.call_rardar_structured

    async def slow(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(rardar_product, "call_rardar_structured", slow)
    browser = asyncio.create_task(service.start_project_insight("new-project", request()))
    await entered.wait()
    browser.cancel()
    with pytest.raises(asyncio.CancelledError):
        await browser
    assert (await service.read_project_insight("new-project", request())).state == "running"
    resume = asyncio.create_task(service.start_project_insight("new-project", request()))
    release.set()
    result = await resume
    assert result.state == "ready" and len(setup[2]) == 1
    assert (await service.read_project_insight("new-project", request())).result.cacheHit


@pytest.mark.asyncio
async def test_actual_adapter_task_keeps_work_slice_and_find_reserved_allowance(setup, monkeypatch, tmp_path):
    from app.services.llm import daily_provider_budget as daily

    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")
    ledger = daily.daily_ledger(100)
    ledger.reservation_limit = 1
    ledger.interactive_reserve = 1
    original = rardar_product.call_rardar_structured

    async def dispatch(**kwargs):
        async with daily.managed_budget_execution(None, (ledger, "project_profile"), scene=kwargs["scene"].value):
            return await original(**kwargs)

    monkeypatch.setattr(rardar_product, "call_rardar_structured", dispatch)
    with daily.work_slice(1) as state:
        result = await service.start_project_insight("new-project", request())
    assert result.state == "waiting" and result.errorCode == "interactive_budget_reserved"
    assert state.used_requests == 0 and ledger.snapshot()["attempted"] == 0
    ledger.reservation_limit = 2  # fixture allows one background request without touching the reserve
    with daily.work_slice(1) as state:
        result = await service.start_project_insight("new-project", request())
    assert result.state == "ready" and state.used_requests == 1
    assert ledger.snapshot()["attempted"] == 1


@pytest.mark.asyncio
async def test_cooperative_budget_yield_remains_waiting_and_no_saved_result(setup, monkeypatch):
    async def yield_work(**kwargs):
        raise ProviderWorkYield("interactive_budget_reserved")

    monkeypatch.setattr(rardar_product, "call_rardar_structured", yield_work)
    result = await service.start_project_insight("new-project", request())
    assert result.state == "waiting" and result.errorCode == "interactive_budget_reserved"
    assert not list(service._directory(setup[0]).glob("*.json"))


def test_post_requires_real_auth_dependency_and_same_origin_while_get_only_reads(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    monkeypatch.setattr(api, "is_rardar_product", lambda: True)
    monkeypatch.setattr(api.settings, "CORS_ORIGINS", "http://127.0.0.1:3000")
    called = []

    async def denied():
        raise HTTPException(status_code=401)

    async def start(identifier, payload):
        called.append(identifier)
        return SharedProjectInsightStatus(state="waiting")

    async def read(identifier, payload):
        return SharedProjectInsightStatus(state="unprocessed")

    app.dependency_overrides[api.get_current_user] = denied
    monkeypatch.setattr(service, "start_project_insight", start)
    monkeypatch.setattr(service, "read_project_insight", read)
    client = TestClient(app)
    path = "/api/v1/rardar/project-insights/new-project"
    assert client.get(path, params={"generationId": "one"}).status_code == 200
    assert client.post(path, json={"generationId": "one"}).status_code == 401
    app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(id=1)
    assert (
        client.post(path, json={"generationId": "one"}, headers={"origin": "https://elsewhere.test"}).status_code == 403
    )
    assert (
        client.post(path, json={"generationId": "one"}, headers={"origin": "http://127.0.0.1:3000"}).status_code == 200
    )
    assert called == ["new-project"]
