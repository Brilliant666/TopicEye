"""Content API endpoints — delegates all DB work to repositories."""
from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.content_repo import ContentRepo
from app.repositories.analysis_repo import AnalysisRepository
from app.schemas.content import ContentResponse, ContentDetailResponse, ContentListResponse
from app.schemas.analysis import AiAnalysisResponse

router = APIRouter(prefix="/contents", tags=["contents"])


def _with_analysis(item) -> dict:
    d = ContentResponse.model_validate(item).model_dump()
    if item.analyses:
        d["analysis"] = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
    return d


@router.get("", response_model=ContentListResponse)
async def list_contents(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None, platform: Optional[str] = None,
    status: Optional[str] = None, category: Optional[str] = None,
    keyword: Optional[str] = None,
    sort_by: str = Query("created_at", pattern=r"^(created_at|published_at|crawled_at)$"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    repo = ContentRepo(db)
    filters = {k: v for k, v in {
        "source_type": source_type, "platform": platform,
        "status": status, "category": category,
        "title": f"%{keyword}%" if keyword else None,
    }.items() if v is not None}
    items, total = await repo.list_paginated_with_analyses(
        page=page, page_size=page_size,
        filters=filters or None, sort_by=sort_by, sort_order=sort_order)
    return {"items": [_with_analysis(i) for i in items],
            "total": total, "page": page, "page_size": page_size}


@router.get("/today-picks")
async def today_picks(
    category: Optional[str] = Query(None, description="Filter by category"),
    time_range: Optional[str] = Query(None, description="Time range: 24h, 48h, 7d"),
    db: AsyncSession = Depends(get_db),
):
    """Top picks — curation_score adjusted by source weight, threshold 60."""
    from app.services.today_picks import build_today_picks
    return await build_today_picks(db, category=category,
                                   hours={"24h": 24, "7d": 168}.get(time_range or "", 48))


@router.get("/favorites/list", response_model=ContentListResponse)
async def list_favorites(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await ContentRepo(db).list_favorites(page=page, page_size=page_size)
    return {"items": [_with_analysis(i) for i in items],
            "total": total, "page": page, "page_size": page_size}


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
        return {"content_id": content_id, "status": "completed", "enrichment": data}
    except Exception as e:
        analysis.enrichment_status = "error"
        await db.flush()
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


@router.get("/{content_id}", response_model=ContentDetailResponse)
async def get_content(content_id: int, db: AsyncSession = Depends(get_db)):
    content = await ContentRepo(db).get_detail(content_id)
    if not content:
        raise HTTPException(404, "Content not found")
    resp = ContentDetailResponse.model_validate(content)
    if content.analyses:
        resp = resp.model_copy(update={
            "analysis": AiAnalysisResponse.model_validate(content.analyses[-1])})
    return content


@router.post("/{content_id}/favorite")
async def toggle_favorite(content_id: int, db: AsyncSession = Depends(get_db)):
    """Toggle favorite status for a content item."""
    repo = ContentRepo(db)
    content = await repo.get_by_id(content_id)
    if not content:
        raise HTTPException(404, "Content not found")
    content.is_favorited = not content.is_favorited
    content.updated_at = datetime.utcnow()
    await db.flush()
    return {"is_favorited": content.is_favorited}
