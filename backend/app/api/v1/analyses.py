"""
AI Analysis API endpoints.

Endpoints:
- POST /api/v1/analyses/content/{content_id}  — analyze single content
- POST /api/v1/analyses/batch                   — analyze multiple content items
- GET  /api/v1/analyses/content/{content_id}    — get analysis for content
- GET  /api/v1/analyses                          — list all analyses
- POST /api/v1/analyses/pending                  — analyze all pending content
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.content import ContentItem, ContentStatus
from app.models.analysis import AiAnalysis
from app.schemas.analysis import AiAnalysisResponse
from app.services.analysis import analyze_content, analyze_batch

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("/content/{content_id}", response_model=AiAnalysisResponse)
async def analyze_single(
    content_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Analyze a single content item."""
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )
    content = result.scalar_one_or_none()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # Check if already analyzed
    existing = await db.execute(
        select(AiAnalysis).where(AiAnalysis.content_id == content_id)
    )
    existing_analysis = existing.scalar_one_or_none()
    if existing_analysis:
        return existing_analysis

    try:
        content.status = ContentStatus.ANALYZING
        await db.flush()

        analysis = await analyze_content(content, db)
        await db.commit()
        return analysis
    except Exception as e:
        await db.rollback()
        try:
            content.status = ContentStatus.ERROR
            await db.commit()
        except Exception:
            await db.rollback()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/batch", response_model=list[AiAnalysisResponse])
async def analyze_batch_endpoint(
    content_ids: list[int],
    db: AsyncSession = Depends(get_db),
):
    """Analyze multiple content items by IDs."""
    if not content_ids:
        raise HTTPException(status_code=400, detail="No content IDs provided")
    if len(content_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 items per batch")

    results = await analyze_batch(content_ids, db)
    return results


@router.post("/pending")
async def analyze_all_pending(
    limit: int = Query(20, ge=1, le=100),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger analysis for all pending content items."""
    result = await db.execute(
        select(ContentItem.id)
        .where(ContentItem.status == ContentStatus.PENDING)
        .order_by(ContentItem.published_at.desc())
        .limit(limit)
    )
    ids = [row[0] for row in result.all()]

    if not ids:
        return {"message": "No pending content to analyze", "count": 0}

    # Run in background for large batches
    if len(ids) > 5:
        background_tasks.add_task(_run_batch_background, ids)
        return {
            "message": f"Analysis started for {len(ids)} items in background",
            "count": len(ids),
            "ids": ids,
        }

    results = await analyze_batch(ids, db)
    return {
        "message": f"Analysis complete for {len(results)} items",
        "count": len(results),
        "analyzed_ids": [a.content_id for a in results],
    }


@router.get("/content/{content_id}", response_model=AiAnalysisResponse)
async def get_analysis(content_id: int, db: AsyncSession = Depends(get_db)):
    """Get the AI analysis for a content item."""
    result = await db.execute(
        select(AiAnalysis).where(AiAnalysis.content_id == content_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.get("")
async def list_analyses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_creator_score: Optional[float] = None,
    min_viral_score: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all analyses with optional score filters."""
    query = select(AiAnalysis)
    count_query = select(func.count()).select_from(AiAnalysis)

    if min_creator_score is not None:
        query = query.where(AiAnalysis.creator_score >= min_creator_score)
        count_query = count_query.where(AiAnalysis.creator_score >= min_creator_score)
    if min_viral_score is not None:
        query = query.where(AiAnalysis.viral_score >= min_viral_score)
        count_query = count_query.where(AiAnalysis.viral_score >= min_viral_score)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(AiAnalysis.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": a.id,
                "content_id": a.content_id,
                "quality_score": a.quality_score,
                "hot_score": a.hot_score,
                "freshness_score": a.freshness_score,
                "creator_score": a.creator_score,
                "viral_score": a.viral_score,
                "risk_score": a.risk_score,
                "summary": a.summary,
                "recommended_reason": a.recommended_reason,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _run_batch_background(content_ids: list[int]) -> None:
    """Run batch analysis in background."""
    from app.database import async_session

    async with async_session() as db:
        await analyze_batch(content_ids, db)
