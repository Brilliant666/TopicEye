"""Durable Find Project workflow backed by PostgreSQL control-plane state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.database import async_session
from app.core.product_profile import get_product_profile
from app.models.rardar_poc import RardarFindProjectJob
from app.rardar.ai_runtime import RardarAIError, call_rardar_ai
from app.rardar.artifact_adapter import RardarIntelligenceAdapter
from app.rardar.schemas import (
    CandidateFixture,
    FindProjectCreate,
    FindProjectResult,
    MatchedProject,
    RequirementProfile,
)
from app.repositories.rardar_poc_repo import RardarFindProjectJobRepository


class FindProjectStateError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _event(state: str, detail: str) -> dict[str, str]:
    return {"state": state, "detail": detail, "at": _now().isoformat()}


def _serialize_job(job: RardarFindProjectJob) -> dict[str, Any]:
    return {
        "jobId": job.job_id,
        "inputMode": job.input_mode,
        "query": job.query,
        "repositoryUrl": job.repository_url,
        "scenario": job.scenario,
        "state": job.state,
        "stateHistory": job.state_history,
        "requirementProfile": job.requirement_profile,
        "confirmedRequirementProfile": job.confirmed_requirement_profile,
        "quickCandidates": job.quick_candidates,
        "result": job.result,
        "candidateFixtureRevision": job.candidate_fixture_revision,
        "explosionArtifactRevision": job.explosion_artifact_revision,
        "attemptCount": job.attempt_count,
        "retryState": job.retry_state,
        "errorCode": job.error_code,
        "errorMessage": job.error_message,
        "createdAt": job.created_at.isoformat(),
        "updatedAt": job.updated_at.isoformat(),
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


async def create_find_project_job(request: FindProjectCreate) -> dict[str, Any]:
    profile = get_product_profile()
    adapter = RardarIntelligenceAdapter(profile.fixture_root)
    artifact = adapter.load_explosion_board()
    candidates = adapter.load_candidate_fixture()
    job = RardarFindProjectJob(
        job_id=f"find_{uuid4().hex}",
        input_mode="requirement_with_repo" if request.repositoryUrl else "requirement_only",
        query=request.query,
        repository_url=str(request.repositoryUrl) if request.repositoryUrl else None,
        scenario=request.scenario,
        state="queued",
        state_history=[_event("queued", "请求已持久化，等待独立 Worker 领取")],
        candidate_fixture_revision=candidates.fixtureRevision,
        explosion_artifact_revision=artifact.artifactRevision,
        created_at=_now(),
        updated_at=_now(),
    )
    async with async_session() as db:
        await RardarFindProjectJobRepository(db).create(job)
        await db.commit()
        return _serialize_job(job)


async def get_find_project_job(job_id: str) -> dict[str, Any] | None:
    async with async_session() as db:
        job = await RardarFindProjectJobRepository(db).get(job_id)
        return _serialize_job(job) if job else None


async def confirm_find_project_job(job_id: str, requirement: RequirementProfile) -> dict[str, Any]:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            raise KeyError(job_id)
        if job.state != "quick_candidates_ready":
            raise FindProjectStateError("job_not_waiting_for_requirement_confirmation")
        job.confirmed_requirement_profile = requirement.model_dump(mode="json")
        job.state = "deep_analysis"
        job.state_history = [
            *job.state_history,
            _event("deep_analysis", "RequirementProfile 已确认，等待 xhigh 横向比较"),
        ]
        job.updated_at = _now()
        await db.commit()
        return _serialize_job(job)


async def retry_find_project_job(job_id: str) -> dict[str, Any]:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            raise KeyError(job_id)
        if job.state != "failed" or job.retry_state not in {"queued", "deep_analysis"}:
            raise FindProjectStateError("job_is_not_retryable")
        job.state = job.retry_state
        job.state_history = [
            *job.state_history,
            _event(job.state, "人工重试已排队，保留历史失败记录"),
        ]
        job.lease_id = None
        job.lease_expires_at = None
        job.error_code = None
        job.error_message = None
        job.updated_at = _now()
        await db.commit()
        return _serialize_job(job)


async def delete_find_project_job(job_id: str) -> bool:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            return False
        await repo.delete(job)
        await db.commit()
        return True


async def _transition(job_id: str, state: str, detail: str) -> RardarFindProjectJob:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            raise KeyError(job_id)
        job.state = state
        job.state_history = [*job.state_history, _event(state, detail)]
        job.updated_at = _now()
        await db.commit()
        return job


async def _finish_quick_candidates(
    job_id: str,
    requirement: RequirementProfile,
    fixture: CandidateFixture,
) -> None:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            raise KeyError(job_id)
        job.requirement_profile = requirement.model_dump(mode="json")
        job.quick_candidates = [item.model_dump(mode="json") for item in fixture.candidates[:5]]
        job.state = "quick_candidates_ready"
        job.state_history = [
            *job.state_history,
            _event("quick_candidates_ready", "5 个版本化候选已就绪，等待用户确认需求画像"),
        ]
        job.lease_id = None
        job.lease_expires_at = None
        job.updated_at = _now()
        await db.commit()


def _matched_candidate(candidate, requirement: RequirementProfile, position: int) -> MatchedProject:
    reuse_types = ("whole_product", "workflow", "module_or_library")
    costs = ("high", "medium", "medium")
    covered = [
        capability
        for capability in requirement.mustHave
        if any(token.lower() in capability.lower() for token in ("自托管", "编排", "验证"))
    ]
    return MatchedProject(
        projectId=candidate.projectId,
        repository=candidate.repository,
        summaryZh=candidate.summaryZh,
        whyMatched="候选的可运行工程证据覆盖了需求画像中的核心编排、持久化或验证能力。",
        mustHaveCoverage=covered or requirement.mustHave[:1],
        missingCapabilities=[] if position == 0 else ["需按 Rardar artifact 边界补充适配层"],
        unknownCapabilities=["真实生产负载下的长期资源曲线"],
        technicalCompatibility=f"技术标签：{', '.join(candidate.technicalTags)}；可通过隔离 adapter 接入。",
        reuseType=reuse_types[position],
        referenceKinds=[],
        integrationCost=costs[position],
        integrationWorkItems=["验证上游升级边界", "保持 Rardar 事实 artifact 为唯一权威"],
        engineeringEvidence=candidate.engineeringEvidence,
        licenseAndRisk=f"许可证：{candidate.license}；合入前需复核分发与商用边界。",
        evidenceRefs=[str(item.url) for item in candidate.engineeringEvidence],
        confidence=0.86 - position * 0.06,
        nextValidationAction="在隔离分支运行一个可回滚的接口与资源基准验证。",
    )


async def _finish_deep_analysis(job_id: str, fixture: CandidateFixture, selected: list[str]) -> None:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            raise KeyError(job_id)
        requirement = RequirementProfile.model_validate(job.confirmed_requirement_profile)
        lookup = {item.repository: item for item in fixture.candidates}
        chosen = [lookup[name] for name in selected if name in lookup][:3]
        if len(chosen) != 3:
            raise FindProjectStateError("provider_did_not_select_three_fixture_candidates")
        result = FindProjectResult(
            requirementProfile=requirement,
            candidates=[_matched_candidate(candidate, requirement, index) for index, candidate in enumerate(chosen)],
            comparedAt=_now(),
            sourceRevision=fixture.fixtureRevision,
            model="gpt-5.6-sol",
            reasoningEffort="xhigh",
        )
        job.result = result.model_dump(mode="json")
        job.state = "ready"
        job.state_history = [
            *job.state_history,
            _event("ready", "3 个有证据的复用方案已完成同批横向比较"),
        ]
        job.lease_id = None
        job.lease_expires_at = None
        job.completed_at = _now()
        job.updated_at = _now()
        await db.commit()


async def _fail_job(job_id: str, retry_state: str, code: str, message: str) -> None:
    async with async_session() as db:
        repo = RardarFindProjectJobRepository(db)
        job = await repo.get(job_id, for_update=True)
        if job is None:
            return
        job.state = "failed"
        job.retry_state = retry_state
        job.error_code = code
        job.error_message = message[:1000]
        job.lease_id = None
        job.lease_expires_at = None
        job.state_history = [*job.state_history, _event("failed", f"{code}: {message[:200]}")]
        job.updated_at = _now()
        await db.commit()


async def process_one_find_project_job() -> str | None:
    """Claim and process one durable unit; returns the claimed job id."""
    async with async_session() as db:
        job = await RardarFindProjectJobRepository(db).claim_next()
        if job is None:
            return None
        job_id = job.job_id
        claimed_state = job.state
        attempt_count = job.attempt_count
        await db.commit()

    profile = get_product_profile()
    fixture = RardarIntelligenceAdapter(profile.fixture_root).load_candidate_fixture()
    try:
        if job.scenario == "job_fail_once" and attempt_count == 1:
            raise FindProjectStateError("simulated_first_worker_attempt_failure")
        ai_scenario = "success" if job.scenario == "job_fail_once" else job.scenario
        if claimed_state == "queued":
            await _transition(job_id, "parsing_requirement", "Worker 正在通过 high 推导 RequirementProfile")
            outcome = await call_rardar_ai(
                scene="rardar_requirement_profile",
                reasoning_effort="high",
                payload={
                    "mockScenario": ai_scenario,
                    "query": job.query,
                    "repositoryUrl": job.repository_url,
                },
                result_model=RequirementProfile,
            )
            await _finish_quick_candidates(job_id, outcome.result, fixture)
        elif claimed_state == "deep_analysis":
            requirement = RequirementProfile.model_validate(job.confirmed_requirement_profile)
            outcome = await call_rardar_ai(
                scene="rardar_candidate_compare",
                reasoning_effort="xhigh",
                payload={
                    "mockScenario": ai_scenario,
                    "requirementProfile": requirement.model_dump(mode="json"),
                    "candidates": [item.model_dump(mode="json") for item in fixture.candidates[:5]],
                },
                result_model=None,
            )
            selected = outcome.result.get("selectedRepositories", [])
            await _finish_deep_analysis(job_id, fixture, selected)
        return job_id
    except RardarAIError as exc:
        await _fail_job(job_id, claimed_state, exc.code, str(exc))
        return job_id
    except Exception as exc:
        await _fail_job(job_id, claimed_state, "worker_processing_failed", str(exc))
        return job_id
