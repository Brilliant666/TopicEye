"""
AI Analysis service — single-pass analysis with curation scoring.

One LLM call produces: summary, 6-dim scores, curation_score, tags,
recommendation, creator angles, and title suggestions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    # Extract scores
    scores = result.get("scores", {})
    for key in ["quality_score", "hot_score", "freshness_score", "creator_score", "viral_score", "risk_score"]:
        val = scores.get(key, 50)
        scores[key] = max(0, min(100, float(val)))

    # Extract curation
    curation = result.get("curation", {})
    curation_score = max(0, min(100, float(curation.get("curation_score", 0))))

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
        try:
            item.status = ContentStatus.ANALYZING
            await db.flush()

            analysis = await analyze_content(item, db)
            results.append(analysis)
            await db.commit()
        except Exception as e:
            logger.error("Failed to analyze content id=%d: %s", item.id, e)
            await db.rollback()
            item.status = ContentStatus.ERROR
            await db.commit()

    return results
