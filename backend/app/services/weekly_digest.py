"""
Weekly Digest service — generate AI-powered weekly curated newsletter.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.weekly_digest import WeeklyDigest
from app.models.content import ContentItem
from app.models.analysis import AiAnalysis
from app.services.llm import call_llm_json
from app.services.llm.prompts.weekly_digest import WEEKLY_DIGEST_PROMPT

logger = logging.getLogger(__name__)


def _get_week_range(reference_date: Optional[date] = None) -> tuple[str, str, str, str]:
    """Return (week_key, week_label, week_start_iso, week_end_iso) for a given date's week.

    Week runs Monday–Sunday (ISO week).
    week_key format: "2025-W21"
    week_label format: "5月19日 ~ 5月25日"
    """
    d = reference_date or date.today()
    iso_cal = d.isocalendar()
    week_key = f"{iso_cal[0]}-W{iso_cal[1]:02d}"

    # Monday of this week
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)

    def _fmt(dt: date) -> str:
        return f"{dt.month}月{dt.day}日"

    week_label = f"{_fmt(monday)} ~ {_fmt(sunday)}"
    return week_key, week_label, monday.isoformat(), sunday.isoformat()


async def _fetch_weekly_analyzed(db: AsyncSession, week_start: str, week_end: str) -> list[dict]:
    """Fetch analyzed content items within the given week range.

    Tries DuckDB analytical layer first for better performance.
    Falls back to SQLite if DuckDB is not available.
    """
    # ── Try DuckDB fast path ──
    try:
        from app.services.duckdb_service import query_content_for_weekly
        data = query_content_for_weekly(start_date=week_start, end_date=week_end)
        if data:
            return data
    except Exception:
        pass  # Fall through to SQLite

    # ── SQLite fallback ──
    start_dt = datetime.combine(date.fromisoformat(week_start), datetime.min.time())
    end_dt = datetime.combine(date.fromisoformat(week_end), datetime.max.time())

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
        a = item.analyses[-1]
        data.append({
            "id": item.id,
            "title": item.title,
            "category": item.category or "未分类",
            "source_name": item.source_name or "",
            "platform": item.platform or "",
            "creator_score": a.creator_score or 0,
            "viral_score": a.viral_score or 0,
            "quality_score": a.quality_score or 0,
            "risk_score": a.risk_score or 0,
            "curation_score": a.curation_score or 0,
            "summary": a.summary or "",
            "tags": a.tags or [],
            "recommendation": a.recommendation or "",
        })

    # Sort by curation_score descending, then creator_score
    data.sort(key=lambda x: (x["curation_score"], x["creator_score"]), reverse=True)
    return data


def _build_category_stats(items: list[dict]) -> dict:
    """Build category-level statistics from items."""
    cats: dict[str, dict] = {}
    for item in items:
        cat = item["category"]
        if cat not in cats:
            cats[cat] = {"count": 0, "scores": [], "titles": []}
        cats[cat]["count"] += 1
        cats[cat]["scores"].append(item["creator_score"])
        cats[cat]["titles"].append(item["title"])
    return cats


async def generate_weekly_digest(
    db: AsyncSession,
    reference_date: Optional[date] = None,
) -> WeeklyDigest:
    """Generate (or regenerate) the weekly digest for the PREVIOUS week.

    By default, generates last week's digest (Monday–Sunday).
    If reference_date is provided, uses that date's previous week.

    Args:
        db: Database session.
        reference_date: The date whose PREVIOUS ISO week to generate for. Defaults to today.

    Returns:
        The WeeklyDigest record (may have status ERROR if generation failed).
    """
    # Use PREVIOUS week, not current week
    d = reference_date or date.today()
    last_week_date = d - timedelta(days=7)
    week_key, week_label, week_start, week_end = _get_week_range(last_week_date)

    # Check if digest already exists and is done
    existing = await db.execute(
        select(WeeklyDigest).where(WeeklyDigest.week_key == week_key)
    )
    digest = existing.scalar_one_or_none()

    if digest and digest.status == "DONE":
        return digest

    # Fetch this week's analyzed content
    items_data = await _fetch_weekly_analyzed(db, week_start, week_end)

    # If no data for the strict ISO week, expand to the last 7 days
    if not items_data:
        expanded_start = (date.fromisoformat(week_end) - timedelta(days=6)).isoformat()
        items_data = await _fetch_weekly_analyzed(db, expanded_start, week_end)
        if items_data:
            logger.info(
                "Weekly digest: no data for ISO week %s, expanded to %s ~ %s (%d items)",
                week_key, expanded_start, week_end, len(items_data),
            )

    if not items_data:
        if not digest:
            digest = WeeklyDigest(
                week_key=week_key,
                week_label=week_label,
                week_start=week_start,
                week_end=week_end,
                status="ERROR",
                overview="本周暂无分析数据，请先同步信源并等待 AI 分析完成。",
            )
            db.add(digest)
            await db.flush()
            await db.commit()
            return digest
        return digest

    # Build items text for prompt (top 25)
    items_text = ""
    for i, item in enumerate(items_data[:25], 1):
        items_text += f"\n{i}. [{item['category']}] {item['title']}"
        items_text += (
            f"\n   来源: {item['source_name']} | "
            f"精选:{item['curation_score']:.0f} 创作:{item['creator_score']:.0f} "
            f"爆文:{item['viral_score']:.0f} 质量:{item['quality_score']:.0f} 风险:{item['risk_score']:.0f}"
        )
        if item.get("summary"):
            items_text += f"\n   摘要: {item['summary'][:120]}"
        if item.get("recommendation"):
            items_text += f"\n   推荐语: {item['recommendation'][:80]}"

    # Build category stats text
    cat_stats = _build_category_stats(items_data)
    category_text = ""
    for cat, info in sorted(cat_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        avg = sum(info["scores"]) / len(info["scores"]) if info["scores"] else 0
        category_text += f"\n- {cat}: {info['count']}篇, 平均创作分 {avg:.0f}, 热门: {info['titles'][0][:40]}"

    prompt = WEEKLY_DIGEST_PROMPT.format(
        week_label=week_label,
        items_text=items_text,
        category_text=category_text,
    )

    # Update or create digest record
    if not digest:
        digest = WeeklyDigest(
            week_key=week_key,
            week_label=week_label,
            week_start=week_start,
            week_end=week_end,
            status="GENERATING",
            content_count=len(items_data),
            analyzed_count=len(items_data),
            source_count=len({x["source_name"] for x in items_data}),
            category_count=len(cat_stats),
        )
        db.add(digest)
        await db.flush()
    else:
        digest.status = "GENERATING"
        digest.content_count = len(items_data)
        digest.analyzed_count = len(items_data)
        digest.source_count = len({x["source_name"] for x in items_data})
        digest.category_count = len(cat_stats)
        await db.flush()

    try:
        result = await call_llm_json(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
            scene="weekly_digest",
        )

        # Validate LLM returned useful content — empty dict is a failure
        overview = result.get("overview", "")
        if not overview or "raw_response" in result:
            raise ValueError(f"LLM返回空内容或格式无效: {str(result)[:200]}")

        digest.overview = overview
        digest.takeaway = result.get("takeaway", "")
        digest.keywords = json.dumps(result.get("keywords", []), ensure_ascii=False)
        digest.trends = json.dumps(result.get("trends", []), ensure_ascii=False)
        digest.top_picks = json.dumps(result.get("top_picks", []), ensure_ascii=False)
        digest.category_summary = json.dumps(result.get("category_summary", {}), ensure_ascii=False)
        digest.platform_tips = json.dumps(result.get("platform_tips", {}), ensure_ascii=False)
        digest.topic_clusters = json.dumps(result.get("topic_clusters", []), ensure_ascii=False)
        digest.action_items = json.dumps(result.get("action_items", []), ensure_ascii=False)
        digest.status = "DONE"
        digest.updated_at = datetime.utcnow()
        await db.commit()
        logger.info("Weekly digest generated: %s (%s)", week_key, week_label)
        # 通知：周刊生成成功
        try:
            from app.services.notification_service import push_notification
            await push_notification("success", "weekly_digest", "AI周刊生成完成", f"{week_label} 已生成")
        except Exception:
            pass
    except Exception as e:
        digest.status = "ERROR"
        digest.overview = f"生成失败: {str(e)[:200]}"
        await db.commit()
        logger.error("Weekly digest generation failed for %s: %s", week_key, e)
        # 通知：周刊生成失败
        try:
            from app.services.notification_service import push_notification
            await push_notification("error", "weekly_digest", "AI周刊生成失败", str(e)[:200])
        except Exception:
            pass

    return digest
