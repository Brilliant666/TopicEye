"""
Daily Report service — generate AI-powered daily briefing.
"""
from __future__ import annotations

import json
from datetime import datetime, date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.daily_report import DailyReport
from app.models.content import ContentItem
from app.models.analysis import AiAnalysis
from app.services.llm import call_llm_json


WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

REPORT_PROMPT = """你是一位资深内容策划顾问。请根据以下今日精选内容数据，生成一份面向创作者的每日选题简报。

## 今日内容数据（{date}）
{items_text}

## 请严格按以下 JSON 格式输出：
{{
  "overview": "一段200字以内的今日热点概述，用轻松专业的口吻，点出今日最值得关注的方向",
  "takeaway": "一句话核心要点，适合作为日报标题/推送文案",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "trends": [
    {{"title": "趋势标题", "desc": "趋势描述（30字内）", "color": "#3B82F6"}}
  ],
  "top_picks": [
    {{"title": "选题标题", "reason": "推荐理由（40字内）", "source_url": "原文链接URL", "score": 85, "platforms": ["公众号", "小红书"]}}
  ],
  "platform_tips": {{
    "公众号": ["tip1"],
    "小红书": ["tip1"],
    "视频号": ["tip1"]
  }}
}}

要求：
- trends 给出 2-3 个今日内容趋势
- top_picks 从上面数据中选 3-5 个最值得写的选题，source_url 必须从上面数据中复制原始URL，不要编造
- platform_tips 给出各平台今天的创作建议
- 所有文本用中文
- 只输出 JSON，不要其他内容"""


async def _fetch_recently_analyzed(db: AsyncSession) -> list[dict]:
    """Fetch recently analyzed content items with scores (48h window).

    Tries DuckDB analytical layer first for better performance.
    Falls back to SQLite if DuckDB has not been synced yet.
    """
    # ── Try DuckDB fast path ──
    try:
        from app.services.duckdb_service import query_content_for_report
        data = query_content_for_report(hours=48)
        if data:
            return data
    except Exception:
        pass  # Fall through to SQLite

    # ── SQLite fallback ──
    from datetime import date, timedelta
    fallback_start = datetime.combine(date.today() - timedelta(days=2), datetime.min.time())

    query = (
        select(ContentItem)
        .options(selectinload(ContentItem.analyses))
        .where(ContentItem.crawled_at >= fallback_start)
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
            "url": item.url,
            "category": item.category,
            "source_name": item.source_name,
            "creator_score": a.creator_score,
            "viral_score": a.viral_score,
            "quality_score": a.quality_score,
            "risk_score": a.risk_score,
            "summary": a.summary or "",
            "recommended_reason": a.recommended_reason or "",
        })

    # Sort by creator_score + viral_score descending
    data.sort(key=lambda x: x["creator_score"] + x["viral_score"], reverse=True)
    return data


async def generate_daily_report(db: AsyncSession) -> DailyReport:
    """Generate (or regenerate) today's AI daily report."""
    today = date.today().isoformat()  # YYYY-MM-DD
    weekday = WEEKDAYS[date.today().weekday()]

    # Check if report already exists for today
    existing = await db.execute(
        select(DailyReport).where(DailyReport.report_date == today)
    )
    report = existing.scalar_one_or_none()

    if report and report.status == "DONE":
        return report

    # Fetch today's analyzed content
    items_data = await _fetch_recently_analyzed(db)

    if not items_data:
        # No content today, create empty report
        if not report:
            report = DailyReport(
                report_date=today,
                weekday=weekday,
                status="ERROR",
                overview="今日暂无分析数据，请先同步信源并等待 AI 分析完成。",
            )
            db.add(report)
            await db.flush()
            await db.commit()
            return report
        return report

    # Build prompt
    items_text = ""
    # Build a title→url mapping for fallback matching
    title_url_map: dict[str, str] = {}
    for i, item in enumerate(items_data[:15], 1):  # limit to top 15
        items_text += f"\n{i}. [{item['category']}] {item['title']}"
        items_text += f"\n   来源: {item['source_name']} | URL: {item.get('url', '')} | 创作:{item['creator_score']} 爆文:{item['viral_score']} 质量:{item['quality_score']} 风险:{item['risk_score']}"
        if item['summary']:
            items_text += f"\n   摘要: {item['summary'][:100]}"
        title_url_map[item['title']] = item.get('url', '')

    prompt = REPORT_PROMPT.format(date=today, items_text=items_text)

    # Update or create report record
    if not report:
        report = DailyReport(
            report_date=today,
            weekday=weekday,
            status="GENERATING",
            content_count=len(items_data),
            analyzed_count=len(items_data),
        )
        db.add(report)
        await db.flush()
    else:
        report.status = "GENERATING"
        report.content_count = len(items_data)
        report.analyzed_count = len(items_data)
        await db.flush()

    try:
        result = await call_llm_json([{"role": "user", "content": prompt}])

        report.overview = result.get("overview", "")
        report.takeaway = result.get("takeaway", "")
        report.keywords = json.dumps(result.get("keywords", []), ensure_ascii=False)
        report.trends = json.dumps(result.get("trends", []), ensure_ascii=False)

        # Enrich top_picks with source_url via title matching fallback
        picks = result.get("top_picks", [])
        for pick in picks:
            pick_url = pick.get("source_url", "")
            if not pick_url or not pick_url.startswith("http"):
                # Fuzzy match: find the best matching title
                pick_title = pick.get("title", "")
                best_url = ""
                best_len = 0
                for t, u in title_url_map.items():
                    if u and (pick_title in t or t in pick_title):
                        if len(t) > best_len:
                            best_url = u
                            best_len = len(t)
                if best_url:
                    pick["source_url"] = best_url

        report.top_picks = json.dumps(picks, ensure_ascii=False)
        report.platform_tips = json.dumps(result.get("platform_tips", {}), ensure_ascii=False)
        report.topic_count = len(result.get("top_picks", []))
        report.status = "DONE"
        report.updated_at = datetime.utcnow()
        await db.commit()
    except Exception as e:
        report.status = "ERROR"
        report.overview = f"生成失败: {str(e)[:200]}"
        await db.commit()

    return report
