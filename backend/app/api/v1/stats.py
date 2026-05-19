"""Dashboard statistics API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.duckdb_service import query_dashboard_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/dashboard")
async def get_dashboard_stats(days: int = Query(7, ge=1, le=90)):
    """
    Dashboard statistics for the last N days.

    Returns:
    - kpi: 4 key performance indicators
    - source_breakdown: per-source content/curated count
    - daily_trend: day-by-day content volume + avg curation score
    """
    return query_dashboard_stats(days=days)
