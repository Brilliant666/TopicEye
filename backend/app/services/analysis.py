"""
AI Analysis service — single-pass analysis with curation scoring.

One LLM call produces: summary, 6-dim scores, curation_score, tags,
recommendation, creator angles, and title suggestions.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sqlite_retry import is_sqlite_locked, retry_sqlite_locked
from app.models.content import ContentItem, ContentStatus
from app.models.analysis import AiAnalysis
from app.services.llm import call_llm_json
from app.services.llm.prompts.analysis import (
    SYSTEM_PROMPT,
    ANALYSIS_PROMPT,
    SYSTEM_PROMPT_EN,
    ANALYSIS_PROMPT_EN,
)
from app.services.content_read_cache import invalidate_content_read_caches

logger = logging.getLogger(__name__)

# ── Language detection (no external deps) ─────────────────────────────

def _detect_lang(title: str, content: str) -> str:
    """Detect whether content is primarily Chinese or English.
    
    Uses character-range heuristics: CJK range vs Latin ASCII letters.
    Returns 'en' if ASCII letters dominate the sample, else 'zh'.
    """
    sample = (title + " " + content)[:500]
    ascii_letters = sum(1 for c in sample if c.isascii() and c.isalpha())
    cjk_chars = sum(1 for c in sample if "\u4e00" <= c <= "\u9fff")
    # If we have meaningful CJK content, prefer Chinese
    if cjk_chars >= 10:
        return "zh"
    if ascii_letters >= 20 and ascii_letters / max(ascii_letters + cjk_chars, 1) > 0.6:
        return "en"
    return "zh"


def _valid_analysis_result(result: dict[str, Any]) -> bool:
    """Return whether the model result contains the minimum analysis contract."""
    return isinstance(result.get("scores"), dict) and isinstance(result.get("curation"), dict)


def _clamp_score(value: Any, default: float = 50) -> float:
    try:
        return max(0, min(100, float(value)))
    except (TypeError, ValueError):
        return default


def _local_analysis_result(content: ContentItem, *, lang: str) -> dict[str, Any]:
    """Build a deterministic baseline analysis when the LLM response is empty."""
    text = f"{content.title}\n{content.summary or ''}\n{content.raw_content or ''}".strip()
    source = f"{content.source_name or ''} {content.source_type or ''} {content.platform or ''}".lower()
    title = content.title.strip()
    text_len = len(text)
    has_content = text_len >= 80
    is_trend_source = any(key in source for key in ("hot", "trend", "rsshub", "zhihu", "reddit", "weread"))

    quality_score = 62 if has_content else 48
    hot_score = 68 if is_trend_source else 55
    creator_score = 64 if has_content else 50
    viral_score = 58 if is_trend_source else 50
    freshness_score = 70
    risk_score = 28
    curation_score = round(
        quality_score * 0.28
        + creator_score * 0.28
        + hot_score * 0.18
        + freshness_score * 0.14
        + viral_score * 0.12,
        1,
    )

    words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{2,}", text)
    tags: list[str] = []
    for word in words:
        if word not in tags:
            tags.append(word)
        if len(tags) >= 5:
            break
    if content.category and content.category not in tags:
        tags.insert(0, content.category)

    summary = content.summary or title
    if len(summary) > 180:
        summary = summary[:180].rstrip() + "..."

    if lang == "en":
        recommendation = f"这条内容来自 {content.source_name or '外部信源'}，适合作为跨市场趋势素材先观察，再结合中文语境提炼选题角度。"
    else:
        recommendation = f"这条内容来自 {content.source_name or '外部信源'}，具备基础选题信号，建议先作为素材进入观察池，再补充数据和角度判断。"

    return {
        "summary": summary,
        "key_points": [summary],
        "recommendation": recommendation,
        "creator_angles": [
            f"从创作者视角拆解「{title[:32]}」的用户关注点",
            "结合评论、搜索热度或同类案例补充证据后成稿",
        ],
        "title_suggestions": [title],
        "risk_notes": "",
        "tags": tags,
        "scores": {
            "quality_score": quality_score,
            "hot_score": hot_score,
            "freshness_score": freshness_score,
            "creator_score": creator_score,
            "viral_score": viral_score,
            "risk_score": risk_score,
        },
        "curation": {
            "curation_score": curation_score,
            "info_density": 60 if has_content else 45,
            "actionability": 58 if has_content else 45,
            "source_weight": 58 if is_trend_source else 50,
        },
        "fallback": "local_empty_llm_response",
    }


# ── Core analysis function ───────────────────────────────────────

async def analyze_content(content: ContentItem, db: AsyncSession) -> AiAnalysis:
    """Run full AI analysis on a single content item (single LLM call)."""
    logger.info("Analyzing content id=%d: %s", content.id, content.title[:50])

    content_text = content.raw_content or content.summary or ""
    title = content.title
    truncated = content_text[:3000] if content_text else "无正文内容"

    # Select language-appropriate prompt
    lang = _detect_lang(title, content_text or "")
    if lang == "en":
        system_prompt = SYSTEM_PROMPT_EN
        analysis_prompt = ANALYSIS_PROMPT_EN
        logger.info("Detected English content, using EN prompts for content id=%d", content.id)
    else:
        system_prompt = SYSTEM_PROMPT
        analysis_prompt = ANALYSIS_PROMPT

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": analysis_prompt.format(title=title, content=truncated)},
    ]

    result = await call_llm_json(messages, temperature=0.25, max_tokens=1500, scene="content_analysis")
    if not _valid_analysis_result(result):
        logger.warning(
            "LLM analysis result invalid for content id=%d, using local fallback: %s",
            content.id,
            str(result)[:200],
        )
        result = _local_analysis_result(content, lang=lang)

    # Extract scores
    scores = result.get("scores", {})
    for key in ["quality_score", "hot_score", "freshness_score", "creator_score", "viral_score", "risk_score"]:
        scores[key] = _clamp_score(scores.get(key), 50)

    # Extract curation
    curation = result.get("curation", {})
    curation_score = _clamp_score(curation.get("curation_score"), 0)

    # Cross-market bonus: English content from HN/Reddit has higher signal value
    # for Chinese-speaking creators (early trend detection before mainstream coverage)
    if lang == "en":
        source_name = (content.source_name or "").lower()
        platform = (content.platform or "").lower()
        is_intl = any(kw in source_name for kw in ("hacker", "reddit", "techcrunch", "arxiv", "github"))
        is_intl = is_intl or any(kw in platform for kw in ("hacker", "reddit"))
        if is_intl and curation_score >= 55:
            bonus = min(10, 100 - curation_score)  # cap at 100
            curation_score += bonus
            logger.info(
                "Cross-market bonus +%d for content id=%d (source=%s, curation=%.0f)",
                bonus, content.id, content.source_name, curation_score,
            )

    # Build analysis record
    analysis = AiAnalysis(
        content_id=content.id,
        quality_score=scores.get("quality_score", 0),
        hot_score=scores.get("hot_score", 0),
        freshness_score=scores.get("freshness_score", 0),
        creator_score=scores.get("creator_score", 0),
        viral_score=scores.get("viral_score", 0),
        risk_score=scores.get("risk_score", 0),
        summary=result.get("summary", ""),
        key_points=result.get("key_points"),
        audience_emotion="",
        recommended_reason=result.get("recommendation"),
        creator_angles=result.get("creator_angles"),
        title_suggestions=result.get("title_suggestions"),
        risk_notes={"notes": result.get("risk_notes", "") if scores.get("risk_score", 0) > 50 else ""},
        # New curation fields
        curation_score=curation_score,
        tags=result.get("tags"),
        recommendation=result.get("recommendation"),
        info_density=curation.get("info_density"),
        actionability=curation.get("actionability"),
        source_weight=curation.get("source_weight"),
    )

    db.add(analysis)
    content.status = ContentStatus.ANALYZED
    await db.flush()
    await db.refresh(analysis)
    invalidate_content_read_caches()

    logger.info(
        "Analysis id=%d: Q=%.0f C=%.0f V=%.0f R=%.0f Curation=%.0f Tags=%s",
        content.id,
        analysis.quality_score or 0,
        analysis.creator_score or 0,
        analysis.viral_score or 0,
        analysis.risk_score or 0,
        analysis.curation_score or 0,
        analysis.tags,
    )

    return analysis


async def analyze_batch(
    content_ids: list[int],
    db: AsyncSession,
) -> list[AiAnalysis]:
    """Analyze multiple content items sequentially (respecting rate limits)."""
    results = []

    result = await db.execute(
        select(ContentItem).where(
            ContentItem.id.in_(content_ids),
            ContentItem.status == ContentStatus.PENDING,
        )
    )
    items = result.scalars().all()

    for item in items:
        content_id = item.id
        try:
            async def _mark_analyzing() -> None:
                await db.execute(
                    update(ContentItem)
                    .where(ContentItem.id == content_id)
                    .values(status=ContentStatus.ANALYZING)
                )
                await db.commit()

            await retry_sqlite_locked(
                _mark_analyzing,
                attempts=3,
                base_delay=0.1,
                on_retry=db.rollback,
            )

            content = await db.get(ContentItem, content_id)
            if content is None:
                continue

            analysis = await analyze_content(content, db)
            results.append(analysis)
            await db.commit()
        except Exception as e:
            await db.rollback()
            if is_sqlite_locked(e):
                logger.warning("Skipped analysis for content id=%d: database is locked", content_id)
                continue

            logger.error("Failed to analyze content id=%d: %s", content_id, e)
            try:
                content = await db.get(ContentItem, content_id)
                if content is not None:
                    content.status = ContentStatus.ERROR
                    await db.commit()
            except Exception as status_error:
                await db.rollback()
                logger.warning(
                    "Failed to mark content id=%d as error after analysis failure: %s",
                    content_id,
                    status_error,
                )

    return results
