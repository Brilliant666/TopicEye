"""
知乎盐选专栏 API。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.zhihu import ZhihuAlbum, ZhihuCategory

router = APIRouter(prefix='/zhihu', tags=['知乎'])


@router.get('/albums')
async def list_albums(
    category: Optional[str] = Query(None, description='一级分类名'),
    subcategory: Optional[str] = Query(None, description='二级分类名（如 爱情、科幻）'),
    sort_type: str = Query('hottest', description='排序类型'),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """知乎盐选专辑列表（支持分类+子分类+排序过滤）。"""
    query = select(ZhihuAlbum).where(ZhihuAlbum.sort_type == sort_type)
    if category:
        query = query.where(ZhihuAlbum.category1_name == category)
    if subcategory:
        query = query.where(ZhihuAlbum.category2_name == subcategory)
    query = query.order_by(desc(ZhihuAlbum.position)).limit(limit).offset(offset)

    result = await db.execute(query)
    albums = result.scalars().all()

    count_q = select(func.count()).select_from(ZhihuAlbum).where(ZhihuAlbum.sort_type == sort_type)
    if category:
        count_q = count_q.where(ZhihuAlbum.category1_name == category)
    if subcategory:
        count_q = count_q.where(ZhihuAlbum.category2_name == subcategory)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    return {
        'sort_type': sort_type,
        'category': category or '',
        'count': len(albums),
        'total': total,
        'offset': offset,
        'albums': [
            {
                'business_id': a.business_id,
                'title': a.title,
                'author': a.author,
                'author_desc': a.author_desc,
                'abstract': a.abstract,
                'thumb_url': a.thumb_url,
                'chapter_text': a.chapter_text,
                'price_yuan': a.price_yuan,
                'price': a.price,
                'is_exclusive': a.is_exclusive,
                'is_svip': a.is_svip,
                'online_time_text': a.online_time_text,
                'tag': a.tag,
                'category1_name': a.category1_name,
                'category2_name': a.category2_name,
                'position': a.position,
                'rank_pos_diff': a.rank_pos_diff,
                'sort_type': a.sort_type,
                'url': a.url,
            }
            for a in albums
        ],
    }


@router.get('/categories')
async def list_categories(
    parent_id: Optional[str] = Query(None, description='父分类 ID，null 表示一级分类'),
    db: AsyncSession = Depends(get_db),
):
    """知乎盐选分类列表。"""
    if parent_id:
        query = select(ZhihuCategory).where(ZhihuCategory.parent_id == parent_id).order_by(ZhihuCategory.sort)
    else:
        query = select(ZhihuCategory).where(ZhihuCategory.parent_id == None).order_by(ZhihuCategory.sort)

    result = await db.execute(query)
    cats = result.scalars().all()

    return {
        'count': len(cats),
        'categories': [
            {
                'zhihu_id': c.zhihu_id,
                'name': c.name,
                'name_en': c.name_en,
                'level': c.level,
                'parent_id': c.parent_id,
                'sort': c.sort,
                'artwork': c.artwork,
            }
            for c in cats
        ],
    }


@router.post('/sync')
async def sync_zhihu(
    background_tasks: BackgroundTasks,
):
    """触发知乎全量同步（后台运行）。"""
    from app.services.zhihu_service import sync_zhihu_ranks
    background_tasks.add_task(sync_zhihu_ranks)
    return {'status': 'syncing', 'message': '知乎榜单后台同步已启动'}