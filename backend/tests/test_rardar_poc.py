from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import async_session, engine
from app.main import app
from app.models.rardar_poc import RardarAIRequest, RardarFindProjectJob
from app.rardar.ai_runtime import RardarAIError, call_rardar_ai
from app.rardar.artifact_adapter import RardarArtifactError, RardarIntelligenceAdapter
from app.rardar.bootstrap import ensure_rardar_poc_runtime
from app.rardar.find_project_service import (
    confirm_find_project_job,
    create_find_project_job,
    delete_find_project_job,
    get_find_project_job,
    process_one_find_project_job,
    retry_find_project_job,
)
from app.rardar.schemas import FindProjectCreate, RequirementProfile
from app.services.llm.circuit_breaker import reset_llm_circuit_breakers
from app.services.llm.mock_sub2api import reset_mock_sub2api
from app.services.llm.provider import invalidate_model_cache
from app.services.llm.response_cache import get_llm_cache

FIXTURES = Path(__file__).resolve().parents[1] / "app" / "rardar" / "fixtures"


@pytest_asyncio.fixture
async def rardar_mode(monkeypatch, clean_tables):
    await engine.dispose(close=False)
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", True)
    monkeypatch.setattr(settings, "RARDAR_FIXTURE_ROOT", str(FIXTURES))
    reset_mock_sub2api()
    reset_llm_circuit_breakers()
    get_llm_cache().clear()
    yield
    await engine.dispose(close=False)


def _copy_fixtures(tmp_path: Path) -> Path:
    destination = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, destination)
    return destination


def _atomic_pointer(fixture_root: Path, revision: str, artifact: str, sha256: str) -> None:
    current = fixture_root / "explosion-board" / "current.json"
    staged = current.with_suffix(".next")
    staged.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "artifactRevision": revision,
                "artifact": artifact,
                "sha256": sha256,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(staged, current)


def test_artifact_adapter_switches_revisions_atomically_without_mixing(tmp_path: Path):
    root = _copy_fixtures(tmp_path)
    adapter = RardarIntelligenceAdapter(root)
    first = adapter.load_explosion_board()
    assert first.artifactRevision == "explosion-poc-a"
    assert first.generationId == "poc-generation-a"
    assert first.artifactVersion == 1
    assert first.coverageState == "degraded"
    assert all(item.sourceProvenance and item.coreCapabilities for item in first.exactTop)
    assert all(
        item.externalSignals and item.aiStatus == "pending" and item.observedWindowStarDelta >= 0
        for item in first.firstSeenPending
    )
    _atomic_pointer(
        root,
        "explosion-poc-b",
        "revisions/explosion-poc-b.json",
        "e76f36efbac3c58dc05e5eee8744e49442eef393b764c82942c3f4040e7f640f",
    )
    second = adapter.load_explosion_board()
    assert second.artifactRevision == "explosion-poc-b"
    assert [item.observedStarDelta for item in second.exactTop] != [item.observedStarDelta for item in first.exactTop]
    assert [item.rank for item in second.exactTop] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_rardar_routes_are_hidden_when_product_mode_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/rardar/profile")
    assert response.status_code == 404


def test_artifact_adapter_rejects_hash_mismatch_and_path_escape(tmp_path: Path):
    root = _copy_fixtures(tmp_path)
    current = root / "explosion-board" / "current.json"
    pointer = json.loads(current.read_text(encoding="utf-8"))
    pointer["sha256"] = "0" * 64
    current.write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(RardarArtifactError, match="digest"):
        RardarIntelligenceAdapter(root).load_explosion_board()

    pointer["artifact"] = "../find-project-candidates.v1.json"
    current.write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(RardarArtifactError):
        RardarIntelligenceAdapter(root).load_explosion_board()


def test_artifact_adapter_rejects_symlink_pointer(tmp_path: Path):
    root = _copy_fixtures(tmp_path)
    current = root / "explosion-board" / "current.json"
    real = root / "external-pointer.json"
    shutil.copy2(current, real)
    current.unlink()
    try:
        current.symlink_to(real)
    except OSError as exc:  # pragma: no cover - Windows hosts without symlink privilege
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(RardarArtifactError, match="symbolic link"):
        RardarIntelligenceAdapter(root).load_explosion_board()


