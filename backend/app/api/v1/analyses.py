"""
AI Analysis API endpoints.
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.content import ContentStatus
from app.schemas.analysis import AiAnalysisResponse
from app.repositories.content_repo import ContentRepo
from app.repositories.analysis_repo import AnalysisRepository
from app.services.analysis import analyze_content, analyze_batch, analyze_batch_concurrent

router = APIRouter(prefix="/analyses", tags=["analyses"], dependencies=[Depends(get_current_user)])


@router.post("/content/{content_id}", response_model=AiAnalysisResponse)
async def analyze_single(
    content_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Analyze a single content item."""
    content_repo = ContentRepo(db)
    analysis_repo = AnalysisRepository(db)

    try:
        content = await content_repo.get_by_id_or_raise(content_id, "Content")
    except NotFoundError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # Check if already analyzed
    existing = await analysis_repo.get_by_content_id(content_id)
    if existing:
        return existing

    try:
        content.status = ContentStatus.ANALYZING
        await db.commit()
        content = await content_repo.get_by_id_or_raise(content_id, "Content")
        analysis = await analyze_content(content, db)
        await db.commit()
        return analysis
    except Exception as e:
        await db.rollback()
        try:
            content = await content_repo.get_by_id_or_raise(content_id, "Content")
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
    return await analyze_batch(content_ids, db)


@router.post("/pending")
async def analyze_all_pending(
    limit: int = Query(20, ge=1, le=100),
    hours: Optional[int] = Query(None, ge=1, le=720, description="Only analyze pending items collected within this many hours"),
    sync: bool = Query(False, description="Run analysis synchronously for diagnostics"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger analysis for pending content items, optionally scoped to a recent window."""
    content_repo = ContentRepo(db)
    pending = await content_repo.list_pending_for_analysis(limit=limit, hours=hours)
    ids = [item.id for item in pending]

    if not ids:
        return {
            "message": "No pending content to analyze",
            "count": 0,
            "ids": [],
            "queued_ids": [],
            "analyzed_ids": [],
            "hours": hours,
            "mode": "sync" if sync else "background",
        }

    if not sync:
        if background_tasks is None:
            background_tasks = BackgroundTasks()
        background_tasks.add_task(_run_batch_background, ids)
        return {
            "message": f"Analysis queued for {len(ids)} items in background",
            "count": len(ids),
            "ids": ids,
            "queued_ids": ids,
            "analyzed_ids": [],
            "hours": hours,
            "mode": "background",
        }

    results = await analyze_batch_concurrent(ids)
    return {"message": f"Analysis complete for {len(results)} items",
            "count": len(results),
            "ids": ids,
            "hours": hours,
            "queued_ids": [],
            "mode": "sync",
            "analyzed_ids": [a.content_id for a in results]}


@router.get("/content/{content_id}", response_model=AiAnalysisResponse)
async def get_analysis(content_id: int, db: AsyncSession = Depends(get_db)):
    """Get the AI analysis for a content item."""
    analysis_repo = AnalysisRepository(db)
    analysis = await analysis_repo.get_by_content_id(content_id)
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
    analysis_repo = AnalysisRepository(db)
    items, total = await analysis_repo.list_with_score_filter(
        page=page, page_size=page_size,
        min_creator_score=min_creator_score,
        min_viral_score=min_viral_score,
    )
    return {
        "items": [
            {
                "id": a.id, "content_id": a.content_id,
                "quality_score": a.quality_score, "hot_score": a.hot_score,
                "freshness_score": a.freshness_score, "creator_score": a.creator_score,
                "viral_score": a.viral_score, "risk_score": a.risk_score,
                "summary": a.summary, "recommended_reason": a.recommended_reason,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


async def _run_batch_background(content_ids: list[int]) -> None:
    """Run batch analysis in background."""
    await analyze_batch_concurrent(content_ids)
