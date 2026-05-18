from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.content import ContentItem
from app.models.analysis import AiAnalysis
from app.schemas.content import (
    ContentResponse, ContentDetailResponse, ContentListResponse,
    ContentMetricsResponse,
)

router = APIRouter(prefix="/contents", tags=["contents"])


@router.get("", response_model=ContentListResponse)
async def list_contents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|published_at|crawled_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContentItem).options(selectinload(ContentItem.analyses))
    count_query = select(func.count()).select_from(ContentItem)

    if source_type:
        query = query.where(ContentItem.source_type == source_type)
        count_query = count_query.where(ContentItem.source_type == source_type)
    if platform:
        query = query.where(ContentItem.platform == platform)
        count_query = count_query.where(ContentItem.platform == platform)
    if status:
        query = query.where(ContentItem.status == status)
        count_query = count_query.where(ContentItem.status == status)
    if category:
        query = query.where(ContentItem.category == category)
        count_query = count_query.where(ContentItem.category == category)
    if keyword:
        query = query.where(ContentItem.title.ilike(f"%{keyword}%"))
        count_query = count_query.where(ContentItem.title.ilike(f"%{keyword}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    sort_column = getattr(ContentItem, sort_by, ContentItem.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().unique().all()

    response_items = []
    for item in items:
        item_dict = ContentResponse.model_validate(item).model_dump()
        if item.analyses:
            from app.schemas.analysis import AiAnalysisResponse
            item_dict["analysis"] = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
        response_items.append(item_dict)

    return {"items": response_items, "total": total, "page": page, "page_size": page_size}


@router.get("/today-picks")
async def today_picks(
    category: Optional[str] = Query(None, description="Filter by category"),
    time_range: Optional[str] = Query(None, description="Time range: 24h, 48h, 7d"),
    db: AsyncSession = Depends(get_db),
):
    """Get today's top picks — curation_score adjusted by source weight, threshold 60.

    Tries DuckDB analytical layer first for better performance.
    Falls back to SQLite if DuckDB has not been synced yet.
    """
    from datetime import date, timedelta
    from app.models.source import Source

    # Determine time window based on time_range param
    if time_range == "24h":
        hours = 24
    elif time_range == "7d":
        hours = 168
    else:
        # Default: 48h
        hours = 48

    # ── Try DuckDB fast path ──
    try:
        from app.services.duckdb_service import query_today_picks, query_topics
        duckdb_items = query_today_picks(hours=hours)
        if duckdb_items:
            # Apply category filter if specified
            if category:
                duckdb_items = [i for i in duckdb_items if i.get("category") == category]

            topic_groups = query_topics()
            topic_map = {t["id"]: t for t in topic_groups}

            response_items = []
            for item in duckdb_items:
                # Build response in the same shape as the SQLite path
                analysis_dict = {
                    "quality_score": item.get("quality_score"),
                    "hot_score": item.get("hot_score"),
                    "freshness_score": item.get("freshness_score"),
                    "creator_score": item.get("creator_score"),
                    "viral_score": item.get("viral_score"),
                    "risk_score": item.get("risk_score"),
                    "curation_score": item.get("curation_score"),
                    "info_density": item.get("info_density"),
                    "actionability": item.get("actionability"),
                    "recommended_reason": item.get("recommended_reason"),
                    "recommendation": item.get("recommendation"),
                    "summary": item.get("ai_summary"),
                    "tags": item.get("ai_tags"),
                    "enrichment_status": item.get("enrichment_status"),
                    "enrichment": item.get("enrichment"),
                    "adjusted_curation_score": item.get("adjusted_curation_score"),
                }
                response_items.append({
                    "id": item["id"],
                    "title": item["title"],
                    "url": item["url"],
                    "source_id": item.get("source_id"),
                    "source_name": item.get("source_name"),
                    "source_type": item.get("source_type"),
                    "platform": item.get("platform"),
                    "author": item.get("author"),
                    "published_at": item.get("published_at"),
                    "crawled_at": item.get("crawled_at"),
                    "summary": item.get("summary"),
                    "category": item.get("category"),
                    "tags": item.get("tags"),
                    "topic_id": item.get("topic_id"),
                    "duplicate_of": item.get("duplicate_of"),
                    "similarity_score": item.get("similarity_score"),
                    "analysis": analysis_dict,
                })

            deduped = [i for i in response_items if not i.get("duplicate_of")]
            dup_count = len(response_items) - len(deduped)

            return {
                "items": deduped,
                "total": len(deduped),
                "duplicates_hidden": dup_count,
                "topics": list(topic_map.values()),
                "page": 1,
                "page_size": len(deduped),
            }
    except Exception:
        pass  # Fall through to SQLite path

    # ── SQLite fallback path ──
    fallback_start = datetime.combine(date.today() - timedelta(hours=hours), datetime.min.time())

    query = (
        select(ContentItem)
        .options(
            selectinload(ContentItem.analyses),
            selectinload(ContentItem.source),
        )
        .join(AiAnalysis, AiAnalysis.content_id == ContentItem.id)
        .where(ContentItem.crawled_at >= fallback_start)
        .where(AiAnalysis.risk_score <= 70)
    )
    if category:
        query = query.where(ContentItem.category == category)
    result = await db.execute(query)
    items = result.scalars().unique().all()

    CURATION_THRESHOLD = 60
    WEIGHT_BONUS = 8

    scored_items = []
    for item in items:
        if not item.analyses:
            continue
        a = item.analyses[-1]
        cs = a.curation_score or 0
        src_weight = item.source.weight if item.source else 3
        adjusted = cs + (src_weight - 3) * WEIGHT_BONUS
        if cs == 0:
            combined = (a.creator_score or 0) + (a.viral_score or 0)
            adjusted = (combined / 2) + (src_weight - 3) * WEIGHT_BONUS
        if adjusted >= CURATION_THRESHOLD:
            scored_items.append((item, adjusted))

    scored_items.sort(key=lambda x: x[1], reverse=True)

    response_items = []
    for item, adj_score in scored_items:
        item_dict = ContentResponse.model_validate(item).model_dump()
        if item.analyses:
            from app.schemas.analysis import AiAnalysisResponse
            analysis_dict = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
            analysis_dict["adjusted_curation_score"] = round(adj_score, 1)
            item_dict["analysis"] = analysis_dict
        item_dict["topic_id"] = item.topic_id
        item_dict["duplicate_of"] = item.duplicate_of
        response_items.append(item_dict)

    from app.models.topic import TopicGroup
    topic_result = await db.execute(
        select(TopicGroup).order_by(TopicGroup.best_score.desc())
    )
    topic_groups = topic_result.scalars().all()
    topic_map = {t.id: {"id": t.id, "name": t.name, "summary": t.summary, "keywords": t.keywords, "best_score": t.best_score} for t in topic_groups}

    deduped = [i for i in response_items if not i.get("duplicate_of")]
    dup_count = len(response_items) - len(deduped)

    return {
        "items": deduped,
        "total": len(deduped),
        "duplicates_hidden": dup_count,
        "topics": list(topic_map.values()),
        "page": 1,
        "page_size": len(deduped),
    }


@router.get("/favorites/list", response_model=ContentListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get all favorited content items."""
    count_query = select(func.count()).select_from(ContentItem).where(ContentItem.is_favorited == True)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = (
        select(ContentItem)
        .options(selectinload(ContentItem.analyses))
        .where(ContentItem.is_favorited == True)
        .order_by(ContentItem.updated_at.desc())
    )
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().unique().all()

    response_items = []
    for item in items:
        item_dict = ContentResponse.model_validate(item).model_dump()
        if item.analyses:
            from app.schemas.analysis import AiAnalysisResponse
            item_dict["analysis"] = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
        response_items.append(item_dict)

    return {"items": response_items, "total": total, "page": page, "page_size": page_size}


# NOTE: /{content_id}/enrich must be defined BEFORE /{content_id}
# so FastAPI matches the static "enrich" path first.
@router.get("/{content_id}/enrich")
async def get_enrichment(
    content_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get or trigger Round-2 enrichment for a content item.

    If enrichment_status == 'completed', returns cached result.
    If 'pending' or 'error', re-runs enrichment.
    """
    from app.services.enricher import enrich_content

    result = await db.execute(
        select(AiAnalysis).where(AiAnalysis.content_id == content_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found for this content")

    if analysis.enrichment_status == "completed" and analysis.enrichment:
        return {
            "content_id": content_id,
            "status": "completed",
            "enrichment": analysis.enrichment,
        }

    try:
        data = await enrich_content(content_id, db)
        analysis.enrichment = data
        analysis.enrichment_status = "completed"
        await db.commit()
        return {"content_id": content_id, "status": "completed", "enrichment": data}
    except Exception as e:
        analysis.enrichment_status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {e}")


@router.post("/enrich-batch")
async def enrich_top_items(
    min_score: float = Query(70.0, ge=0, le=100),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Batch-enrich top curated items (scheduler-friendly, call nightly)."""
    from app.services.enricher import enrich_batch

    result = await db.execute(
        select(AiAnalysis.content_id)
        .where(
            AiAnalysis.curation_score >= min_score,
            (AiAnalysis.enrichment_status.in_(["pending", "error"])) | (AiAnalysis.enrichment_status.is_(None)),
        )
        .order_by(AiAnalysis.curation_score.desc())
        .limit(limit)
    )
    ids = [r[0] for r in result.all()]
    if not ids:
        return {"message": "No items need enrichment", "processed": []}

    results = await enrich_batch(ids, db)
    return {"processed": results}


@router.get("/{content_id}", response_model=ContentDetailResponse)
async def get_content(content_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContentItem)
        .options(selectinload(ContentItem.metrics))
        .options(selectinload(ContentItem.analyses))
        .where(ContentItem.id == content_id)
    )
    content = result.scalar_one_or_none()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    response = ContentDetailResponse.model_validate(content)
    if content.analyses:
        from app.schemas.analysis import AiAnalysisResponse
        response = response.model_copy(update={
            "analysis": AiAnalysisResponse.model_validate(content.analyses[-1])
        })
    return content


@router.post("/{content_id}/favorite")
async def toggle_favorite(content_id: int, db: AsyncSession = Depends(get_db)):
    """Toggle favorite status for a content item."""
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )
    content = result.scalar_one_or_none()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    content.is_favorited = not content.is_favorited
    content.updated_at = datetime.utcnow()
    await db.flush()
    return {"is_favorited": content.is_favorited}
