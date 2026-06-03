"""
Trend tracking API endpoints.

Endpoints:
- POST /api/v1/trends/snapshot  — trigger daily snapshot
- GET  /api/v1/trends/topics    — topic trend curves (last N days)
- GET  /api/v1/trends/keywords  — keyword word cloud (last N days)

Read queries use DuckDB when available, falling back to SQLite.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Query
from typing import Optional

from app.core.database import async_session
from app.services.trends import snapshot_daily_trends, get_topic_trends, get_keyword_cloud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trends", tags=["trends"])


@router.post("/snapshot")
async def trigger_snapshot(
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
):
    """Manually trigger a trend snapshot for a given date."""
    td = date.fromisoformat(target_date) if target_date else None
    async with async_session() as db:
        result = await snapshot_daily_trends(db, td)
        await db.commit()
    return {"status": "ok", **result}


@router.get("/topics")
async def topic_trends(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
):
    """Get topic trend data for charts. Uses DuckDB when synced."""
    # ── Try DuckDB fast path ──
    try:
        from app.services.duckdb_service import query_trend_topics
        trends = query_trend_topics(days=days)
        if trends:
            return {"days": days, "trends": trends}
    except Exception:
        pass  # Fall through to SQLite

    # ── SQLite fallback ──
    async with async_session() as db:
        trends = await get_topic_trends(db, days=days)
    return {"days": days, "trends": trends}


@router.get("/keywords")
async def keyword_cloud(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=10, le=200),
):
    """Get keyword frequency for word cloud visualization. Uses DuckDB when synced."""
    # ── Try DuckDB fast path ──
    try:
        from app.services.duckdb_service import query_keyword_cloud
        keywords = query_keyword_cloud(days=days, limit=limit)
        if keywords:
            return {"days": days, "keywords": keywords}
    except Exception:
        pass  # Fall through to SQLite

    # ── SQLite fallback ──
    async with async_session() as db:
        keywords = await get_keyword_cloud(db, days=days, limit=limit)
    return {"days": days, "keywords": keywords}
