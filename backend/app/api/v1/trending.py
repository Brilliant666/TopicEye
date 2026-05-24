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
