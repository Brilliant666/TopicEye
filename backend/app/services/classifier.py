"""
Content classification and tag extraction service.

Dual-mode classifier:
- **Async (LLM)**: Uses AI to dynamically classify content into existing
  or new categories. New categories are auto-registered in the database.
- **Sync (keyword fallback)**: Pure keyword matching for when LLM is
  unavailable (startup, rate-limit, offline).

The sync path is unchanged from the original implementation and serves as
a zero-dependency fallback.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Keyword-based fallback (unchanged) ─────────────────────────────────

CATEGORIES: list[str] = [
    "AI", "职场", "商业", "教育", "自媒体", "科技", "生活", "产品", "情感", "其他",
]

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI": [
        "AI", "GPT", "ChatGPT", "LLM", "OpenAI", "Claude", "DeepSeek",
        "大模型", "人工智能", "机器学习", "Agent", "Prompt", "transformer",
        "diffusion", "RAG", "fine-tune", "微调", "神经网络", "深度学习",
    ],
    "职场": [
        "职场", "工作", "月薪", "跳槽", "副业", "辞职", "转行", "打工人",
        "上班", "摸鱼", "简历", "面试", "offer", "薪资", "加班", "晋升",
    ],
    "商业": [
        "商业", "创业", "融资", "上市", "商业模式", "变现", "营收", "电商",
        "投资", "IPO", "独角兽", "B2B", "B2C", "SaaS", "利润", "亏损",
    ],
    "教育": [
        "教育", "考研", "考公", "学习", "课程", "学历", "大学", "培训",
        "考试", "高考", "留学", "英语", "备考", "上岸", "知识付费",
    ],
    "自媒体": [
        "自媒体", "涨粉", "运营", "IP", "粉丝", "账号", "内容创作", "博主",
        "短视频", "直播", "带货", "流量", "爆款", "选题", "MCN",
    ],
    "科技": [
        "科技", "Apple", "WWDC", "iOS", "Android", "芯片", "手机", "硬件",
        "开源", "Google", "Microsoft", "Meta", "特斯拉", "5G", "云计算",
        "量子", "无人机", "机器人", "半导体",
    ],
    "生活": [
        "生活", "旅行", "美食", "健康", "健身", "穿搭", "宠物", "家居",
        "装修", "租房", "理财", "保险", "养老", "收纳", "极简",
    ],
    "产品": [
        "产品", "用户体验", "需求", "设计", "功能", "竞品", "发布", "更新",
        "MVP", "迭代", "原型", "交互", "UI", "UX", "AB测试", "PM",
    ],
    "情感": [
        "情感", "恋爱", "婚姻", "分手", "暗恋", "表白", "离婚", "相亲",
        "异地恋", "三观", "星座", "治愈", "孤独", "成长",
    ],
}

# Build a flat keyword -> category lookup (lower-case for matching)
_KEYWORD_MAP: dict[str, str] = {}
for _cat, _kws in CATEGORY_KEYWORDS.items():
    for _kw in _kws:
        _KEYWORD_MAP[_kw.lower()] = _cat


def classify(text: str) -> str:
    """
    Sync keyword-based classification (fallback).

    Returns the category with the most keyword hits; falls back to "其他".
    """
    if not text:
        return "其他"

    text_lower = text.lower()
    scores: Counter[str] = Counter()
    for keyword, category in _KEYWORD_MAP.items():
        if keyword in text_lower:
            scores[category] += 1

    if not scores:
        return "其他"

    return scores.most_common(1)[0][0]


def extract_tags(text: str, max_tags: int = 5) -> list[str]:
    """
    Extract relevant keyword tags from *text* (sync fallback).
    """
    if not text:
        return []

    text_lower = text.lower()
    matched: Counter[str] = Counter()
    for keyword in _KEYWORD_MAP:
        count = text_lower.count(keyword)
        if count > 0:
            matched[keyword] = count

    sorted_tags = sorted(matched.keys(), key=lambda k: (-matched[k], k))
    return sorted_tags[:max_tags]


# ── LLM-powered async classification ────────────────────────────────────

async def classify_async(
    title: str,
    summary: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Classify content using LLM with dynamic category discovery.

    Returns:
        {
            "category": str,          # 分类名称
            "tags": list[str],        # 关键词标签
            "is_new_category": bool,  # 是否为新发现的分类
            "confidence": float,      # 置信度
        }

    Falls back to keyword-based classification on any error.
    """
    from app.repositories.category_repo import CategoryRepository
    from app.services.llm import call_llm_json
    from app.services.llm.prompts.classification import (
        SYSTEM_PROMPT,
        CLASSIFICATION_PROMPT,
    )

    cat_repo = CategoryRepository(db)

    # Get current category list for the prompt
    category_names = await cat_repo.get_active_names()

    # If no categories in DB yet, use the hardcoded list as seed
    if not category_names:
        category_names = CATEGORIES.copy()

    categories_str = "、".join(category_names)
    text_input = f"{title} {summary}".strip()

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": CLASSIFICATION_PROMPT.format(
                    categories=categories_str,
                    title=title,
                    summary=summary or "无摘要",
                ),
            },
        ]

        result = await call_llm_json(
            messages,
            temperature=0.1,
            max_tokens=300,
        )

        category = result.get("category", "").strip()
        tags = result.get("tags", [])
        is_new = result.get("is_new_category", False)
        confidence = result.get("confidence", 0.5)

        if not category:
            raise ValueError("Empty category from LLM")

        # Auto-register new category
        if is_new:
            try:
                await cat_repo.get_or_create(
                    name=category,
                    description=f"LLM自动发现的分类",
                    is_auto_created=True,
                )
            except Exception as e:
                logger.warning("Failed to auto-create category '%s': %s", category, e)

        return {
            "category": category,
            "tags": tags if isinstance(tags, list) else [],
            "is_new_category": is_new,
            "confidence": confidence,
        }

    except Exception as exc:
        logger.warning(
            "LLM classification failed, falling back to keywords: %s", exc
        )
        category = classify(text_input)
        tags = extract_tags(text_input)
        return {
            "category": category,
            "tags": tags,
            "is_new_category": False,
            "confidence": 0.3,
        }


async def seed_categories(db: AsyncSession) -> int:
    """
    Initialize the categories table with seed data from the hardcoded list.

    Run once on first startup (or when DB is fresh).
    Returns the number of categories created.
    """
    from app.repositories.category_repo import CategoryRepository

    cat_repo = CategoryRepository(db)
    created = 0

    for name, keywords in CATEGORY_KEYWORDS.items():
        existing = await cat_repo.get_by_name(name)
        if not existing:
            await cat_repo.create(
                name=name,
                description=f"{name}相关内容",
                keywords=",".join(keywords),
                is_auto_created=False,
                is_active=True,
                content_count=0,
            )
            created += 1

    # Also add "其他" if missing
    other = await cat_repo.get_by_name("其他")
    if not other:
        await cat_repo.create(
            name="其他",
            description="未匹配到具体分类的内容",
            is_auto_created=False,
            is_active=True,
            content_count=0,
        )
        created += 1

    if created > 0:
        logger.info("Seeded %d categories", created)

    return created
