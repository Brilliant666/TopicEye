"""
Repository for DailyReport — daily briefing queries.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from sqlalchemy import select

from app.models.daily_report import DailyReport
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DailyReportRepository(BaseRepository[DailyReport]):
    """DailyReport repository with date-based lookups."""

    model = DailyReport

    async def get_by_date(self, report_date: str) -> Optional[DailyReport]:
        """Fetch a single report by its date string (YYYY-MM-DD)."""
        stmt = select(self.model).where(self.model.report_date == report_date)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest(self, limit: int = 7) -> Sequence[DailyReport]:
        """Return the most recent reports, newest first."""
        stmt = (
            select(self.model)
            .order_by(self.model.report_date.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
