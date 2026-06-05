"""
Repository for AiAnalysis model operations.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select

from app.models.analysis import AiAnalysis
from app.repositories.base import BaseRepository


class AnalysisRepository(BaseRepository[AiAnalysis]):
    """AiAnalysis table CRUD + content-based lookups."""

    model = AiAnalysis

    async def get_by_content_id(self, content_id: int) -> Optional[AiAnalysis]:
        """Fetch the analysis record for a given content item."""
        stmt = select(AiAnalysis).where(AiAnalysis.content_id == content_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_enrichment_ids(self, min_score: float, limit: int) -> list[int]:
        """Return high-value analysis content IDs that still need enrichment."""
        stmt = (
            select(AiAnalysis.content_id)
            .where(
                AiAnalysis.curation_score >= min_score,
                or_(
                    AiAnalysis.enrichment_status.is_(None),
                    AiAnalysis.enrichment_status != "completed",
                ),
            )
            .order_by(AiAnalysis.curation_score.desc(), AiAnalysis.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [int(content_id) for content_id in result.scalars().all()]

    async def list_with_score_filter(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        min_creator_score: Optional[float] = None,
        min_viral_score: Optional[float] = None,
    ):
        """List analyses with optional score thresholds."""
        from sqlalchemy import func
        filters = {}
        if min_creator_score is not None:
            filters["min_creator_score"] = min_creator_score
        if min_viral_score is not None:
            filters["min_viral_score"] = min_viral_score

        stmt = select(AiAnalysis)
        count_stmt = select(func.count()).select_from(AiAnalysis)

        if min_creator_score is not None:
            stmt = stmt.where(AiAnalysis.creator_score >= min_creator_score)
            count_stmt = count_stmt.where(AiAnalysis.creator_score >= min_creator_score)
        if min_viral_score is not None:
            stmt = stmt.where(AiAnalysis.viral_score >= min_viral_score)
            count_stmt = count_stmt.where(AiAnalysis.viral_score >= min_viral_score)

        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(AiAnalysis.created_at.desc())
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.db.execute(stmt)
        items = result.scalars().all()
        return items, total
