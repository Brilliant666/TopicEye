"""Content API endpoints — delegates all DB work to repositories."""
from __future__ import annotations
from typing import Optional, Set
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db
from app.core.config import settings
from app.core.sqlite_retry import retry_sqlite_locked, is_sqlite_locked
from app.models.content import ContentItem
from app.repositories.content_repo import ContentRepo
from app.repositories.favorite_repo import FavoriteRepo
from app.repositories.analysis_repo import AnalysisRepository
from app.schemas.content import ContentResponse, ContentListResponse
from app.schemas.analysis import AiAnalysisResponse
from app.services.content_list_cache import (
    ContentListCacheParams,
    get_cached_content_list,
    set_cached_content_list,
)
from app.services.content_read_cache import invalidate_content_read_caches
from app.services.content_serialization import content_with_latest_analysis
from app.services.favorite_cache import invalidate_favorite_cache
from app.services.json_cache import get_cached_json, invalidate_json_cache, set_cached_json
from app.services.today_picks_cache import TodayPicksCacheParams, get_cached_today_picks, set_cached_today_picks

router = APIRouter(prefix="/contents", tags=["contents"])

# Large batch size for scoring — enough for diversity penalty to work well
_SCORING_BATCH_SIZE = 500
_TREND_SOURCE_TYPES = {"DouyinHot"}


def _empty_list_response(page: int, page_size: int) -> dict:
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