@pytest.mark.asyncio
async def test_explosion_board_ai_failure_keeps_http_200_facts_and_order(rardar_mode):
    await ensure_rardar_poc_runtime()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/rardar/explosion-board", params={"aiScenario": "timeout"})
        repeated = await client.get("/api/v1/rardar/explosion-board", params={"aiScenario": "timeout"})
    assert response.status_code == 200
    assert repeated.status_code == 200
    payload = response.json()
    assert payload["aiChangesRanking"] is False
    assert [item["rank"] for item in payload["exactTop"]] == [1, 2, 3, 4, 5]
    assert [item["observedStarDelta"] for item in payload["exactTop"]] == sorted(
        [item["observedStarDelta"] for item in payload["exactTop"]], reverse=True
    )
    assert all(item["ai"]["profile"] is None for item in payload["exactTop"])
    async with async_session() as db:
        request_ids = list((await db.scalars(select(RardarAIRequest.request_id))).all())
    assert len(request_ids) == len(set(request_ids))


@pytest.mark.asyncio
async def test_http_request_observes_atomic_pointer_switch_without_restart(rardar_mode, tmp_path: Path):
    root = _copy_fixtures(tmp_path)
    settings.RARDAR_FIXTURE_ROOT = str(root)
    await ensure_rardar_poc_runtime()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/api/v1/rardar/explosion-board")
        _atomic_pointer(
            root,
            "explosion-poc-b",
            "revisions/explosion-poc-b.json",
            "e76f36efbac3c58dc05e5eee8744e49442eef393b764c82942c3f4040e7f640f",
        )
        second = await client.get("/api/v1/rardar/explosion-board")
    assert first.status_code == second.status_code == 200
    assert first.json()["artifactRevision"] == "explosion-poc-a"
    assert second.json()["artifactRevision"] == "explosion-poc-b"
    assert {item["ai"]["profile"]["sourceRevision"] for item in first.json()["exactTop"]} == {"explosion-poc-a"}
    assert {item["ai"]["profile"]["sourceRevision"] for item in second.json()["exactTop"]} == {"explosion-poc-b"}


@pytest.mark.asyncio
async def test_mock_sub2api_proves_effort_layers_cache_and_local_schema(rardar_mode):
    await ensure_rardar_poc_runtime()
    audits = []
    for effort in ("medium", "high", "xhigh"):
        outcome = await call_rardar_ai(
            scene="rardar_project_summary",
            reasoning_effort=effort,
            payload={
                "mockScenario": "success",
                "repository": "fxbin/TopicEye",
                "sourceRevision": f"effort-{effort}",
                "evidenceRefs": ["repository:TopicEye"],
            },
            result_model=None,
        )
        audits.append(outcome.audit)
    assert [audit["reasoningEffort"] for audit in audits] == ["medium", "high", "xhigh"]
    assert {audit["model"] for audit in audits} == {"gpt-5.6-sol"}
    assert {
        "projectId",
        "projectForm",
        "notablePoint",
        "coreCapabilities",
        "whyTrendingHypothesis",
        "schemaVersion",
    } <= set(outcome.result)

    payload = {
        "mockScenario": "success",
        "repository": "n8n-io/n8n",
        "sourceRevision": "cache-v1",
        "evidenceRefs": ["repository:n8n"],
    }
    first = await call_rardar_ai(
        scene="rardar_project_summary", reasoning_effort="medium", payload=payload, result_model=None
    )
    second = await call_rardar_ai(
        scene="rardar_project_summary", reasoning_effort="medium", payload=payload, result_model=None
    )
    assert first.audit["resultState"] == "ready"
    assert second.audit["resultState"] == "cache_hit"
    assert second.audit["usage"]["cachedTokens"] > 0

    effort_payload = {
        "mockScenario": "success",
        "repository": "fxbin/TopicEye",
        "sourceRevision": "effort-cache-v1",
        "evidenceRefs": ["repository:TopicEye"],
    }
    medium = await call_rardar_ai(
        scene="rardar_project_summary",
        reasoning_effort="medium",
        payload=effort_payload,
        result_model=None,
    )
    high = await call_rardar_ai(
        scene="rardar_project_summary",
        reasoning_effort="high",
        payload=effort_payload,
        result_model=None,
    )
    repeated_high = await call_rardar_ai(
        scene="rardar_project_summary",
        reasoning_effort="high",
        payload=effort_payload,
        result_model=None,
    )
    assert medium.result["reasoningEffort"] == "medium"
    assert high.result["reasoningEffort"] == "high"
    assert high.audit["resultState"] == "ready"
    assert repeated_high.audit["resultState"] == "cache_hit"

    for index, scenario in enumerate(("invalid_json", "schema_mismatch")):
        reset_llm_circuit_breakers()
        await invalidate_model_cache()
        with pytest.raises(RardarAIError) as raised:
            await call_rardar_ai(
                scene="rardar_project_summary",
                reasoning_effort="high",
                payload={
                    "mockScenario": scenario,
                    "repository": "fxbin/TopicEye",
                    "sourceRevision": f"invalid-{index}",
                    "evidenceRefs": ["repository:TopicEye"],
                },
                result_model=None,
            )
        assert raised.value.code in {"invalid_provider_json", "provider_schema_mismatch"}


