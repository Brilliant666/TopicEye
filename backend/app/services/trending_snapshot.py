"""
趋势雷达历史快照服务。

每天定时保存全量快照（APScheduler），
保留15天，超过则清理。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trending import TrendingItem, TrendingSnapshot, TrendingSource
from app.services.trending_scrapers import get_all_trending_sources

logger = logging.getLogger(__name__)

# 快照保留天数
SNAPSHOT_RETENTION_DAYS = 15


async def save_snapshot(db: AsyncSession, source: str) -> int:
    """
    为指定 source 保存当天快照。
    如果当日已存在则覆盖（upsert）。
    返回保存的条目数。
    """
    today = date.today()

    # 取当前最新数据
    result = await db.execute(
        select(TrendingItem).where(TrendingItem.source == source).order_by(TrendingItem.rank)
    )
    items = result.scalars().all()

    if not items:
        logger.info("save_snapshot: no items for source=%s, skip", source)
        return 0

    # 序列化
    items_json = [
        {
            "rank": it.rank,
            "title": it.title,
            "url": it.url,
            "hot_value": it.hot_value,
            "hot_value_raw": it.hot_value_raw,
            "trend": it.trend,
        }
        for it in items
    ]

    # 查重：当日该 source 是否已有快照
    existing = await db.execute(
        select(TrendingSnapshot).where(
            and_(
                TrendingSnapshot.snapshot_date == today,
                TrendingSnapshot.source == source,
            )
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.items = items_json
        record.total_count = len(items_json)
        record.fetched_at = datetime.utcnow()
        logger.info("save_snapshot: updated source=%s date=%s count=%d", source, today, len(items_json))
    else:
        record = TrendingSnapshot(
            snapshot_date=today,
            source=source,
            category=items[0].category if items else "hot",
            items=items_json,
            total_count=len(items_json),
            fetched_at=datetime.utcnow(),
        )
        db.add(record)
        logger.info("save_snapshot: created source=%s date=%s count=%d", source, today, len(items_json))

    await db.flush()
    return len(items_json)


async def save_all_snapshots(db: AsyncSession) -> dict:
    """
    为所有有数据的 source 保存快照。
    返回 {source: count, ...}
    """
    results = {}
    for source_name in get_all_trending_sources():
        try:
            count = await save_snapshot(db, source_name)
            if count > 0:
                results[source_name] = count
        except Exception as exc:
            logger.exception("save_snapshot failed for source=%s", source_name)
            results[source_name] = 0
    return results


async def cleanup_old_snapshots(db: AsyncSession) -> int:
    """
    删除 15 天前的快照。
    返回删除条数。
    """
    cutoff = date.today() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
    result = await db.execute(
        delete(TrendingSnapshot).where(TrendingSnapshot.snapshot_date < cutoff)
    )
    # result.rowcount 在 SQLAlchemy 2.0 中可能不可用，改用 count 查询
    count = len((await db.execute(select(TrendingSnapshot).where(TrendingSnapshot.snapshot_date < cutoff))).scalars().all())
    logger.info("cleanup_old_snapshots: deleted %d snapshots before %s", count, cutoff)
    return count


async def get_snapshot_diff(db: AsyncSession, source: str) -> Optional[dict]:
    """
    获取今日 vs 昨日的快照对比。
    返回 {"yesterday_rank": {title: rank}, "today_rank": {title: rank}, "changes": [...]}
    或 None（数据不足）。
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    # 取两天快照
    snap_today = await db.execute(
        select(TrendingSnapshot).where(
            and_(TrendingSnapshot.snapshot_date == today, TrendingSnapshot.source == source)
        )
    )
    snap_today = snap_today.scalar_one_or_none()

    snap_yesterday = await db.execute(
        select(TrendingSnapshot).where(
            and_(TrendingSnapshot.snapshot_date == yesterday, TrendingSnapshot.source == source)
        )
    )
    snap_yesterday = snap_yesterday.scalar_one_or_none()

    if not snap_yesterday and not snap_today:
        return None

    def build_rank_map(snap):
        if not snap:
            return {}
        return {item["title"]: item["rank"] for item in snap.items}

    yesterday_ranks = build_rank_map(snap_yesterday)
    today_ranks = build_rank_map(snap_today)

    # 计算变化
    changes = []
    all_titles = set(yesterday_ranks.keys()) | set(today_ranks.keys())

    for title in all_titles:
        y_rank = yesterday_ranks.get(title)
        t_rank = today_ranks.get(title)
        if y_rank is None and t_rank is not None:
            change = "new"
        elif t_rank is None and y_rank is not None:
            change = "dropped"
        elif t_rank < y_rank:
            change = "up"
        elif t_rank > y_rank:
            change = "down"
        else:
            change = "same"
        changes.append({"title": title, "yesterday_rank": y_rank, "today_rank": t_rank, "change": change})

    return {
        "yesterday_date": str(yesterday),
        "today_date": str(today),
        "yesterday_count": len(yesterday_ranks),
        "today_count": len(today_ranks),
        "changes": sorted(changes, key=lambda x: x["change"] != "new", reverse=True),
    }