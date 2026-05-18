"""
Content classification and tag extraction service.

Uses keyword matching to classify content into predefined categories
and extract relevant tags from text.
"""

from __future__ import annotations

import re
from collections import Counter

# ── Category definitions ──────────────────────────────────────────────
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
    Classify *text* (title + summary) into one of the predefined categories.

    Returns the category with the most keyword hits; falls back to "其他".
    """
    if not text:
        return "其他"

    text_lower = text.lower()

    # Count keyword hits per category
    scores: Counter[str] = Counter()
    for keyword, category in _KEYWORD_MAP.items():
        # Use word-boundary-aware search where possible; simple `in` for Chinese
        if keyword in text_lower:
            scores[category] += 1

    if not scores:
        return "其他"

    return scores.most_common(1)[0][0]


def extract_tags(text: str, max_tags: int = 5) -> list[str]:
    """
    Extract relevant keyword tags from *text*.

    Scans the text against all known keywords and returns the ones that appear,
    ranked by frequency of occurrence.  Up to *max_tags* are returned.
    """
    if not text:
        return []

    text_lower = text.lower()

    # Find all matching keywords
    matched: Counter[str] = Counter()
    for keyword in _KEYWORD_MAP:
        # Count occurrences
        count = text_lower.count(keyword)
        if count > 0:
            matched[keyword] = count

    # Sort by count descending, then alphabetically for stability
    sorted_tags = sorted(matched.keys(), key=lambda k: (-matched[k], k))
    return sorted_tags[:max_tags]