@pytest.mark.asyncio
async def test_mock_provider_failure_matrix_and_circuit_recovery(rardar_mode):
    from app.services.llm.circuit_breaker import get_llm_circuit_breaker

    await ensure_rardar_poc_runtime()
    for index, scenario in enumerate(("timeout", "429", "5xx")):
        await invalidate_model_cache()
        breaker = get_llm_circuit_breaker("rardar_poc")
        breaker.failure_threshold = 1
        breaker.cooldown_seconds = 0.05
        with pytest.raises(RardarAIError) as raised:
            await call_rardar_ai(
                scene="rardar_project_summary",
                reasoning_effort="high",
                payload={
                    "mockScenario": scenario,
                    "repository": "fxbin/TopicEye",
                    "sourceRevision": f"failure-{index}",
                    "evidenceRefs": ["repository:TopicEye"],
                },
                result_model=None,
            )
        expected = {"timeout": "provider_timeout", "429": "provider_rate_limited", "5xx": "provider_5xx"}
        assert raised.value.code == expected[scenario]

    await invalidate_model_cache()
    breaker = get_llm_circuit_breaker("rardar_poc")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 0.05
    with pytest.raises(RardarAIError, match="503"):
        await call_rardar_ai(
            scene="rardar_project_summary",
            reasoning_effort="high",
            payload={
                "mockScenario": "5xx",
                "repository": "fxbin/TopicEye",
                "sourceRevision": "circuit-failure",
                "evidenceRefs": ["repository:TopicEye"],
            },
            result_model=None,
        )
    assert breaker.status()["state"] == "open"
    with pytest.raises(RardarAIError) as open_error:
        await call_rardar_ai(
            scene="rardar_project_summary",
            reasoning_effort="high",
            payload={
                "mockScenario": "success",
                "repository": "fxbin/TopicEye",
                "sourceRevision": "circuit-blocked",
                "evidenceRefs": ["repository:TopicEye"],
            },
            result_model=None,
        )
    assert open_error.value.code == "circuit_open"
    await asyncio.sleep(1.05)
    recovered = await call_rardar_ai(
        scene="rardar_project_summary",
        reasoning_effort="high",
        payload={
            "mockScenario": "success",
            "repository": "fxbin/TopicEye",
            "sourceRevision": "circuit-recovered",
            "evidenceRefs": ["repository:TopicEye"],
        },
        result_model=None,
    )
    assert recovered.audit["resultState"] == "ready"
    assert breaker.status()["state"] == "closed"


