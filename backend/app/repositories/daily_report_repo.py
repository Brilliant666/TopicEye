"""
Repository for DailyReport — daily briefing queries.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

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

    async def get_dates_with_reports(self) -> List[Dict[str, Optional[str]]]:
        """Return list of {report_date, weekday, takeaway, status} for all reports, newest first."""
        stmt = (
            select(
                self.model.report_date,
                self.model.weekday,
                self.model.takeaway,
                self.model.status,
            )
            .order_by(self.model.report_date.desc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        return [
            {
                "report_date": row[0],
                "weekday": row[1],
                "takeaway": row[2][:60] if row[2] else None,
                "status": row[3],
            }
            for row in rows
        ]
