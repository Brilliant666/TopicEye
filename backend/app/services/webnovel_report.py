"""
Webnovel report service — weekly history and rank movement analysis.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Optional, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fanqie import FanqieBook, FanqieCategory, FanqieRankSnapshot
from app.models.qimao import QimaoBook
from app.models.zhihu import ZhihuAlbum


def _platform_label(platform: str) -> str:
    return {
        "fanqie": "番茄小说",
        "qimao": "七猫小说",
        "zhihu": "知乎盐选",
    }.get(platform, platform)


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").strip()
    try:
        return int(float(text))
    except ValueError:
        return 0


def _movement_item(
    *,
    platform: str,
    title: str,
    author: Optional[str],
    category: Optional[str],
    rank_type: str,
    position: int,
    change: int,
    url: Optional[str] = None,
) -> dict:
    return {
        "platform": platform,
        "platform_label": _platform_label(platform),
        "title": title,
        "author": author or "",
        "category": category or "未分类",
        "rank_type": rank_type,
        "position": position,
        "change": change,
        "url": url,
    }


async def _fanqie_history(db: AsyncSession, start_date: str, end_date: str) -> dict:
    rows = await db.execute(
        select(FanqieRankSnapshot)
        .where(FanqieRankSnapshot.snapshot_date >= start_date)
        .where(FanqieRankSnapshot.snapshot_date <= end_date)
        .order_by(FanqieRankSnapshot.snapshot_date.asc(), FanqieRankSnapshot.rank_type.asc(), FanqieRankSnapshot.position.asc())
    )
    snapshots = rows.scalars().all()
    if not snapshots:
        return {
            "snapshot_dates": [],
            "daily_counts": [],
            "rank_movements": [],
            "category_mix": [],
            "read_count_delta": 0,
        }

    category_rows = await db.execute(select(FanqieCategory.fanqie_id, FanqieCategory.name))
    category_names = {row[0]: row[1] for row in category_rows.all()}

    dates = sorted({snap.snapshot_date for snap in snapshots})
    latest_date = dates[-1]
    daily_counter = Counter(snap.snapshot_date for snap in snapshots)
    latest_category_counter = Counter(
        category_names.get(snap.category_id, snap.category_id)
        for snap in snapshots
        if snap.snapshot_date == latest_date
    )

    by_book_rank: dict[tuple[str, str], list[FanqieRankSnapshot]] = defaultdict(list)
    for snap in snapshots:
        by_book_rank[(snap.book_id, snap.rank_type)].append(snap)

    movements = []
    read_count_delta = 0
    for (_, rank_type), items in by_book_rank.items():
        items.sort(key=lambda item: item.snapshot_date)
        first = items[0]
        latest = items[-1]
        if first.snapshot_date == latest.snapshot_date:
            continue
        change = first.position - latest.position
        first_reads = _safe_int(first.read_count)
        latest_reads = _safe_int(latest.read_count)
        read_count_delta += max(0, latest_reads - first_reads)
        if change == 0:
            continue
        movements.append(_movement_item(
            platform="fanqie",
            title=latest.book_name,
            author=None,
            category=category_names.get(latest.category_id, latest.category_id),
            rank_type=rank_type,
            position=latest.position,
            change=change,
            url=f"https://fanqienovel.com/page/{latest.book_id}",
        ))

    movements.sort(key=lambda item: abs(item["change"]), reverse=True)
    category_mix = [
        {"category": name, "count": count}
        for name, count in latest_category_counter.most_common(10)
    ]

    return {
        "snapshot_dates": dates,
        "daily_counts": [
            {"date": day, "count": daily_counter.get(day, 0)}
            for day in dates
        ],
        "rank_movements": movements[:24],
        "category_mix": category_mix,
        "read_count_delta": read_count_delta,
    }


async def _fanqie_current(db: AsyncSession) -> tuple[int, list[dict]]:
    rows = await db.execute(
        select(FanqieBook)
        .where(FanqieBook.rank_pos_diff != None)  # noqa: E711
        .order_by(func.abs(FanqieBook.rank_pos_diff).desc())
        .limit(30)
    )
    books = rows.scalars().all()
    movements = [
        _movement_item(
            platform="fanqie",
            title=book.book_name,
            author=book.author,
            category=book.category_name,
            rank_type=book.rank_type,
            position=book.current_pos,
            change=book.rank_pos_diff or 0,
            url=f"https://fanqienovel.com/page/{book.book_id}",
        )
        for book in books
        if book.rank_pos_diff
    ]
    count = (await db.execute(select(func.count()).select_from(FanqieBook))).scalar() or 0
    return count, movements


async def _qimao_current(db: AsyncSession) -> tuple[int, list[dict], list[dict]]:
    rows = await db.execute(
        select(QimaoBook)
        .where(QimaoBook.index_change != None)  # noqa: E711
        .order_by(func.abs(QimaoBook.index_change).desc())
        .limit(30)
    )
    books = rows.scalars().all()
    movements = [
        _movement_item(
            platform="qimao",
            title=book.title,
            author=book.author,
            category=book.category1_name,
            rank_type=f"{book.channel}_{book.rank_type}",
            position=book.position,
            change=book.index_change or 0,
            url=f"https://www.qimao.com/shuku/{book.book_id}/",
        )
        for book in books
        if book.index_change
    ]
    count = (await db.execute(select(func.count()).select_from(QimaoBook))).scalar() or 0
    category_rows = await db.execute(
        select(QimaoBook.category1_name, func.count(QimaoBook.id).label("count"))
        .where(QimaoBook.category1_name != None)  # noqa: E711
        .group_by(QimaoBook.category1_name)
        .order_by(func.count(QimaoBook.id).desc())
        .limit(8)
    )
    categories = [{"category": row[0], "count": row[1]} for row in category_rows.all()]
    return count, movements, categories


async def _zhihu_current(db: AsyncSession) -> tuple[int, list[dict], list[dict]]:
    rows = await db.execute(
        select(ZhihuAlbum)
        .where(ZhihuAlbum.rank_pos_diff != None)  # noqa: E711
        .order_by(func.abs(ZhihuAlbum.rank_pos_diff).desc(), ZhihuAlbum.position.asc())
        .limit(30)
    )
    albums = rows.scalars().all()
    movements = [
        _movement_item(
            platform="zhihu",
            title=album.title,
            author=album.author,
            category=album.category2_name or album.category1_name,
            rank_type=album.sort_type,
            position=album.position,
            change=album.rank_pos_diff or 0,
            url=album.url,
        )
        for album in albums
        if album.rank_pos_diff
    ]
    count = (await db.execute(select(func.count()).select_from(ZhihuAlbum))).scalar() or 0
    category_rows = await db.execute(
        select(ZhihuAlbum.category2_name, func.count(ZhihuAlbum.id).label("count"))
        .where(ZhihuAlbum.category2_name != None)  # noqa: E711
        .group_by(ZhihuAlbum.category2_name)
        .order_by(func.count(ZhihuAlbum.id).desc())
        .limit(8)
    )
    categories = [{"category": row[0], "count": row[1]} for row in category_rows.all()]
    return count, movements, categories


async def build_weekly_webnovel_report(db: AsyncSession, days: int = 7) -> dict:
    """Build a read-only weekly webnovel report from stored rankings and snapshots."""
    safe_days = max(3, min(days, 31))
    today = date.today()
    start = today - timedelta(days=safe_days - 1)
    start_iso = start.isoformat()
    end_iso = today.isoformat()

    fanqie_history = await _fanqie_history(db, start_iso, end_iso)
    fanqie_count, fanqie_current = await _fanqie_current(db)
    qimao_count, qimao_current, qimao_categories = await _qimao_current(db)
    zhihu_count, zhihu_current, zhihu_categories = await _zhihu_current(db)

    current_movements = fanqie_current + qimao_current + zhihu_current
    if fanqie_history["rank_movements"]:
        movement_keys = {
            (item["platform"], item["title"], item["rank_type"])
            for item in current_movements
        }
        current_movements.extend(
            item
            for item in fanqie_history["rank_movements"]
            if (item["platform"], item["title"], item["rank_type"]) not in movement_keys
        )
    current_movements.sort(key=lambda item: abs(item["change"]), reverse=True)

    rising = [item for item in current_movements if item["change"] > 0]
    falling = [item for item in current_movements if item["change"] < 0]

    platform_summary = [
        {
            "platform": "fanqie",
            "label": "番茄小说",
            "item_count": fanqie_count,
            "rising_count": len([item for item in fanqie_current if item["change"] > 0]),
            "falling_count": len([item for item in fanqie_current if item["change"] < 0]),
            "history_days": len(fanqie_history["snapshot_dates"]),
        },
        {
            "platform": "qimao",
            "label": "七猫小说",
            "item_count": qimao_count,
            "rising_count": len([item for item in qimao_current if item["change"] > 0]),
            "falling_count": len([item for item in qimao_current if item["change"] < 0]),
            "history_days": 1 if qimao_count else 0,
        },
        {
            "platform": "zhihu",
            "label": "知乎盐选",
            "item_count": zhihu_count,
            "rising_count": len([item for item in zhihu_current if item["change"] > 0]),
            "falling_count": len([item for item in zhihu_current if item["change"] < 0]),
            "history_days": 1 if zhihu_count else 0,
        },
    ]

    return {
        "period": {
            "start": start_iso,
            "end": end_iso,
            "days": safe_days,
            "label": f"{start.month}月{start.day}日 ~ {today.month}月{today.day}日",
        },
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "total_items": fanqie_count + qimao_count + zhihu_count,
            "snapshot_days": len(fanqie_history["snapshot_dates"]),
            "rising_count": len(rising),
            "falling_count": len(falling),
            "read_count_delta": fanqie_history["read_count_delta"],
        },
        "platforms": platform_summary,
        "daily_counts": fanqie_history["daily_counts"],
        "top_risers": rising[:10],
        "top_fallers": falling[:10],
        "category_mix": {
            "fanqie": fanqie_history["category_mix"],
            "qimao": qimao_categories,
            "zhihu": zhihu_categories,
        },
        "notes": [
            "番茄小说已保存日级排名快照，可展示周内排名变化。",
            "七猫小说与知乎盐选当前使用最近一次同步的排名变化；补充快照表后可扩展为完整历史曲线。",
        ],
    }
