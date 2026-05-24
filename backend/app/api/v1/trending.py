"""
趋势雷达 API — GET /api/v1/trending
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.trending import TrendingItem, TrendingCategory, TrendingSource
from app.services.trending_pipeline import sync_trending_source, sync_all_trending

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trending", tags=["trending"])


class TrendingItemOut(BaseModel):
    id: int
    source: str
    category: str
    rank: int
    title: str
    url: str
    hot_value: int
    hot_value_raw: str
    trend: Optional[str] = None
    cover_url: Optional[str] = None
    extra: Optional[dict] = None

    class Config:
        from_attributes = True


class TrendingSourceInfo(BaseModel):
    source: str
    category: str
    count: int


@router.get("", response_model=list[TrendingItemOut])
async def get_trending(
    category: Optional[str] = Query(None, description="分类筛选: hot/tech/finance/entertainment/community"),
    source: Optional[str] = Query(None, description="信源筛选: weibo/baidu/douyin/..."),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取趋势雷达数据。支持按分类和信源筛选。"""
    stmt = select(TrendingItem)

    if category:
        try:
            cat_enum = TrendingCategory(category)
            stmt = stmt.where(TrendingItem.category == cat_enum)
        except ValueError:
            pass
    if source:
        try:
            src_enum = TrendingSource(source)
            stmt = stmt.where(TrendingItem.source == src_enum)
        except ValueError:
            pass

    stmt = stmt.order_by(TrendingItem.source, TrendingItem.rank).limit(limit * 10)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return items


@router.get("/sources", response_model=list[TrendingSourceInfo])
async def get_trending_sources(
    db: AsyncSession = Depends(get_db),
):
    """获取所有趋势源及其条目数量。"""
    stmt = (
        select(
            TrendingItem.source,
            TrendingItem.category,
            func.count(TrendingItem.id).label("count"),
        )
        .group_by(TrendingItem.source, TrendingItem.category)
        .order_by(TrendingItem.category, TrendingItem.source)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        TrendingSourceInfo(source=row[0], category=row[1], count=row[2])
        for row in rows
    ]


@router.post("/sync/{source_name}")
async def trigger_sync(
    source_name: str,
    db: AsyncSession = Depends(get_db),
):
    """手动触发单个趋势源同步。"""
    result = await sync_trending_source(source_name, db)
    return result


@router.post("/sync-all")
async def trigger_sync_all(
    db: AsyncSession = Depends(get_db),
):
    """手动触发所有趋势源同步。"""
    results = await sync_all_trending(db)
    return results


@router.get("/cross-platform")
async def get_cross_platform(
    min_resonance: int = Query(1, ge=1, le=10, description="最小共振平台数"),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """跨平台热点交叉发现。

    对所有趋势数据做标题聚类，找出在多平台同时出现的热点话题。
    resonance >= 3 为"高共振"，值得关注。
    """
    from app.services.trending_cross import cluster_trending_items

    # 取全部数据
    stmt = select(TrendingItem).order_by(TrendingItem.source, TrendingItem.rank)
    result = await db.execute(stmt)
    items = result.scalars().all()

    # 转成 dict 列表给聚类函数
    item_dicts = [
        {
            "id": it.id,
            "source": it.source.name if hasattr(it.source, "name") else str(it.source),
            "category": it.category.name if hasattr(it.category, "name") else str(it.category),
            "rank": it.rank,
            "title": it.title,
            "url": it.url,
            "hot_value": it.hot_value,
            "hot_value_raw": it.hot_value_raw,
            "trend": it.trend,
            "extra": it.extra,
        }
        for it in items
    ]

    clusters = cluster_trending_items(item_dicts)

    # 过滤最小共振数
    clusters = [c for c in clusters if c["resonance"] >= min_resonance]

    # 限制返回数量
    clusters = clusters[:limit]

    # 清理内部字段
    for c in clusters:
        for it in c.get("items", []):
            it.pop("_keywords", None)

    return {
        "total": len(clusters),
        "clusters": clusters,
    }


class AngleRecommendOut(BaseModel):
    common_angles: list[str]
    contrast_angles: list[dict[str, str]]
    angle_note: str


@router.get("/angles")
async def get_topic_angles(
    topic: str = Query(..., description="话题标题"),
    db: AsyncSession = Depends(get_db),
):
    """为指定话题生成创作角度推荐。

    基于卡兹克方法论：
    - 大众角度（第一直觉想到的不能写）
    - 反差角度（陌生化，情理之中预料之外）
    """
    from app.services.angle_recommend import generate_angles_for_topic

    # 从 DB 找到相关趋势条目，拼出各平台标题
    # 转义 LIKE 通配符，防止用户输入 %/_ 泄露非预期数据
    safe_topic = topic[:8].replace('%', '\\%').replace('_', '\\_')
    stmt = (
        select(TrendingItem)
        .where(TrendingItem.title.like(f"%{safe_topic}%"))
        .order_by(TrendingItem.rank)
        .limit(8)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    if not items:
        return {"common_angles": [], "contrast_angles": [], "angle_note": "未找到相关话题数据"}

    platform_titles = [it.title for it in items]

    # 取第一个作为代表
    rep_item = items[0]
    keywords: list[str] = []
    if rep_item.extra and isinstance(rep_item.extra, dict):
        keywords = rep_item.extra.get("keywords", [])

    angles = await generate_angles_for_topic(
        topic=topic,
        keywords=keywords,
        platform_titles=platform_titles,
    )
    return angles
