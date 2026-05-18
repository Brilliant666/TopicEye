"""
Trend snapshot service — computes daily/periodic aggregates.

Called by the scheduler after clustering. Produces TopicTrend rows
that the frontend queries for trend charts.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, text, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trend import TopicTrend
from app.models.topic import TopicGroup
from app.models.content import ContentItem
from app.models.analysis import AiAnalysis

logger = logging.getLogger(__name__)


async def snapshot_daily_trends(db: AsyncSession, target_date: Optional[date] = None) -> dict:
    """
    Compute and persist daily trend snapshots for topics and keywords.

    Returns {"topics": N, "keywords": N, "date": "YYYY-MM-DD"}.
    """
    if target_date is None:
        target_date = date.today()

    # ── 1. Delete existing snapshots for this date ──────────────────
    await db.execute(
        text("DELETE FROM topic_trends WHERE snapshot_date = :d"),
        {"d": target_date.isoformat()},
    )

    # ── 2. Topic-level trends ───────────────────────────────────────
    # Get content items grouped by topic_id for the target date
    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

    topic_rows = await db.execute(
        select(
            ContentItem.topic_id,
            func.count(ContentItem.id).label("cnt"),
            func.avg(AiAnalysis.curation_score).label("avg_score"),
            func.max(AiAnalysis.curation_score).label("max_score"),
            func.sum(
                case(
                    (AiAnalysis.curation_score >= 60, 1),
                    else_=0,
                )
            ).label("pick_count"),
        )
        .join(AiAnalysis, AiAnalysis.content_id == ContentItem.id)
        .where(
            and_(
                ContentItem.topic_id.isnot(None),
                ContentItem.created_at >= start_dt,
                ContentItem.created_at < end_dt,
            )
        )
        .group_by(ContentItem.topic_id)
    )

    topic_count = 0
    for row in topic_rows:
        topic_id = row.topic_id
        # Get topic name
        tg = await db.get(TopicGroup, topic_id)
        topic_name = tg.name if tg else f"Topic-{topic_id}"

        # Get top 3 items for this topic
        top_q = await db.execute(
            select(ContentItem.title, ContentItem.url, AiAnalysis.curation_score)
            .join(AiAnalysis, AiAnalysis.content_id == ContentItem.id)
            .where(
                and_(
                    ContentItem.topic_id == topic_id,
                    ContentItem.created_at >= start_dt,
                    ContentItem.created_at < end_dt,
                )
            )
            .order_by(AiAnalysis.curation_score.desc())
            .limit(3)
        )
        top_items = [
            {"title": r.title, "url": r.url, "score": round(r.curation_score or 0, 1)}
            for r in top_q
        ]

        snap = TopicTrend(
            snapshot_date=target_date,
            topic_id=topic_id,
            topic_name=topic_name,
            content_count=row.cnt,
            avg_score=round(float(row.avg_score or 0), 1),
            max_score=round(float(row.max_score or 0), 1),
            pick_count=int(row.pick_count or 0),
            top_items=top_items,
        )
        db.add(snap)
        topic_count += 1

    # ── 3. Keyword-level trends ─────────────────────────────────────
    # Extract from tags JSON, count frequency
    keyword_rows = await db.execute(
        select(AiAnalysis.tags)
        .join(ContentItem, ContentItem.id == AiAnalysis.content_id)
        .where(
            and_(
                AiAnalysis.tags.isnot(None),
                ContentItem.created_at >= start_dt,
                ContentItem.created_at < end_dt,
            )
        )
    )

    keyword_stats: dict[str, list[float]] = {}
    for (tags_json,) in keyword_rows:
        if not tags_json:
            continue
        tags_list = tags_json if isinstance(tags_json, list) else json.loads(tags_json)
        for tag in tags_list:
            tag = tag.strip()
            if tag:
                keyword_stats.setdefault(tag, []).append(0)  # just counting

    keyword_count = 0
    for kw, occurrences in sorted(
        keyword_stats.items(), key=lambda x: len(x[1]), reverse=True
    )[:50]:  # top 50 keywords
        snap = TopicTrend(
            snapshot_date=target_date,
            keyword=kw,
            content_count=len(occurrences),
            avg_score=0,
            max_score=0,
            pick_count=0,
        )
        db.add(snap)
        keyword_count += 1

    await db.flush()
    logger.info(
        "Trend snapshot for %s: %d topics, %d keywords",
        target_date, topic_count, keyword_count,
    )

    return {"topics": topic_count, "keywords": keyword_count, "date": target_date.isoformat()}


async def get_topic_trends(
    db: AsyncSession, days: int = 7
) -> list[dict]:
    """Get topic trend data for the last N days."""
    cutoff = date.today() - timedelta(days=days)

    rows = await db.execute(
        select(TopicTrend)
        .where(
            and_(
                TopicTrend.topic_id.isnot(None),
                TopicTrend.snapshot_date >= cutoff,
            )
        )
        .order_by(TopicTrend.snapshot_date, TopicTrend.topic_id)
    )
    trends = rows.scalars().all()
    return [
        {
            "date": t.snapshot_date.isoformat(),
            "topic_id": t.topic_id,
            "topic_name": t.topic_name,
            "content_count": t.content_count,
            "avg_score": t.avg_score,
            "max_score": t.max_score,
            "pick_count": t.pick_count,
            "top_items": t.top_items,
        }
        for t in trends
    ]


async def get_keyword_cloud(
    db: AsyncSession, days: int = 7, limit: int = 50
) -> list[dict]:
    """Get keyword frequency for word cloud, aggregated over N days."""
    cutoff = date.today() - timedelta(days=days)

    rows = await db.execute(
        select(
            TopicTrend.keyword,
            func.sum(TopicTrend.content_count).label("total"),
        )
        .where(
            and_(
                TopicTrend.keyword.isnot(None),
                TopicTrend.snapshot_date >= cutoff,
            )
        )
        .group_by(TopicTrend.keyword)
        .order_by(func.sum(TopicTrend.content_count).desc())
        .limit(limit)
    )

    return [
        {"keyword": r.keyword, "count": int(r.total)}
        for r in rows
    ]
