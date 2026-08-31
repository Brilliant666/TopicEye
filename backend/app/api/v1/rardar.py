"""Rardar-mode read-only product APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

from app.core.product_profile import is_rardar_product
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError
from app.integrations.rardar.discover_serving_schemas import DiscoverApiResponse, DiscoverProjectDetail
from app.integrations.rardar.serving_schemas import ServingProjectDetail, ServingTodaySnapshot
from app.schemas.rardar_product import (
    FindProjectRequest,
    FindProjectResponse,
    ProjectExplanationRequest,
    ProjectExplanationResponse,
    ProjectInsightRequest,
)
from app.services.rardar_intelligence import (
    load_discover_project_detail,
    load_discover_snapshot,
    load_explosion_board,
    load_project_detail,
    load_today_snapshot,
)
from app.services.rardar_product import (
    RardarProductError,
    explain_discover_project_by_id,
    explain_project,
    explain_project_by_id,
    find_projects,
)

router = APIRouter(prefix="/rardar", tags=["rardar"])

_SERVING_CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=45"


def _cache_headers(response: Response, etag: str) -> None:
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _SERVING_CACHE_CONTROL
    response.headers["Vary"] = "Accept"


def _not_modified(request: Request, etag: str) -> Response | None:
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": _SERVING_CACHE_CONTROL, "Vary": "Accept"},
        )
    return None


@router.get("/today", response_model=ServingTodaySnapshot)
def today_snapshot(request: Request, response: Response):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        snapshot, etag = load_today_snapshot()
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc
    cached = _not_modified(request, etag)
    if cached:
        return cached
    _cache_headers(response, etag)
    return snapshot


@router.get("/explosion-board", response_model=ExplosionBoardResponse)
def explosion_board(request: Request, response: Response):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        board = load_explosion_board()
        etag = f'"{board.artifactSha256 or board.generationId or "not-synced"}"'
        cached = _not_modified(request, etag)
        if cached:
            return cached
        _cache_headers(response, etag)
        return board
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/discover", response_model=DiscoverApiResponse)
def discover_snapshot(request: Request, response: Response):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        snapshot, etag = load_discover_snapshot()
    except RardarArtifactError as exc:
        not_configured = exc.code in {
            "rardar_intelligence_not_configured",
            "rardar_intelligence_unavailable",
            "rardar_discover_not_configured",
        }
        response.status_code = 503
        return DiscoverApiResponse(
            status="not_configured" if not_configured else "invalid",
            generation=None,
            freshnessState="unavailable",
            updateCadenceMinutes=120,
            stageCounts={
                "justDiscovered": 0,
                "outsideTodayMomentum": 0,
                "rising": 0,
                "nearValidation": 0,
            },
            stages={
                "justDiscovered": [],
                "outsideTodayMomentum": [],
                "rising": [],
                "nearValidation": [],
            },
            coverage=None,
            conflicts={"count": 0, "reasons": {}},
            code=exc.code,
        )
    cached = _not_modified(request, etag)
    if cached:
        return cached
    _cache_headers(response, etag)
    return snapshot


@router.get("/discover/projects/{github_repository_id}", response_model=DiscoverProjectDetail)
def discover_project_detail(
    request: Request,
    response: Response,
    github_repository_id: int = Path(gt=0),
    generation_id: str = Query(alias="generationId", min_length=2, max_length=127),
):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        detail, etag = load_discover_project_detail(github_repository_id, generation_id)
    except RardarArtifactError as exc:
        if exc.code == "rardar_discover_project_not_found":
            status_code = 404
        elif exc.code == "rardar_discover_revision_mismatch":
            status_code = 409
        else:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    cached = _not_modified(request, etag)
    if cached:
        return cached
    _cache_headers(response, etag)
    return detail


@router.get("/projects/{github_repository_id}", response_model=ServingProjectDetail)
def project_detail(
    request: Request,
    response: Response,
    github_repository_id: int = Path(gt=0),
    generation_id: str = Query(alias="generationId", min_length=2, max_length=127),
):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        detail, etag = load_project_detail(github_repository_id, generation_id)
    except RardarArtifactError as exc:
        if exc.code == "rardar_serving_project_not_found":
            status_code = 404
        elif exc.code in {
            "rardar_serving_source_invalid",
            "rardar_serving_source_not_found",
            "rardar_serving_mixed_generation",
        }:
            status_code = 409
        else:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    cached = _not_modified(request, etag)
    if cached:
        return cached
    _cache_headers(response, etag)
    return detail


@router.post("/projects/explain", response_model=ProjectExplanationResponse)
async def project_explanation(payload: ProjectExplanationRequest) -> ProjectExplanationResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return await explain_project(payload)
    except RardarProductError as exc:
        status_code = 409 if exc.code == "rardar_project_revision_changed" else 404
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    except RardarArtifactError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/projects/{github_repository_id}/insight", response_model=ProjectExplanationResponse)
async def project_insight(
    payload: ProjectInsightRequest,
    github_repository_id: int = Path(gt=0),
) -> ProjectExplanationResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return await explain_project_by_id(github_repository_id, payload.generationId)
    except RardarProductError as exc:
        status_code = 409 if exc.code == "rardar_project_revision_changed" else 404
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    except RardarArtifactError as exc:
        if exc.code == "rardar_serving_project_not_found":
            status_code = 404
        elif exc.code in {
            "rardar_serving_source_invalid",
            "rardar_serving_source_not_found",
            "rardar_serving_mixed_generation",
        }:
            status_code = 409
        else:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc


@router.post("/discover/projects/{github_repository_id}/insight", response_model=ProjectExplanationResponse)
async def discover_project_insight(
    payload: ProjectInsightRequest,
    github_repository_id: int = Path(gt=0),
) -> ProjectExplanationResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return await explain_discover_project_by_id(github_repository_id, payload.generationId)
    except RardarProductError as exc:
        status_code = 409 if exc.code == "rardar_project_revision_changed" else 404
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    except RardarArtifactError as exc:
        if exc.code == "rardar_discover_project_not_found":
            status_code = 404
        elif exc.code == "rardar_discover_revision_mismatch":
            status_code = 409
        else:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc


@router.post("/find-projects", response_model=FindProjectResponse)
async def find_project_candidates(payload: FindProjectRequest) -> FindProjectResponse:
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    return await find_projects(payload)
