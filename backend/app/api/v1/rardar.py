"""Rardar-mode read-only product APIs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_admin_user, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.product_profile import is_rardar_product
from app.core.rardar_scope import RardarModulePaused, require_module_execution
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError
from app.integrations.rardar.discover_serving_schemas import DiscoverApiResponse, DiscoverProjectDetail
from app.integrations.rardar.selection_schemas import SelectionApiResponse, SelectionProjectDetail
from app.integrations.rardar.serving_schemas import ServingProjectDetail, ServingTodaySnapshot
from app.schemas.rardar_discover_operations import DiscoverOperationRequest, DiscoverPrepareRequest
from app.schemas.rardar_hotspot_news import HotspotNewsResponse
from app.schemas.rardar_news_operations import NewsOperationRequest
from app.schemas.rardar_product import (
    FindProjectRequest,
    FindProjectResponse,
    ProjectExplanationRequest,
    ProjectExplanationResponse,
    ProjectInsightRequest,
    SharedProjectInsightRequest,
    SharedProjectInsightStatus,
)
from app.schemas.rardar_today_operations import TodayOperationRequest
from app.services import (
    rardar_discover_operations as discover_operations,
    rardar_news_operations as news_operations,
    rardar_today_operations as today_operations,
)
from app.services.rardar_hotspot_news import load_hotspot_news
from app.services.rardar_intelligence import (
    load_discover_project_detail,
    load_discover_snapshot,
    load_explosion_board,
    load_project_detail,
    load_selection_project_detail,
    load_selection_snapshot,
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


@router.get("/project-insights/{project_id}", response_model=SharedProjectInsightStatus)
async def shared_project_insight_read(
    project_id: str,
    response: Response,
    generation_id: str = Query(alias="generationId", min_length=1, max_length=128),
    context: Literal["trending", "historical_hot"] = "trending",
):
    from app.services.rardar_project_insights import read_project_insight

    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await read_project_insight(
            project_id, SharedProjectInsightRequest(generationId=generation_id, context=context)
        )
    except LookupError:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"}) from None
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail={"code": "project_material_invalid"}) from None


@router.post("/project-insights/{project_id}", response_model=SharedProjectInsightStatus)
async def shared_project_insight_start(
    project_id: str,
    payload: SharedProjectInsightRequest,
    request: Request,
    response: Response,
    _user=Depends(get_current_user),
):
    from app.services.rardar_project_insights import start_project_insight

    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    if not request.headers.get("authorization") and (
        request.headers.get("origin") not in settings.cors_origins
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(status_code=403, detail={"code": "project_insight_origin_rejected"})
    response.headers["Cache-Control"] = "no-store"
    try:
        return await start_project_insight(project_id, payload)
    except LookupError:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"}) from None
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail={"code": "project_material_invalid"}) from None


@router.get("/trending-today")
async def trending_today(response: Response):
    from app.services import rardar_trending

    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    try:
        return rardar_trending.today()
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail="trending_snapshot_invalid") from None


@router.get("/historical-hot")
async def historical_hot(response: Response):
    from app.services import rardar_trending

    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    try:
        return rardar_trending.history()
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail="historical_snapshot_invalid") from None


@router.get("/trending-projects/{project_id}")
async def trending_project(project_id: str, generation: str = Query(min_length=1, max_length=128)):
    from app.services import rardar_trending

    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return rardar_trending.detail(project_id, generation)
    except LookupError:
        raise HTTPException(status_code=404, detail="project_not_found") from None
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail="trending_snapshot_invalid") from None


@router.get("/historical-projects/{project_id}")
async def historical_project(project_id: str):
    from app.services import rardar_trending

    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return rardar_trending.detail(project_id, None, historical=True)
    except LookupError:
        raise HTTPException(status_code=404, detail="project_not_found") from None
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail="historical_snapshot_invalid") from None


_SERVING_CACHE_CONTROL = "private, max-age=15, stale-while-revalidate=45"


def _cache_headers(response: Response, etag: str) -> None:
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _SERVING_CACHE_CONTROL
    response.headers["Vary"] = "Accept"


def _require_active_module(module: str) -> None:
    try:
        require_module_execution(module)
    except RardarModulePaused as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code}) from None


def _not_modified(request: Request, etag: str) -> Response | None:
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": _SERVING_CACHE_CONTROL, "Vary": "Accept"},
        )
    return None


@router.get("/hotspot-news", response_model=HotspotNewsResponse)
async def hotspot_news(
    request: Request,
    response: Response,
    source: str | None = Query(default=None, min_length=1, max_length=40),
    topic: str | None = Query(default=None, min_length=1, max_length=40),
    sort: Literal["balanced", "latest"] = Query(default="balanced"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=18, alias="pageSize", ge=1, le=40),
    db: AsyncSession = Depends(get_db),
):
    """Read the last saved news refresh; GET never contacts a source or model."""
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        snapshot, etag = await load_hotspot_news(
            db,
            selected_source=source,
            selected_topic=topic,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        if str(exc) in {
            "hotspot_news_source_unknown",
            "hotspot_news_topic_unknown",
            "hotspot_news_sort_unknown",
            "hotspot_news_pagination_invalid",
        }:
            raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc
        raise
    cached = _not_modified(request, etag)
    if cached:
        return cached
    _cache_headers(response, etag)
    return snapshot


@router.get("/hotspot-news/operations")
async def news_operation_status(response: Response, _admin=Depends(get_current_admin_user)):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    return {
        "requestLimit": news_operations.request_limit(),
        "pageSize": 18,
        "latest": news_operations.latest_operation(),
    }


@router.get("/hotspot-news/operations/{operation_id}")
async def news_operation_detail(operation_id: str, response: Response, _admin=Depends(get_current_admin_user)):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    try:
        operation = news_operations.get_operation(operation_id)
    except ValueError:
        operation = None
    if operation is None:
        raise HTTPException(status_code=404, detail="Not found")
    return operation


@router.post("/hotspot-news/operations", status_code=202)
async def news_operation_start(
    payload: NewsOperationRequest,
    request: Request,
    response: Response,
    admin=Depends(get_current_admin_user),
):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    _require_active_module("news")
    # Cookie auth needs an explicit same-origin browser request. Bearer clients
    # retain the existing CLI/API authentication contract; localhost is not auth.
    if not request.headers.get("authorization"):
        origin = request.headers.get("origin")
        if origin not in settings.cors_origins or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(status_code=403, detail="news_origin_rejected")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await news_operations.start_operation(payload, user_id=admin.id)
    except (ValueError, news_operations.ProviderBudgetError):
        raise HTTPException(status_code=409, detail="news_operation_unavailable") from None


@router.get("/discover/operations")
async def discover_operation_status(response: Response, _admin=Depends(get_current_admin_user)):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    return {
        "latest": discover_operations.latest_operation(),
        "prepared": discover_operations.prepared_plan(),
        "requestLimit": discover_operations.request_limit(),
        "batchSize": discover_operations.BATCH_SIZE,
    }


@router.get("/discover/operations/{operation_id}")
async def discover_operation_detail(operation_id: str, response: Response, _admin=Depends(get_current_admin_user)):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    try:
        operation = discover_operations.get_operation(operation_id)
    except ValueError:
        operation = None
    if operation is None:
        raise HTTPException(status_code=404, detail="Not found")
    return operation


@router.post("/discover/operations/prepare")
async def discover_operation_prepare(
    payload: DiscoverPrepareRequest, request: Request, response: Response, admin=Depends(get_current_admin_user)
):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    _require_active_module("discover")
    if not request.headers.get("authorization") and (
        request.headers.get("origin") not in settings.cors_origins
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(status_code=403, detail="discover_origin_rejected")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await discover_operations.prepare_operation(payload, user_id=admin.id)
    except (ValueError, OSError, RardarArtifactError, discover_operations.ProviderBudgetError):
        raise HTTPException(status_code=409, detail="discover_source_unavailable") from None


@router.post("/discover/operations", status_code=202)
async def discover_operation_start(
    payload: DiscoverOperationRequest, request: Request, response: Response, admin=Depends(get_current_admin_user)
):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    _require_active_module("discover")
    if not request.headers.get("authorization") and (
        request.headers.get("origin") not in settings.cors_origins
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(status_code=403, detail="discover_origin_rejected")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await discover_operations.start_operation(payload, user_id=admin.id)
    except (ValueError, discover_operations.ProviderBudgetError):
        raise HTTPException(status_code=409, detail="discover_operation_unavailable") from None


@router.get("/today/operations")
async def today_operation_status(response: Response, _admin=Depends(get_current_admin_user)):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    return {
        "latest": today_operations.latest_operation(),
        "lastSuccessfulSyncAt": today_operations.last_successful_sync_at(),
    }


@router.get("/today/operations/{operation_id}")
async def today_operation_detail(operation_id: str, response: Response, _admin=Depends(get_current_admin_user)):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["Cache-Control"] = "no-store"
    try:
        operation = today_operations.get_operation(operation_id)
    except ValueError:
        operation = None
    if operation is None:
        raise HTTPException(status_code=404, detail="Not found")
    return operation


@router.post("/today/operations", status_code=202)
async def today_operation_start(
    payload: TodayOperationRequest,
    request: Request,
    response: Response,
    admin=Depends(get_current_admin_user),
):
    if not is_rardar_product() or settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    if not request.headers.get("authorization") and (
        request.headers.get("origin") not in settings.cors_origins
        or request.headers.get("sec-fetch-site") == "cross-site"
    ):
        raise HTTPException(status_code=403, detail="today_origin_rejected")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await today_operations.start_operation(payload, user_id=admin.id)
    except (ValueError, today_operations.ProviderBudgetError):
        raise HTTPException(status_code=409, detail="today_operation_unavailable") from None


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


@router.get("/discover/selection", response_model=SelectionApiResponse)
def selection_snapshot(request: Request, response: Response):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        snapshot, etag = load_selection_snapshot()
    except RardarArtifactError as exc:
        not_configured = exc.code in {
            "rardar_intelligence_not_configured",
            "rardar_intelligence_unavailable",
            "rardar_selection_not_configured",
        }
        response.status_code = 503
        return SelectionApiResponse(
            mode="shadow",
            status="not_configured" if not_configured else "invalid",
            state="not_configured" if not_configured else "invalid",
            generation=None,
            sourceObservation=None,
            sourceTodayGeneration=None,
            items=[],
            categoryCounts={},
            primaryReasonCounts={},
            candidateCount=0,
            selectedCount=0,
            publishedCount=0,
            suppressedCount=0,
            provenance={},
            code=exc.code,
        )
    cached = _not_modified(request, etag)
    if cached:
        return cached
    _cache_headers(response, etag)
    return snapshot


@router.get("/discover/selection/projects/{github_repository_id}", response_model=SelectionProjectDetail)
def selection_project_detail(
    request: Request,
    response: Response,
    github_repository_id: int = Path(gt=0),
    selection_generation: str = Query(alias="selectionGeneration", min_length=2, max_length=191),
):
    if not is_rardar_product():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        detail, etag = load_selection_project_detail(github_repository_id, selection_generation)
    except RardarArtifactError as exc:
        status_code = 404 if exc.code == "rardar_selection_project_not_found" else 503
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
    _require_active_module("discover")
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
