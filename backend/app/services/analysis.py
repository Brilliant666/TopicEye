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
from app.services.llm import call_llm, call_llm_json

logger = logging.getLogger(__name__)

# ── Single-pass analysis prompt ──────────────────────────────────

SYSTEM_PROMPT = """你是一位资深内容策展分析师，负责评估内容的选题价值并决定是否入选精选。

你的评分标准参考了一线内容策展平台的精选规则：
- 信息密度（纯转发/一句话感想直接淘汰）
- 可操作性（能直接上手用的工具/教程得分更高）
- 相关性（必须和目标领域直接相关）
- 来源权威度（一手信源 > 二手转载）
- 时效性（首发/独家 > 已被广泛报道）

所有评分范围 0-100。所有文本使用中文。语气直接、有态度、不说客套话。"""

ANALYSIS_PROMPT = """请对以下内容进行完整分析。

标题：{title}
正文：{content}

请严格按以下 JSON 格式输出（不要输出任何其他内容）：
{{
  "summary": "一句话摘要（30字以内）",
  "key_points": ["核心观点1", "核心观点2", "核心观点3"],
  "tags": ["标签1", "标签2"],
  "scores": {{
    "quality_score": <0-100, 信息密度和逻辑性>,
    "hot_score": <0-100, 当前热度和传播速度>,
    "freshness_score": <0-100, 新鲜度和时效性>,
    "creator_score": <0-100, 对创作者的选题价值>,
    "viral_score": <0-100, 爆文传播潜力>,
    "risk_score": <0-100, 内容风险>
  }},
  "risk_notes": "风险说明文本或空字符串。规则：当risk_score大于50时，必须填写具体风险说明（如：话题敏感、可能引发争议、涉及未证实信息、版权风险等），20字以内；当risk_score小于等于50时，输出空字符串\"\"",
  "curation": {{
    "info_density": <0-100, 信息密度：纯转发/空话=0-20, 有观点=40-60, 有数据/案例/方法=70-100>,
    "actionability": <0-100, 可操作性：纯资讯=10-30, 有参考价值=40-60, 能直接上手用=70-100>,
    "source_weight": <0-100, 来源权威度：匿名/营销号=10-30, 二手转载=40-60, 一手信源/官方/KOL=70-100>,
    "curation_score": <0-100, 综合精选分（加权：信息密度30%+可操作性25%+创作者价值20%+爆文潜力15%+来源10%，风险分>70则扣20分）>
  }},
  "recommendation": "精选推荐理由（50字以内，内行视角点评。要求：①先说这事牛在哪或不同在哪（具体功能/数据/差异点，不要用'神器''炸裂'等夸大词）②点出谁该关注③给一个具体行动建议。风格：老手之间的推荐，不是营销号喊话。例：'一键转代码不稀奇，但兼容Cursor这套组合拳让它成了产设研协作的新选项，做项目的上手试试'）",
  "creator_angles": ["创作角度1", "创作角度2", "创作角度3"],
  "title_suggestions": ["建议标题1", "建议标题2", "建议标题3"]
}}

精选分（curation_score）评判标准：
- ≥80：重大发布/独家/强实用性工具/高传播力事件
- 70-79：扎实的产品更新/行业动态/有价值教程
- 60-69：有参考价值但不够突出
- <60：信息量低/纯情绪/重复内容/过于个人化

精选门槛为 60 分。"""


# ── Core analysis function ────────────────────────────────────────

async def analyze_content(content: ContentItem, db: AsyncSession) -> AiAnalysis:
    """Run full AI analysis on a single content item (single LLM call)."""
    logger.info("Analyzing content id=%d: %s", content.id, content.title[:50])

    content_text = content.raw_content or content.summary or ""
    title = content.title
    truncated = content_text[:3000] if content_text else "无正文内容"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": ANALYSIS_PROMPT.format(title=title, content=truncated)},
    ]

    result = await call_llm_json(messages, temperature=0.25, max_tokens=1500)

    # Extract scores
    scores = result.get("scores", {})
    for key in ["quality_score", "hot_score", "freshness_score", "creator_score", "viral_score", "risk_score"]:
        val = scores.get(key, 50)
        scores[key] = max(0, min(100, float(val)))

    # Extract curation
    curation = result.get("curation", {})
    curation_score = max(0, min(100, float(curation.get("curation_score", 0))))

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
