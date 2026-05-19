"""Content API endpoints — delegates all DB work to repositories."""
from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.repositories.content_repo import ContentRepo
from app.repositories.analysis_repo import AnalysisRepository
from app.schemas.content import ContentResponse, ContentDetailResponse, ContentListResponse
from app.schemas.analysis import AiAnalysisResponse

router = APIRouter(prefix="/contents", tags=["contents"])

# Large batch size for scoring — enough for diversity penalty to work well
_SCORING_BATCH_SIZE = 500


def _with_analysis(item) -> dict:
    d = ContentResponse.model_validate(item).model_dump()
    if item.analyses:
        d["analysis"] = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
    return d


@router.get("")
async def list_contents(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = None, platform: Optional[str] = None,
    status: Optional[str] = None, category: Optional[str] = None,
    keyword: Optional[str] = None, source_id: Optional[int] = None,
    hours: Optional[int] = Query(None, description="Time range in hours, e.g. 24, 48, 168"),
    sort_by: str = Query("created_at",
                          pattern=r"^(created_at|published_at|crawled_at|curation_score|low_follower_viral)$"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.ignored_repo import IgnoredRepo
    from app.models.content import ContentItem
    from app.models.analysis import AiAnalysis
    from app.services.scoring_engine import ScoringInput, score_items
    from datetime import timedelta

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

    # ── Curation-score ranking path ────────────────────────────────────
    if sort_by == "curation_score":
        repo = ContentRepo(db)
        scored_items, total = await repo.list_for_scoring(
            filters=filters,
            exclude_ids=ignored_ids,
            time_cutoff=time_cutoff,
            limit=_SCORING_BATCH_SIZE,
        )

        if not scored_items:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # Build scoring inputs
        scoring_inputs: list[ScoringInput] = []
        item_map: dict[int, ContentItem] = {}
        for item in scored_items:
            if not item.analyses:
                continue
            a = item.analyses[-1]
            src_w = item.source.weight if item.source else 3
            si = ScoringInput(
                content_id=item.id,
                title=item.title,
                source_id=item.source_id,
                source_name=item.source_name,
                published_at=item.published_at,
                crawled_at=item.crawled_at,
                curation_score=a.curation_score or 0,
                info_density=a.info_density or 50,
                actionability=a.actionability or 50,
                source_weight=a.source_weight or 50,
                creator_score=a.creator_score or 0,
                viral_score=a.viral_score or 0,
                freshness_score=a.freshness_score or 0,
                quality_score=a.quality_score or 0,
                hot_score=a.hot_score or 0,
                risk_score=a.risk_score or 0,
                source_weight_db=src_w,
            )
            scoring_inputs.append(si)
            item_map[item.id] = item

        if not scoring_inputs:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # Run full scoring pipeline (risk filter → 6-dim weighted → time decay → diversity)
        scored = score_items(scoring_inputs)

        # Paginate scored results
        page_offset = (page - 1) * page_size
        page_items = scored[page_offset:page_offset + page_size]

        result_items = []
        for breakdown, si in page_items:
            item = item_map.get(si.content_id)
            if not item:
                continue
            d = _with_analysis(item)
            # Attach scoring engine output to analysis dict
            if "analysis" in d and d["analysis"]:
                d["analysis"]["adjusted_curation_score"] = breakdown.final_score
                d["analysis"]["score_breakdown"] = breakdown.to_dict()
            result_items.append(d)

        # sort_order desc is already guaranteed by score_items (descending)
        if sort_order == "asc" and result_items:
            result_items.reverse()

        return {
            "items": result_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── Low-follower viral discovery path ────────────────────────────────
    if sort_by == "low_follower_viral":
        from app.services.scoring_engine import score_low_follower_viral

        repo = ContentRepo(db)
        scored_items, total = await repo.list_for_scoring(
            filters=filters,
            exclude_ids=ignored_ids,
            time_cutoff=time_cutoff,
            limit=_SCORING_BATCH_SIZE,
        )

        if not scored_items:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        scoring_inputs: list[ScoringInput] = []
        item_map: dict[int, ContentItem] = {}
        for item in scored_items:
            if not item.analyses:
                continue
            a = item.analyses[-1]
            src_w = item.source.weight if item.source else 3
            si = ScoringInput(
                content_id=item.id,
                title=item.title,
                source_id=item.source_id,
                source_name=item.source_name,
                published_at=item.published_at,
                crawled_at=item.crawled_at,
                curation_score=a.curation_score or 0,
                info_density=a.info_density or 50,
                actionability=a.actionability or 50,
                source_weight=a.source_weight or 50,
                creator_score=a.creator_score or 0,
                viral_score=a.viral_score or 0,
                freshness_score=a.freshness_score or 0,
                quality_score=a.quality_score or 0,
                hot_score=a.hot_score or 0,
                risk_score=a.risk_score or 0,
                source_weight_db=src_w,
            )
            scoring_inputs.append(si)
            item_map[item.id] = item

        if not scoring_inputs:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # Run LFV scoring pipeline
        scored = score_low_follower_viral(scoring_inputs)

        page_offset = (page - 1) * page_size
        page_items = scored[page_offset:page_offset + page_size]

        result_items = []
        for breakdown, si in page_items:
            item = item_map.get(si.content_id)
            if not item:
                continue
            d = _with_analysis(item)
            if "analysis" in d and d["analysis"]:
                d["analysis"]["adjusted_curation_score"] = breakdown.final_score
                d["analysis"]["score_breakdown"] = breakdown.to_dict()
            result_items.append(d)

        return {
            "items": result_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── Standard SQL sort path ─────────────────────────────────────────
    repo = ContentRepo(db)
    items, total = await repo.list_paginated_with_analyses(
        page=page, page_size=page_size,
        filters=filters or None, sort_by=sort_by, sort_order=sort_order,
        exclude_ids=ignored_ids, time_cutoff=time_cutoff)
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
    repo = ContentRepo(db)
    content = await repo.get_by_id(content_id)
    if not content:
        raise HTTPException(404, "Content not found")
    content.is_favorited = not content.is_favorited
    content.updated_at = datetime.utcnow()
    await db.flush()
    return {"is_favorited": content.is_favorited}


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
    return {"content_id": content_id, "ignored": True, "reason": ignored.reason}


@router.delete("/{content_id}/ignore")
async def unignore_content(content_id: int, db: AsyncSession = Depends(get_db)):
    """Remove ignore flag from a content item."""
    from app.repositories.ignored_repo import IgnoredRepo
    removed = await IgnoredRepo(db).unignore(content_id)
    return {"content_id": content_id, "ignored": False, "removed": removed}