async def _score_content_page(
    db: AsyncSession,
    *,
    filters: dict,
    ignored_ids: list[int],
    time_cutoff: Optional[datetime],
    exclude_source_types: Optional[Set[str]],
    page: int,
    page_size: int,
    score_fn,
    sort_order: str = "desc",
) -> dict:
    from app.services.scoring_inputs import build_scoring_inputs

    scored_items, total = await ContentRepo(db).list_for_scoring(
        filters=filters,
        exclude_ids=ignored_ids,
        exclude_source_types=exclude_source_types,
        time_cutoff=time_cutoff,
        limit=_SCORING_BATCH_SIZE,
    )
    if not scored_items:
        return _empty_list_response(page, page_size)

    scoring_inputs, item_map, _ = await build_scoring_inputs(db, scored_items)
    if not scoring_inputs:
        return _empty_list_response(page, page_size)

    scored = score_fn(scoring_inputs)
    page_offset = (page - 1) * page_size
    page_items = scored[page_offset:page_offset + page_size]
    result_items = [_with_scoring_breakdown(item_map, breakdown, scoring_input) for breakdown, scoring_input in page_items]
    result_items = [item for item in result_items if item]

    if sort_order == "asc" and result_items:
        result_items.reverse()

    return {
        "items": result_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _with_scoring_breakdown(item_map: dict, breakdown, scoring_input) -> Optional[dict]:
    item = item_map.get(scoring_input.content_id)
    if not item:
        return None

    data = content_with_latest_analysis(item)
    if data.get("analysis"):
        data["analysis"]["adjusted_curation_score"] = breakdown.final_score
        data["analysis"]["score_breakdown"] = breakdown.to_dict()
    return data


@router.get("")
async def list_contents(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    source_type: Optional[str] = None, platform: Optional[str] = None,
    status: Optional[str] = None, category: Optional[str] = None,
    keyword: Optional[str] = None, source_id: Optional[int] = None,
    include_trend_sources: bool = Query(False, description="Include榜单/趋势源 such as DouyinHot"),
    hours: Optional[int] = Query(None, description="Time range in hours, e.g. 24, 48, 168"),
    sort_by: str = Query("created_at",
                          pattern=r"^(created_at|published_at|crawled_at|curation_score|low_follower_viral)$"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
):
    from app.repositories.ignored_repo import IgnoredRepo
    from datetime import timedelta

    cache_params = ContentListCacheParams(
        page=page,
        page_size=page_size,
        source_type=source_type,
        platform=platform,
        status=status,
        category=category,
        keyword=keyword,
        source_id=source_id,
        include_trend_sources=include_trend_sources,
        hours=hours,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    if cache_params.cacheable:
        cached = get_cached_content_list(cache_params, ttl_seconds=settings.READ_CACHE_TTL_SECONDS)
        if cached:
            content, age_seconds = cached
            return Response(
                content=content,
                media_type="application/json",
                headers={"X-Content-List-Cache": f"HIT; age={age_seconds:.3f}s"},
            )

    async with async_session() as db:
        filters = {k: v for k, v in {
            "source_type": source_type, "platform": platform,
            "status": status, "category": category,
            "source_id": source_id,
            "title": f"%{keyword}%" if keyword else None,
        }.items() if v is not None}

        time_cutoff = None
        if hours:
            time_cutoff = datetime.utcnow() - timedelta(hours=hours)

        ignored_ids = await IgnoredRepo(db).list_ignored_ids()
        exclude_source_types = None if include_trend_sources else _TREND_SOURCE_TYPES

        # ── Curation-score ranking path ────────────────────────────────────
        if sort_by == "curation_score":
            from app.services.scoring_engine import score_items

            return await _score_content_page(
                db,
                filters=filters,
                ignored_ids=ignored_ids,
                time_cutoff=time_cutoff,
                exclude_source_types=exclude_source_types,
                page=page,
                page_size=page_size,
                score_fn=score_items,
                sort_order=sort_order,
            )

        # ── Low-follower viral discovery path ────────────────────────────────
        if sort_by == "low_follower_viral":
            from app.services.scoring_engine import score_low_follower_viral

            return await _score_content_page(
                db,
                filters=filters,
                ignored_ids=ignored_ids,
                time_cutoff=time_cutoff,
                exclude_source_types=exclude_source_types,
                page=page,
                page_size=page_size,
                score_fn=score_low_follower_viral,
            )

        # ── Standard SQL sort path ─────────────────────────────────────────
        repo = ContentRepo(db)
        items, total = await repo.list_paginated_with_analyses(
            page=page, page_size=page_size,
            filters=filters or None, sort_by=sort_by, sort_order=sort_order,
            exclude_ids=ignored_ids, exclude_source_types=exclude_source_types, time_cutoff=time_cutoff)
        payload = {"items": [content_with_latest_analysis(i) for i in items],
                   "total": total, "page": page, "page_size": page_size}
        if cache_params.cacheable:
            content = set_cached_content_list(cache_params, payload)
            return Response(
                content=content,
                media_type="application/json",
                headers={"X-Content-List-Cache": "MISS"},
            )
        return payload


@router.get("/today-picks")
async def today_picks(
    category: Optional[str] = Query(None, description="Filter by category"),
    time_range: Optional[str] = Query(None, description="Time range: 24h, 48h, 7d"),
):
    """Top picks — curation_score adjusted by source weight, threshold 60."""
    from app.services.today_picks import build_today_picks

    params = TodayPicksCacheParams(
        category=category,
        hours={"24h": 24, "7d": 168}.get(time_range or "", 48),
    )
    cached = get_cached_today_picks(params, ttl_seconds=settings.READ_CACHE_TTL_SECONDS)
    if cached:
        content, age_seconds = cached
        return Response(
            content=content,
            media_type="application/json",
            headers={"X-Today-Picks-Cache": f"HIT; age={age_seconds:.3f}s"},
        )

    async with async_session() as db:
        payload = await build_today_picks(db, category=category, hours=params.hours)
        content = set_cached_today_picks(params, payload)
        return Response(
            content=content,
            media_type="application/json",
            headers={"X-Today-Picks-Cache": "MISS"},
        )


@router.get("/scoring-flow")
async def scoring_flow(
    hours: int = Query(48, ge=1, le=720),
    limit: int = Query(120, ge=20, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Return a read-only explanation payload for the content scoring funnel."""
    from app.services.scoring_flow import build_scoring_flow_payload, get_cached_scoring_flow_json

    cached = get_cached_scoring_flow_json(hours=hours, limit=limit)
    if cached:
        content, age_seconds = cached
        return Response(
            content=content,
            media_type="application/json",
            headers={"X-Scoring-Flow-Cache": f"HIT; age={age_seconds:.3f}s"},
        )

    return await build_scoring_flow_payload(db, hours=hours, limit=limit)


@router.get("/favorites/list", response_model=ContentListResponse)
async def list_favorites(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"contents:favorites:list:{page}:{page_size}"
    cached = get_cached_json(cache_key, ttl_seconds=settings.READ_CACHE_TTL_SECONDS)
    if cached:
        content, age_seconds = cached
        return Response(
            content=content,
            media_type="application/json",
            headers={"X-Content-Favorites-Cache": f"HIT; age={age_seconds:.3f}s"},
        )

    items, total = await ContentRepo(db).list_favorites(page=page, page_size=page_size)
    payload = {"items": [content_with_latest_analysis(i) for i in items],
               "total": total, "page": page, "page_size": page_size}
    content = set_cached_json(cache_key, payload)
    return Response(
        content=content,
        media_type="application/json",
        headers={"X-Content-Favorites-Cache": "MISS"},
    )


@router.get("/{content_id}/enrich")
async def get_enrichment(content_id: int, db: AsyncSession = Depends(get_db)):
    """Get or trigger Round-2 enrichment for a content item."""
    from app.services.enricher import enrich_content
    analysis = await AnalysisRepository(db).get_by_content_id(content_id)
    if not analysis:
        raise HTTPException(404, "No analysis found for this content")
    if analysis.enrichment_status == "completed" and analysis.enrichment:
        return {"content_id": content_id, "status": "completed", "enrichment": analysis.enrichment}
    try:
        data = await enrich_content(content_id, db)
        analysis.enrichment, analysis.enrichment_status = data, "completed"
        await db.flush()
        invalidate_content_read_caches()
        return {"content_id": content_id, "status": "completed", "enrichment": data}
    except Exception as e:
        analysis.enrichment_status = "error"
        await db.flush()
        invalidate_content_read_caches()
        raise HTTPException(500, f"Enrichment failed: {e}")


@router.post("/enrich-batch")
async def enrich_top_items(
    min_score: float = Query(70.0, ge=0, le=100),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Batch-enrich top curated items (scheduler-friendly)."""
    from app.services.enricher import enrich_batch
    ids = await AnalysisRepository(db).get_pending_enrichment_ids(min_score, limit)
    if not ids:
        return {"message": "No items need enrichment", "processed": []}
    return {"processed": await enrich_batch(ids, db)}


@router.get("/{content_id}")
async def get_content(content_id: int, db: AsyncSession = Depends(get_db)):
    content = await ContentRepo(db).get_detail(content_id)
    if not content:
        raise HTTPException(404, "Content not found")
    d = ContentResponse.model_validate(content).model_dump()
    if content.analyses:
        a = content.analyses[-1]
        a_dict = AiAnalysisResponse.model_validate(a).model_dump()
        # Include curation detail fields
        a_dict["info_density"] = a.info_density
        a_dict["actionability"] = a.actionability
        a_dict["source_weight"] = a.source_weight
        a_dict["curation_score"] = a.curation_score
        a_dict["recommendation"] = a.recommendation
        # Include enrichment if available
        if a.enrichment_status == "completed" and a.enrichment:
            a_dict["enrichment"] = a.enrichment
            a_dict["enrichment_status"] = a.enrichment_status
        d["analysis"] = a_dict
    if content.metrics:
        from app.schemas.content import ContentMetricsResponse
        d["metrics"] = [ContentMetricsResponse.model_validate(m).model_dump() for m in content.metrics]
    return d


@router.post("/{content_id}/favorite")
async def toggle_favorite(content_id: int, db: AsyncSession = Depends(get_db)):
    """Toggle favorite status for a content item."""
    result = await db.execute(select(ContentItem.is_favorited).where(ContentItem.id == content_id))
    current = result.scalar_one_or_none()
    if current is None:
        raise HTTPException(404, "Content not found")

    next_value = not bool(current)

    async def _write() -> None:
        await db.execute(
            update(ContentItem)
            .where(ContentItem.id == content_id)
            .values(is_favorited=next_value, updated_at=datetime.utcnow())
        )
        favorite_repo = FavoriteRepo(db)
        if next_value:
            await favorite_repo.create_from_content(content_id)
        else:
            await favorite_repo.remove_by_content(content_id)
        invalidate_favorite_cache()
        invalidate_content_read_caches()
        invalidate_json_cache("contents:favorites:")
        await db.flush()

    restore_busy_timeout = False
    try:
        if settings.DATABASE_URL.startswith("sqlite"):
            await db.execute(text("PRAGMA busy_timeout=500"))
            restore_busy_timeout = True
        await retry_sqlite_locked(_write, attempts=3, base_delay=0.1, on_retry=db.rollback)
    except OperationalError as exc:
        await db.rollback()
        if is_sqlite_locked(exc):
            raise HTTPException(status_code=503, detail="数据库繁忙，请稍后重试")
        raise
    finally:
        if restore_busy_timeout:
            try:
                await db.execute(text("PRAGMA busy_timeout=30000"))
            except Exception:
                await db.rollback()
    return {"is_favorited": next_value}


@router.post("/{content_id}/ignore")
async def ignore_content(
    content_id: int,
    reason: str = Query("not_interested", description="Ignore reason: not_interested, seen, irrelevant"),
    db: AsyncSession = Depends(get_db),
):
    """Mark a content item as ignored (won't appear in feeds)."""
    from app.repositories.ignored_repo import IgnoredRepo
    content = await ContentRepo(db).get_by_id(content_id)
    if not content:
        raise HTTPException(404, "Content not found")
    ignored = await IgnoredRepo(db).ignore(content_id, reason=reason)
    invalidate_content_read_caches()
    return {"content_id": content_id, "ignored": True, "reason": ignored.reason}


@router.delete("/{content_id}/ignore")
async def unignore_content(content_id: int, db: AsyncSession = Depends(get_db)):
    """Remove ignore flag from a content item."""
    from app.repositories.ignored_repo import IgnoredRepo
    removed = await IgnoredRepo(db).unignore(content_id)
    invalidate_content_read_caches()
    return {"content_id": content_id, "ignored": False, "removed": removed}
