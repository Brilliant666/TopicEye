"""Isolated Rardar product-mode API surface for the vertical POC."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core.database import async_session
from app.core.product_profile import get_product_profile
from app.rardar.ai_runtime import RardarAIError, call_rardar_ai
from app.rardar.artifact_adapter import RardarArtifactError, RardarIntelligenceAdapter
from app.rardar.explosion_service import build_explosion_board
from app.rardar.find_project_service import (
    FindProjectStateError,
    confirm_find_project_job,
    create_find_project_job,
    delete_find_project_job,
    get_find_project_job,
    retry_find_project_job,
)
from app.rardar.schemas import FindProjectConfirm, FindProjectCreate
from app.repositories.rardar_poc_repo import RardarAIRequestRepository, RardarFindProjectJobRepository
from app.services.llm.circuit_breaker import get_llm_circuit_breaker


def require_rardar_product_mode() -> None:
    if not get_product_profile().enabled:
        raise HTTPException(status_code=404, detail="Rardar product mode is disabled")


router = APIRouter(
    prefix="/rardar",
    tags=["rardar-poc"],
    dependencies=[Depends(require_rardar_product_mode)],
)


@router.get("/profile")
async def product_profile() -> dict:
    profile = get_product_profile()
    return {
        "key": profile.key,
        "productName": profile.product_name,
        "aiProvider": profile.ai_provider,
        "aiProviderMode": profile.ai_provider_mode,
        "model": profile.ai_model,
        "navigation": [{"href": href, "label": label} for href, label in profile.navigation],
        "legacyModulesDisposition": "hidden_not_deleted",
    }


@router.get("/explosion-board")
async def explosion_board(
    ai_scenario: str = Query("success", alias="aiScenario"),
) -> dict:
    try:
        return await build_explosion_board(ai_scenario=ai_scenario)
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/ai/probe")
async def ai_probe(
    effort: str = Query(..., pattern="^(medium|high|xhigh)$"),
    scenario: str = Query("success"),
) -> dict:
    try:
        outcome = await call_rardar_ai(
            scene="rardar_project_summary",
            reasoning_effort=effort,
            payload={
                "mockScenario": scenario,
                "repository": "fxbin/TopicEye",
                "sourceRevision": "probe-v1",
                "evidenceRefs": ["repository:https://github.com/fxbin/TopicEye"],
            },
            result_model=None,
        )
        return {"status": "ok", "result": outcome.result, "audit": outcome.audit}
    except RardarAIError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "state": exc.state.value, "message": str(exc)},
        ) from exc


@router.post("/find-jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(request: FindProjectCreate) -> dict:
    return await create_find_project_job(request)


@router.get("/find-jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await get_find_project_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Find Project job not found")
    return job


@router.post("/find-jobs/{job_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_job(job_id: str, request: FindProjectConfirm) -> dict:
    try:
        return await confirm_find_project_job(job_id, request.requirementProfile)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Find Project job not found") from exc
    except FindProjectStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/find-jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(job_id: str) -> dict:
    try:
        return await retry_find_project_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Find Project job not found") from exc
    except FindProjectStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/find-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str) -> Response:
    if not await delete_find_project_job(job_id):
        raise HTTPException(status_code=404, detail="Find Project job not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/diagnostics")
async def diagnostics() -> dict:
    profile = get_product_profile()
    adapter = RardarIntelligenceAdapter(profile.fixture_root)
    artifact = adapter.load_explosion_board()
    candidates = adapter.load_candidate_fixture()
    async with async_session() as db:
        jobs = await RardarFindProjectJobRepository(db).diagnostics()
        calls = await RardarAIRequestRepository(db).diagnostics()
    breaker = get_llm_circuit_breaker(profile.ai_routing_group)
    return {
        "productProfile": profile.key,
        "artifactRevision": artifact.artifactRevision,
        "candidateFixtureRevision": candidates.fixtureRevision,
        "provider": {
            "name": profile.ai_provider,
            "mode": profile.ai_provider_mode,
            "model": profile.ai_model,
            "networkCalls": False,
        },
        "jobs": jobs,
        "aiCalls": calls,
        "circuit": breaker.status(),
        "featureFlags": {"rardarProductMode": True, "legacyModules": "hidden"},
    }
