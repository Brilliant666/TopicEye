"""
DuckDB analytics layer for TopicEye.

Architecture:
    DuckDB connects in-memory and ATTACHes the SQLite file (READ_ONLY).
    All analytical queries run directly against the attached SQLite tables.
    Zero sync, zero redundancy — data is always fresh.

    SQLite: OLTP source of truth (all writes go here).
    DuckDB: OLAP layer (reads only, for analytical/aggregation queries).
    Fallback: if DuckDB sqlite extension fails, callers fall back to SQLAlchemy.

Usage:
    from app.services.duckdb_service import DuckDBAnalytics
    analytics = DuckDBAnalytics()
    picks = analytics.query_today_picks(hours=48)
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ── SQLite path resolution ─────────────────────────────────────────────

def _sqlite_path() -> str:
    """Resolve the SQLite database file path from DATABASE_URL."""
    url = settings.DATABASE_URL
    if ":///" in url:
        path = url.split(":///", 1)[1]
    else:
        path = "./topiceye.db"
    return os.path.abspath(path)


# ── DuckDB Analytics singleton ─────────────────────────────────────────

class DuckDBAnalytics:
    """
    Thread-local DuckDB connection that attaches SQLite in READ_ONLY mode.

    Each thread gets its own in-memory DuckDB instance with the SQLite file
    attached. This avoids concurrency issues and ensures fresh data.
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._sqlite_path = _sqlite_path()
        self._available: Optional[bool] = None  # tri-state: None=unchecked

    def _get_conn(self):
        """Get or create a thread-local DuckDB connection with SQLite attached."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn

        import duckdb

        conn = duckdb.connect(":memory:")
        conn.execute("SET threads=2")
        conn.execute("SET memory_limit='256MB'")

        # Load sqlite extension and attach
        conn.execute("INSTALL sqlite; LOAD sqlite;")
        conn.execute(
            f"ATTACH '{self._sqlite_path}' AS sqlite_db (TYPE SQLITE, READ_ONLY)"
        )

        self._local.conn = conn
        logger.info(
            "DuckDB analytics: attached SQLite %s (thread %s)",
            self._sqlite_path,
            threading.current_thread().name,
        )
        return conn

    def close(self) -> None:
        """Close the thread-local DuckDB connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
            logger.info("DuckDB analytics: connection closed")

    @property
    def available(self) -> bool:
        """Check if DuckDB analytics layer is available."""
        if self._available is not None:
            return self._available
        try:
            conn = self._get_conn()
            conn.execute("SELECT 1 FROM sqlite_db.content_items LIMIT 1")
            self._available = True
        except Exception as e:
            logger.warning("DuckDB analytics not available: %s", e)
            self._available = False
        return self._available

    def reset_availability(self) -> None:
        """Reset availability check (e.g. after a failure)."""
        self._available = None

    # ── Analytical queries ──────────────────────────────────────────────

    def query_today_picks(
        self,
        hours: int = 48,
        curation_threshold: float = 60,
        weight_bonus: int = 8,
        risk_threshold: float = 70,
    ) -> List[Dict[str, Any]]:
        """
        Top curated picks from the last N hours.

        Runs the curation scoring + source weight adjustment entirely in DuckDB.
        Returns items with adjusted_curation_score >= threshold.
        """
        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        results = conn.execute(f"""
            SELECT
                c.id, c.title, c.url, c.source_id, c.source_name, c.source_type,
                c.platform, c.author,
                c.published_at, c.crawled_at,
                c.summary, c.category, c.tags, c.language,
                c.topic_id, c.duplicate_of, c.similarity_score,
                a.quality_score, a.hot_score, a.freshness_score,
                a.creator_score, a.viral_score, a.risk_score,
                a.curation_score, a.info_density, a.actionability,
                a.recommended_reason, a.recommendation,
                a.summary AS ai_summary, a.tags AS ai_tags,
                a.enrichment_status, a.enrichment,
                COALESCE(s.weight, 3) AS source_weight,
                CASE
                    WHEN a.curation_score > 0
                        THEN a.curation_score + (COALESCE(s.weight, 3) - 3) * {weight_bonus}
                    ELSE (COALESCE(a.creator_score, 0) + COALESCE(a.viral_score, 0)) / 2.0
                         + (COALESCE(s.weight, 3) - 3) * {weight_bonus}
                END AS adjusted_curation_score
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            LEFT JOIN sqlite_db.sources s ON s.id = c.source_id
            WHERE c.crawled_at >= '{cutoff}'
              AND a.risk_score <= {risk_threshold}
              AND a.curation_score IS NOT NULL
            ORDER BY adjusted_curation_score DESC
        """).fetchall()

        columns = [
            'id', 'title', 'url', 'source_id', 'source_name', 'source_type',
            'platform', 'author', 'published_at', 'crawled_at',
            'summary', 'category', 'tags', 'language',
            'topic_id', 'duplicate_of', 'similarity_score',
            'quality_score', 'hot_score', 'freshness_score',
            'creator_score', 'viral_score', 'risk_score',
            'curation_score', 'info_density', 'actionability',
            'recommended_reason', 'recommendation',
            'ai_summary', 'ai_tags',
            'enrichment_status', 'enrichment', 'source_weight',
            'adjusted_curation_score',
        ]

        items: List[Dict[str, Any]] = []
        for row in results:
            item = dict(zip(columns, row))
            if item['adjusted_curation_score'] < curation_threshold:
                continue
            # Serialize datetime fields
            for dt_field in ('published_at', 'crawled_at'):
                val = item.get(dt_field)
                if val and hasattr(val, 'isoformat'):
                    item[dt_field] = val.isoformat()
            # Round floats
            item['adjusted_curation_score'] = round(float(item['adjusted_curation_score']), 1)
            for score_field in (
                'quality_score', 'hot_score', 'freshness_score',
                'creator_score', 'viral_score', 'risk_score',
                'curation_score', 'info_density', 'actionability',
                'similarity_score',
            ):
                val = item.get(score_field)
                if val is not None:
                    item[score_field] = float(val)
            items.append(item)

        return items

    def query_topics(self) -> List[Dict[str, Any]]:
        """Get all topic groups ordered by best_score."""
        conn = self._get_conn()
        results = conn.execute("""
            SELECT id, name, summary, keywords, best_score, content_count
            FROM sqlite_db.topic_groups
            ORDER BY best_score DESC
        """).fetchall()

        return [
            {
                "id": row[0],
                "name": row[1],
                "summary": row[2],
                "keywords": row[3],
                "best_score": float(row[4]) if row[4] else 0.0,
                "content_count": row[5] or 0,
            }
            for row in results
        ]

    def query_trend_topics(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get topic trend data for the last N days."""
        conn = self._get_conn()
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        results = conn.execute(f"""
            SELECT snapshot_date, topic_id, topic_name, content_count,
                   avg_score, max_score, pick_count, top_items
            FROM sqlite_db.topic_trends
            WHERE topic_id IS NOT NULL
              AND snapshot_date >= '{cutoff}'
            ORDER BY snapshot_date, topic_id
        """).fetchall()

        return [
            {
                "date": str(row[0]) if hasattr(row[0], 'isoformat') else str(row[0]),
                "topic_id": row[1],
                "topic_name": row[2],
                "content_count": row[3],
                "avg_score": float(row[4]) if row[4] else 0.0,
                "max_score": float(row[5]) if row[5] else 0.0,
                "pick_count": row[6] or 0,
                "top_items": row[7],
            }
            for row in results
        ]

    def query_keyword_cloud(self, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
        """Get keyword frequency for word cloud, aggregated over N days."""
        conn = self._get_conn()
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        results = conn.execute(f"""
            SELECT keyword, SUM(content_count) AS total
            FROM sqlite_db.topic_trends
            WHERE keyword IS NOT NULL
              AND snapshot_date >= '{cutoff}'
            GROUP BY keyword
            ORDER BY total DESC
            LIMIT {limit}
        """).fetchall()

        return [
            {"keyword": row[0], "count": int(row[1])}
            for row in results
        ]

    def query_daily_stats(self) -> Dict[str, Any]:
        """Statistics for daily report generation."""
        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()

        row = conn.execute(f"""
            SELECT
                COUNT(*) AS total_items,
                COUNT(CASE WHEN a.curation_score >= 70 THEN 1 END) AS curated_count,
                AVG(a.curation_score) AS avg_curation,
                MAX(a.curation_score) AS max_curation,
                COUNT(DISTINCT c.topic_id) AS topic_count,
                COUNT(CASE WHEN c.duplicate_of IS NOT NULL THEN 1 END) AS dup_count
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            WHERE c.crawled_at >= '{cutoff}'
              AND a.risk_score <= 70
        """).fetchone()

        return {
            "total_items": row[0] or 0,
            "curated_count": row[1] or 0,
            "avg_curation": round(float(row[2] or 0), 1),
            "max_curation": round(float(row[3] or 0), 1),
            "topic_count": row[4] or 0,
            "dup_count": row[5] or 0,
        }

    def query_dashboard_stats(self, days: int = 7) -> Dict[str, Any]:
        """Dashboard statistics: KPI cards + source breakdown + daily volume trend."""
        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # ── KPI row ────────────────────────────────────────────────────────
        kpi_row = conn.execute(f"""
            SELECT
                COUNT(DISTINCT c.id) AS total_crawled,
                COUNT(DISTINCT CASE WHEN a.curation_score >= 70 THEN c.id END) AS total_curated,
                ROUND(AVG(a.curation_score), 1) AS avg_curation,
                COUNT(DISTINCT c.source_id) AS active_sources
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            WHERE c.crawled_at >= '{cutoff}'
        """).fetchone()

        # ── Source breakdown (curated count per source) ───────────────────
        source_rows = conn.execute(f"""
            SELECT
                s.name,
                s.source_type,
                COUNT(DISTINCT c.id) AS content_count,
                COUNT(DISTINCT CASE WHEN a.curation_score >= 70 THEN c.id END) AS curated_count,
                ROUND(AVG(a.curation_score), 1) AS avg_score
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            LEFT JOIN sqlite_db.sources s ON s.id = c.source_id
            WHERE c.crawled_at >= '{cutoff}'
            GROUP BY s.id, s.name, s.source_type
            HAVING COUNT(DISTINCT c.id) > 0
            ORDER BY content_count DESC
            LIMIT 20
        """).fetchall()

        # ── Daily volume trend ─────────────────────────────────────────────
        trend_rows = conn.execute(f"""
            SELECT
                DATE(c.crawled_at) AS crawl_date,
                COUNT(DISTINCT c.id) AS content_count,
                COUNT(DISTINCT CASE WHEN a.curation_score >= 70 THEN c.id END) AS curated_count,
                ROUND(AVG(a.curation_score), 1) AS avg_curation
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            WHERE c.crawled_at >= '{cutoff}'
            GROUP BY DATE(c.crawled_at)
            ORDER BY crawl_date ASC
        """).fetchall()

        return {
            "kpi": {
                "total_crawled": kpi_row[0] or 0,
                "total_curated": kpi_row[1] or 0,
                "avg_curation": round(float(kpi_row[2] or 0), 1),
                "active_sources": kpi_row[3] or 0,
            },
            "source_breakdown": [
                {
                    "source_name": row[0] or "未知",
                    "source_type": row[1] or "rss",
                    "content_count": row[2] or 0,
                    "curated_count": row[3] or 0,
                    "avg_score": round(float(row[4] or 0), 1),
                }
                for row in source_rows
            ],
            "daily_trend": [
                {
                    "date": row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                    "content_count": row[1] or 0,
                    "curated_count": row[2] or 0,
                    "avg_curation": round(float(row[3] or 0), 1),
                }
                for row in trend_rows
            ],
        }

    def query_content_for_report(self, hours: int = 48) -> List[Dict[str, Any]]:
        """Fetch recently analyzed content for daily report generation."""
        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        results = conn.execute(f"""
            SELECT c.id, c.title, c.category, c.source_name, a.summary,
                   a.creator_score, a.viral_score, a.quality_score, a.risk_score,
                   a.recommended_reason
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            WHERE c.crawled_at >= '{cutoff}'
              AND a.curation_score IS NOT NULL
            ORDER BY (COALESCE(a.creator_score, 0) + COALESCE(a.viral_score, 0)) DESC
            LIMIT 15
        """).fetchall()

        return [
            {
                "id": row[0],
                "title": row[1],
                "category": row[2],
                "source_name": row[3],
                "summary": row[4] or "",
                "creator_score": float(row[5]) if row[5] else 0,
                "viral_score": float(row[6]) if row[6] else 0,
                "quality_score": float(row[7]) if row[7] else 0,
                "risk_score": float(row[8]) if row[8] else 0,
                "recommended_reason": row[9] or "",
            }
            for row in results
        ]

    def query_content_for_weekly(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Fetch analyzed content for a given week date range (YYYY-MM-DD strings).

        Returns items sorted by curation_score descending, with additional fields
        for weekly digest generation (tags, recommendation, curation_score).
        """
        conn = self._get_conn()

        results = conn.execute(f"""
            SELECT c.id, c.title, c.category, c.source_name, c.platform,
                   a.summary, a.creator_score, a.viral_score, a.quality_score,
                   a.risk_score, a.curation_score, a.tags, a.recommendation,
                   a.recommended_reason
            FROM sqlite_db.content_items c
            LEFT JOIN sqlite_db.ai_analyses a ON a.content_id = c.id
            WHERE DATE(c.crawled_at) >= '{start_date}'
              AND DATE(c.crawled_at) <= '{end_date}'
              AND a.curation_score IS NOT NULL
            ORDER BY COALESCE(a.curation_score, 0) DESC, COALESCE(a.creator_score, 0) DESC
        """).fetchall()

        return [
            {
                "id": row[0],
                "title": row[1],
                "category": row[2] or "未分类",
                "source_name": row[3] or "",
                "platform": row[4] or "",
                "summary": row[5] or "",
                "creator_score": float(row[6]) if row[6] else 0,
                "viral_score": float(row[7]) if row[7] else 0,
                "quality_score": float(row[8]) if row[8] else 0,
                "risk_score": float(row[9]) if row[9] else 0,
                "curation_score": float(row[10]) if row[10] else 0,
                "tags": row[11] or [],
                "recommendation": row[12] or "",
                "recommended_reason": row[13] or "",
            }
            for row in results
        ]


# ── Module-level singleton ─────────────────────────────────────────────

_analytics: Optional[DuckDBAnalytics] = None
_lock = threading.Lock()


def get_analytics() -> DuckDBAnalytics:
    """Get the module-level DuckDBAnalytics singleton."""
    global _analytics
    if _analytics is None:
        with _lock:
            if _analytics is None:
                _analytics = DuckDBAnalytics()
    return _analytics


def close_analytics() -> None:
    """Close the DuckDBAnalytics singleton."""
    global _analytics
    if _analytics is not None:
        _analytics.close()
        _analytics = None


# ── Backward-compatible function API ───────────────────────────────────
# These match the original function signatures so existing callers work
# without any changes.

def query_today_picks(hours: int = 48, **kwargs) -> List[Dict[str, Any]]:
    return get_analytics().query_today_picks(hours=hours, **kwargs)

def query_topics() -> List[Dict[str, Any]]:
    return get_analytics().query_topics()

def query_trend_topics(days: int = 7) -> List[Dict[str, Any]]:
    return get_analytics().query_trend_topics(days=days)

def query_keyword_cloud(days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    return get_analytics().query_keyword_cloud(days=days, limit=limit)

def query_daily_stats() -> Dict[str, Any]:
    return get_analytics().query_daily_stats()

def query_dashboard_stats(days: int = 7) -> Dict[str, Any]:
    return get_analytics().query_dashboard_stats(days=days)

def query_content_for_report(hours: int = 48) -> List[Dict[str, Any]]:
    return get_analytics().query_content_for_report(hours=hours)


def query_content_for_weekly(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Fetch analyzed content for a given week date range (YYYY-MM-DD strings)."""
    return get_analytics().query_content_for_weekly(start_date=start_date, end_date=end_date)
