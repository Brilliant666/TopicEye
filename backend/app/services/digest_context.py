"""
Shared context builders for periodical AI digests.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.duckdb_service import query_content_for_weekly


async def fetch_analyzed_content(
    db: AsyncSession,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Fetch analyzed content through the fixed DuckDB analytical layer."""
    _ = db
    return query_content_for_weekly(start_date=start_date, end_date=end_date)


async def fetch_analyzed_content_with_expanded_window(
    db: AsyncSession,
    start_date: str,
    end_date: str,
    expanded_days: int,
) -> list[dict]:
    """Fetch a strict period first, then expand to a trailing window ending at end_date."""
    data = await fetch_analyzed_content(db, start_date, end_date)
    if data:
        return data

    expanded_start = (date.fromisoformat(end_date) - timedelta(days=expanded_days - 1)).isoformat()
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
        curation_score = item.get("adjusted_score", item.get("curation_score", 0))
        block = [
            f"{index}. [{item['category']}] {item['title']}",
            (
                f"   来源: {item['source_name']} | "
                f"精选:{curation_score:.0f} 创作:{item['creator_score']:.0f} "
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