@pytest.mark.asyncio
async def test_find_project_job_success_failure_retry_and_control_plane_boundaries(rardar_mode, tmp_path: Path):
    await ensure_rardar_poc_runtime()
    root = _copy_fixtures(tmp_path)
    settings.RARDAR_FIXTURE_ROOT = str(root)
    original_pointer = (root / "explosion-board" / "current.json").read_bytes()

    created = await create_find_project_job(FindProjectCreate(query="寻找可自托管并能审计任务状态的开发者平台"))
    assert created["state"] == "queued"
    await process_one_find_project_job()
    quick = await get_find_project_job(created["jobId"])
    assert quick and quick["state"] == "quick_candidates_ready"
    assert len(quick["quickCandidates"]) == 5
    requirement = RequirementProfile.model_validate(quick["requirementProfile"])
    assert requirement.mustHave
    assert requirement.exclude
    assert requirement.technologyStack
    assert requirement.deployment
    assert requirement.licensePreference
    assert requirement.reuseGranularity
    assert requirement.acceptanceCriteria
    await confirm_find_project_job(created["jobId"], requirement)
    await process_one_find_project_job()
    ready = await get_find_project_job(created["jobId"])
    assert ready and ready["state"] == "ready"
    assert len(ready["result"]["candidates"]) == 3
    assert {item["reuseType"] for item in ready["result"]["candidates"]} == {
        "whole_product",
        "workflow",
        "module_or_library",
    }

    failing = await create_find_project_job(
        FindProjectCreate(
            query="验证持久 Job 在首次失败后能够安全重试",
            scenario="job_fail_once",
        )
    )
    await process_one_find_project_job()
    failed = await get_find_project_job(failing["jobId"])
    assert failed and failed["state"] == "failed" and failed["retryState"] == "queued"
    await retry_find_project_job(failing["jobId"])
    await process_one_find_project_job()
    retried = await get_find_project_job(failing["jobId"])
    assert retried and retried["state"] == "quick_candidates_ready"

    assert await delete_find_project_job(created["jobId"]) is True

    with_repository = await create_find_project_job(
        FindProjectCreate(
            query="分析一个公开仓库并寻找可替换或复用的实现",
            repositoryUrl="https://github.com/Brilliant666/rardar",
        )
    )
    assert with_repository["inputMode"] == "requirement_with_repo"
    await process_one_find_project_job()
    repository_quick = await get_find_project_job(with_repository["jobId"])
    assert repository_quick and repository_quick["state"] == "quick_candidates_ready"
    assert repository_quick["requirementProfile"]["repositoryContext"] == ("https://github.com/Brilliant666/rardar")
    assert (root / "explosion-board" / "current.json").read_bytes() == original_pointer
    assert (root / "explosion-board" / "revisions" / "explosion-poc-a.json").exists()


@pytest.mark.asyncio
async def test_artifact_replacement_does_not_rewrite_historical_job(rardar_mode, tmp_path: Path):
    root = _copy_fixtures(tmp_path)
    settings.RARDAR_FIXTURE_ROOT = str(root)
    first = await create_find_project_job(FindProjectCreate(query="验证历史 Job 来源版本不会被改写"))
    _atomic_pointer(
        root,
        "explosion-poc-b",
        "revisions/explosion-poc-b.json",
        "e76f36efbac3c58dc05e5eee8744e49442eef393b764c82942c3f4040e7f640f",
    )
    second = await create_find_project_job(FindProjectCreate(query="验证新 Job 读取新 artifact revision"))
    historical = await get_find_project_job(first["jobId"])
    assert historical and historical["explosionArtifactRevision"] == "explosion-poc-a"
    assert second["explosionArtifactRevision"] == "explosion-poc-b"


@pytest.mark.asyncio
async def test_postgresql_poc_tables_record_jobs_and_ai_audit(rardar_mode):
    await ensure_rardar_poc_runtime()
    created = await create_find_project_job(FindProjectCreate(query="验证 PostgreSQL 控制面持久状态"))
    await process_one_find_project_job()
    async with async_session() as db:
        jobs = await db.scalar(select(func.count()).select_from(RardarFindProjectJob))
        calls = await db.scalar(select(func.count()).select_from(RardarAIRequest))
        persisted = await db.get(RardarFindProjectJob, created["jobId"])
    assert jobs == 1
    assert calls == 1
    assert persisted and persisted.state == "quick_candidates_ready"
