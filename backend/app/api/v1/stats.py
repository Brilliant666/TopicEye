"""Dashboard statistics API endpoints — SQLAlchemy async aggregation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import (
    func,
    case,
    select,
    text,
    cast,
    Date,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stats", tags=["stats"])

# Target curation rate: top ~25-30%
# Data distribution: >=85 → 17.7%, >=80 → 44.1%, so P70 ≈ 83
TARGET_PCT = 70  # percentile rank (top 30% = P70 and above)
FALLBACK_THRESHOLD = 83  # used when not enough data to compute percentile


# ─────────────────────────────────────────────────────────────────
# Helper: compute the P70 threshold dynamically from the DB
# ─────────────────────────────────────────────────────────────────
async def _p70_threshold(db: AsyncSession, cutoff: datetime) -> float:
    """Return the P70 curation_score for items within the cutoff date range."""
    try:
        # Use raw SQL to get the 70th percentile value directly
        result = await db.execute(
            text("""
                SELECT curation_score
                FROM ai_analyses a
                JOIN content_items c ON c.id = a.content_id
                WHERE c.crawled_at >= :cutoff
                  AND c.duplicate_of IS NULL
                  AND a.curation_score > 0
                ORDER BY a.curation_score ASC
                LIMIT 1 OFFSET (
                    SELECT FLOOR(0.70 * COUNT(*) - 1)
                    FROM ai_analyses a2
                    JOIN content_items c2 ON c2.id = a2.content_id
                    WHERE c2.crawled_at >= :cutoff
                      AND c2.duplicate_of IS NULL
                      AND a2.curation_score > 0
                )
            """),
            {"cutoff": cutoff.isoformat()},
        )
        row = result.fetchone()
        if row and row[0]:
            return float(row[0])
    except Exception as e:
        logger.warning(f"Failed to compute P70 threshold: {e}")
    return FALLBACK_THRESHOLD


# ────────────────────────────────────────────────────────────────
# A. Content Overview
# ────────────────────────────────────────────────────────────────
@router.get("/overview")
async def get_overview(days: int = Query(7, ge=1, le=90)):
    """
    内容总览 KPI:
    - total: 总内容数 (in date range)
    - analyzed: 已分析数
    - curated: 精选数 (curation_score >= P70 threshold, ~top 30%)
    - today_new: 今日新增
    """
    async with async_session() as db:
        cutoff = datetime.utcnow() - timedelta(days=days)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        thr = await _p70_threshold(db, cutoff)

        # Total & analyzed & curated in date range
        row = await db.execute(
            select(
                func.count(text("content_items.id")).label("total"),
                func.count(
                    case(
                        (
                            text("ai_analyses.curation_score IS NOT NULL"),
                            text("content_items.id"),
                        )
                    )
                ).label("analyzed"),
                func.count(
                    case(
                        (
                            text(f"ai_analyses.curation_score >= {thr:.1f}"),
                            text("content_items.id"),
                        )
                    )
                ).label("curated"),
            )
            .select_from(text("content_items"))
            .outerjoin(text("ai_analyses"), text("ai_analyses.content_id = content_items.id"))
            .where(text("content_items.crawled_at >= :cutoff"), text("content_items.duplicate_of IS NULL"))
            .params(cutoff=cutoff.isoformat())
        )
        r = row.fetchone()

        # Today new
        today_row = await db.execute(
            select(func.count(text("content_items.id")))
            .select_from(text("content_items"))
            .where(
                text("content_items.crawled_at >= :today_start"),
                text("content_items.duplicate_of IS NULL"),
            )
            .params(today_start=today_start.isoformat())
        )
        today_new = today_row.scalar() or 0

        return {
            "total": r.total or 0,
            "analyzed": r.analyzed or 0,
            "curated": r.curated or 0,
            "curation_threshold": round(thr, 1),
            "today_new": today_new,
        }


# ────────────────────────────────────────────────────────────────
# B. Source Distribution
# ────────────────────────────────────────────────────────────────
@router.get("/source-distribution")
async def get_source_distribution(days: int = Query(7, ge=1, le=90)):
    """
    信源分布:
    - source_name, source_type
    - content_count, curated_count, curation_rate
    """
    async with async_session() as db:
        cutoff = datetime.utcnow() - timedelta(days=days)
        thr = await _p70_threshold(db, cutoff)

        rows = await db.execute(
            select(
                func.coalesce(text("sources.name"), "未知").label("source_name"),
                func.coalesce(func.lower(text("sources.source_type")), "unknown").label("source_type"),
                func.count(text("content_items.id")).label("content_count"),
                func.count(
                    case(
                        (
                            text(f"ai_analyses.curation_score >= {thr:.1f}"),
                            text("content_items.id"),
                        )
                    )
                ).label("curated_count"),
            )
            .select_from(text("content_items"))
            .outerjoin(text("sources"), text("sources.id = content_items.source_id"))
            .outerjoin(text("ai_analyses"), text("ai_analyses.content_id = content_items.id"))
            .where(
                text("content_items.crawled_at >= :cutoff"),
                text("content_items.duplicate_of IS NULL"),
            )
            .group_by(text("sources.id"), text("sources.name"), text("sources.source_type"))
            .having(func.count(text("content_items.id")) > 0)
            .order_by(func.count(text("content_items.id")).desc())
            .params(cutoff=cutoff.isoformat())
            .limit(20)
        )
        results = []
        for r in rows.fetchall():
            cnt = r.content_count or 0
            cur = r.curated_count or 0
            results.append({
                "source_name": r.source_name,
                "source_type": r.source_type,
                "content_count": cnt,
                "curated_count": cur,
                "curation_rate": round(cur / cnt * 100, 1) if cnt > 0 else 0,
            })
        return {"sources": results}


# ────────────────────────────────────────────────────────────────
# C. Category Distribution
# ────────────────────────────────────────────────────────────────
@router.get("/category-distribution")
async def get_category_distribution(days: int = Query(7, ge=1, le=90)):
    """
    分类分布:
    - category, content_count, avg_curation_score
    """
    async with async_session() as db:
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = await db.execute(
            select(
                func.coalesce(text("content_items.category"), "未分类").label("category"),
                func.count(text("content_items.id")).label("content_count"),
                func.round(func.avg(text("ai_analyses.curation_score")), 1).label("avg_score"),
            )
            .select_from(text("content_items"))
            .outerjoin(text("ai_analyses"), text("ai_analyses.content_id = content_items.id"))
            .where(
                text("content_items.crawled_at >= :cutoff"),
                text("content_items.duplicate_of IS NULL"),
            )
            .group_by(text("content_items.category"))
            .order_by(func.count(text("content_items.id")).desc())
            .params(cutoff=cutoff.isoformat())
        )
        results = []
        for r in rows.fetchall():
            results.append({
                "category": r.category,
                "content_count": r.content_count or 0,
                "avg_score": float(r.avg_score) if r.avg_score else 0,
            })
        return {"categories": results}


# ────────────────────────────────────────────────────────────────
# D. Daily Trend
# ────────────────────────────────────────────────────────────────
@router.get("/daily-trend")
async def get_daily_trend(days: int = Query(7, ge=1, le=90)):
    """
    时间趋势:
    - date, content_count, curated_count, analyzed_count
    """
    async with async_session() as db:
        cutoff = datetime.utcnow() - timedelta(days=days)
        thr = await _p70_threshold(db, cutoff)

        rows = await db.execute(
            select(
                func.date(text("content_items.crawled_at")).label("crawl_date"),
                func.count(text("content_items.id")).label("content_count"),
                func.count(
                    case(
                        (
                            text(f"ai_analyses.curation_score >= {thr:.1f}"),
                            text("content_items.id"),
                        )
                    )
                ).label("curated_count"),
                func.count(
                    case(
                        (
                            text("ai_analyses.id IS NOT NULL"),
                            text("content_items.id"),
                        )
                    )
                ).label("analyzed_count"),
            )
            .select_from(text("content_items"))
            .outerjoin(text("ai_analyses"), text("ai_analyses.content_id = content_items.id"))
            .where(
                text("content_items.crawled_at >= :cutoff"),
                text("content_items.duplicate_of IS NULL"),
            )
            .group_by(func.date(text("content_items.crawled_at")))
            .order_by(text("crawl_date ASC"))
            .params(cutoff=cutoff.isoformat())
        )
        results = []
        for r in rows.fetchall():
            d = r.crawl_date
            results.append({
                "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                "content_count": r.content_count or 0,
                "curated_count": r.curated_count or 0,
                "analyzed_count": r.analyzed_count or 0,
            })
        return {"trend": results}


# ────────────────────────────────────────────────────────────────
# E. Novel Platform Stats (番茄 / 七猫 / 知乎)
# ────────────────────────────────────────────────────────────────
@router.get("/novel-platforms")
async def get_novel_platform_stats():
    """
    网文雷达统计:
    - fanqie: count, last_sync
    - qimao:  count, last_sync
    - zhihu:  count, last_sync
    """
    async with async_session() as db:
        # Fanqie
        fq_row = await db.execute(
            select(
                func.count(text("fanqie_books.id")).label("cnt"),
                func.max(text("fanqie_books.crawled_at")).label("last_sync"),
            ).select_from(text("fanqie_books"))
        )
        fq = fq_row.fetchone()

        # Qimao
        qm_row = await db.execute(
            select(
                func.count(text("qimao_books.id")).label("cnt"),
                func.max(text("qimao_books.crawled_at")).label("last_sync"),
            ).select_from(text("qimao_books"))
        )
        qm = qm_row.fetchone()

        # Zhihu
        zh_row = await db.execute(
            select(
                func.count(text("zhihu_albums.id")).label("cnt"),
                func.max(text("zhihu_albums.updated_at")).label("last_sync"),
            ).select_from(text("zhihu_albums"))
        )
        zh = zh_row.fetchone()

        def _fmt(dt):
            if dt is None:
                return None
            return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

        return {
            "platforms": [
                {"name": "番茄小说", "table": "fanqie", "count": fq.cnt or 0, "last_sync": _fmt(fq.last_sync)},
                {"name": "七猫小说", "table": "qimao", "count": qm.cnt or 0, "last_sync": _fmt(qm.last_sync)},
                {"name": "知乎盐选", "table": "zhihu", "count": zh.cnt or 0, "last_sync": _fmt(zh.last_sync)},
            ]
        }


# ────────────────────────────────────────────────────────────────
# Legacy dashboard endpoint
# ────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def get_dashboard_stats(days: int = Query(7, ge=1, le=90)):
    """
    Legacy dashboard stats — delegates to duckdb_service for now.
    New code should use the granular endpoints above.
    """
    try:
        from app.services.duckdb_service import query_dashboard_stats
        return query_dashboard_stats(days=days)
    except Exception:
        pass

    async with async_session() as db:
        cutoff = datetime.utcnow() - timedelta(days=days)
        thr = await _p70_threshold(db, cutoff)

        kpi_row = await db.execute(
            select(
                func.count(text("content_items.id")).label("total_crawled"),
                func.count(
                    case(
                        (text(f"ai_analyses.curation_score >= {thr:.1f}"), text("content_items.id"))
                    )
                ).label("total_curated"),
                func.round(func.avg(text("ai_analyses.curation_score")), 1).label("avg_curation"),
                func.count(func.distinct(text("content_items.source_id"))).label("active_sources"),
            )
            .select_from(text("content_items"))
            .outerjoin(text("ai_analyses"), text("ai_analyses.content_id = content_items.id"))
            .where(text("content_items.crawled_at >= :cutoff"))
            .params(cutoff=cutoff.isoformat())
        )
        kpi = kpi_row.fetchone()

        return {
            "kpi": {
                "total_crawled": kpi.total_crawled or 0,
                "total_curated": kpi.total_curated or 0,
                "avg_curation": float(kpi.avg_curation) if kpi.avg_curation else 0,
                "active_sources": kpi.active_sources or 0,
                "curation_threshold": round(thr, 1),
            },
            "source_breakdown": [],
            "daily_trend": [],
        }
