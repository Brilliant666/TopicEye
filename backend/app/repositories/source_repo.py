"""
Repository for Source model operations.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select

from app.models.source import Source, SourceStatus
from app.repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    """Source table CRUD + enabled-sources query."""

    model = Source

    async def get_enabled_sources(self) -> Sequence[Source]:
        """Return syncable sources in the user-managed order."""
        stmt = (
            select(Source)
            .where(
                Source.enabled.is_(True),
                Source.status != SourceStatus.DISABLED,
            )
            .order_by(Source.sort_order.asc(), Source.id.asc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
