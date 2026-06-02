from __future__ import annotations

from typing import Any


PLAN_TIERS: list[dict[str, Any]] = [
    {
        "key": "free",
        "name": "免费版",
        "price_label": "0 元",
        "positioning": "验证每日选题价值，适合个人创作者试用。",
        "highlight": "每天发现少量值得写的选题。",
        "features": [
            "每日查看部分今日选题",
            "基础摘要",
            "基础推荐理由",
            "少量收藏",
            "基础信源浏览",
        ],
        "limits": {
            "daily_topic_view": 20,
            "favorites": 30,
            "custom_sources": 0,
            "creation_plans_per_day": 3,
            "team_members": 1,
        },
        "cta": "开始免费使用",
        "recommended": False,
    },
    {
        "key": "pro",
        "name": "Pro 版",
        "price_label": "19-49 元/月",
        "positioning": "面向稳定更新的单人创作者。",
        "highlight": "把选题发现转成可执行内容方案。",
        "features": [
            "查看全部今日选题",
            "查看低粉爆文",
            "AI 选题转化",
            "小红书爆款浏览",
            "收藏夹工作流",
            "每日 Brief",
        ],
        "limits": {
            "daily_topic_view": -1,
            "favorites": 500,
            "custom_sources": 10,
            "creation_plans_per_day": 50,
            "team_members": 1,
        },
        "cta": "规划 Pro 功能",
        "recommended": True,
    },
    {
        "key": "studio",
        "name": "Studio 版",
        "price_label": "99-199 元/月",
        "positioning": "面向工作室、矩阵号和内容团队。",
        "highlight": "把信源、批量分析和协作沉淀成选题库。",
        "features": [
            "自定义信源",
            "批量选题分析",
            "竞品账号监控",
            "导出选题库",
            "团队成员",
            "策略配置",
        ],
        "limits": {
            "daily_topic_view": -1,
            "favorites": 3000,
            "custom_sources": 100,
            "creation_plans_per_day": 300,
            "team_members": 5,
        },
        "cta": "规划 Studio 功能",
        "recommended": False,
    },
    {
        "key": "enterprise",
        "name": "企业版",
        "price_label": "定制",
        "positioning": "面向垂直行业内容团队和私有化场景。",
        "highlight": "行业信源、组织协同和专属策略模型。",
        "features": [
            "专属行业信源库",
            "私有部署",
            "团队协作",
            "API 接入",
            "企业微信/飞书推送",
            "专属策略模型",
        ],
        "limits": {
            "daily_topic_view": -1,
            "favorites": -1,
            "custom_sources": -1,
            "creation_plans_per_day": -1,
            "team_members": -1,
        },
        "cta": "联系定制",
        "recommended": False,
    },
]


FREE_AREA = [
    "今日选题的有限浏览",
    "内容基础摘要和推荐理由",
    "少量收藏和基础状态流转",
    "信源列表浏览",
    "邮箱登录和个人工作区",
]


PAID_AREA = [
    "全部今日选题和低粉爆文",
    "AI 选题转内容方案",
    "自定义信源和批量导入",
    "竞品账号监控",
    "每日 Brief 和导出选题库",
    "团队协作、API 接入和私有部署",
]


def get_plan_catalog() -> dict[str, Any]:
    return {
        "tiers": PLAN_TIERS,
        "free_area": FREE_AREA,
        "paid_area": PAID_AREA,
        "currency": "CNY",
        "source": "docs/创作者选题雷达_1_0_prd_融合版.md#商业模式初稿",
    }
