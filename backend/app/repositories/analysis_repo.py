"""
Repository for AiAnalysis model operations.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

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
