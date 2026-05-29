"""
Shared context builders for periodical AI digests.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.content import ContentItem


async def fetch_analyzed_content(
    db: AsyncSession,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Fetch analyzed content items within an inclusive date range."""
    try:
        from app.services.duckdb_service import query_content_for_weekly
        data = query_content_for_weekly(start_date=start_date, end_date=end_date)
        if data:
            return data
    except Exception:
        pass

    start_dt = datetime.combine(date.fromisoformat(start_date), datetime.min.time())
    end_dt = datetime.combine(date.fromisoformat(end_date), datetime.max.time())

    query = (
        select(ContentItem)
        .options(selectinload(ContentItem.analyses))
        .join(ContentItem.analyses)
        .where(ContentItem.crawled_at >= start_dt)
        .where(ContentItem.crawled_at <= end_dt)
        .where(ContentItem.analyses.any())
    )
    result = await db.execute(query)
    items = result.scalars().unique().all()

    data = []
    for item in items:
        if not item.analyses:
            continue
        analysis = item.analyses[-1]
        data.append({
            "id": item.id,
            "title": item.title,
            "category": item.category or "未分类",
            "source_name": item.source_name or "",
            "platform": item.platform or "",
            "creator_score": analysis.creator_score or 0,
            "viral_score": analysis.viral_score or 0,
            "quality_score": analysis.quality_score or 0,
            "risk_score": analysis.risk_score or 0,
            "curation_score": analysis.curation_score or 0,
            "summary": analysis.summary or "",
            "tags": analysis.tags or [],
            "recommendation": analysis.recommendation or "",
        })

    data.sort(key=lambda x: (x["curation_score"], x["creator_score"]), reverse=True)
    return data


async def fetch_analyzed_content_with_fallback(
    db: AsyncSession,
    start_date: str,
    end_date: str,
    fallback_days: int,
) -> list[dict]:
    """Fetch a strict period first, then fall back to a trailing window ending at end_date."""
    data = await fetch_analyzed_content(db, start_date, end_date)
    if data:
        return data

    expanded_start = (date.fromisoformat(end_date) - timedelta(days=fallback_days - 1)).isoformat()
    return await fetch_analyzed_content(db, expanded_start, end_date)


def build_category_stats(items: list[dict]) -> dict[str, dict]:
    """Build category-level statistics from scored content items."""
    categories: dict[str, dict] = {}
    for item in items:
        category = item["category"]
        if category not in categories:
            categories[category] = {"count": 0, "scores": [], "titles": []}
        categories[category]["count"] += 1
        categories[category]["scores"].append(item["creator_score"])
        categories[category]["titles"].append(item["title"])
    return categories


def build_items_text(items: list[dict], limit: int = 25) -> str:
    """Build compact ranked item text for digest prompts."""
    lines = []
    for index, item in enumerate(items[:limit], 1):
        block = [
            f"{index}. [{item['category']}] {item['title']}",
            (
                f"   来源: {item['source_name']} | "
                f"精选:{item['curation_score']:.0f} 创作:{item['creator_score']:.0f} "
                f"爆文:{item['viral_score']:.0f} 质量:{item['quality_score']:.0f} "
                f"风险:{item['risk_score']:.0f}"
            ),
        ]
        if item.get("summary"):
            block.append(f"   摘要: {item['summary'][:120]}")
        if item.get("recommendation"):
            block.append(f"   推荐语: {item['recommendation'][:80]}")
        lines.append("\n".join(block))
    return "\n" + "\n".join(lines) if lines else ""


def build_category_text(category_stats: dict[str, dict]) -> str:
    """Build compact category statistics text for digest prompts."""
    lines = []
    for category, info in sorted(category_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        avg = sum(info["scores"]) / len(info["scores"]) if info["scores"] else 0
        lines.append(
            f"- {category}: {info['count']}篇, 平均创作分 {avg:.0f}, 热门: {info['titles'][0][:40]}"
        )
    return "\n" + "\n".join(lines) if lines else ""
