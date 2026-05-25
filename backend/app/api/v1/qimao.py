"""
七猫小说 API。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Query, Depends, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.qimao import QimaoBook

router = APIRouter(prefix="/qimao", tags=["qimao"])


@router.get("/rankings")
async def rankings(
    db: AsyncSession = Depends(get_db),
    channel: str = Query("boy", description="boy / girl"),
):
    """各榜单概览：每个榜单有多少本。"""
    rows = await db.execute(
        select(
            QimaoBook.channel,
            QimaoBook.rank_type,
            func.count(QimaoBook.id).label("count"),
        )
        .where(QimaoBook.channel == channel)
        .group_by(QimaoBook.channel, QimaoBook.rank_type)
    )
    result = {}
    for row in rows:
        result[row.rank_type] = {"count": row.count, "channel": row.channel}
    return result


@router.get("/books")
async def list_books(
    channel: str = Query("boy", description="boy / girl"),
    rank_type: str = Query("hot", description="hot / new / over / collect / update"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """指定榜单的图书列表。"""
    rows = await db.execute(
        select(QimaoBook)
        .where(QimaoBook.channel == channel, QimaoBook.rank_type == rank_type)
        .order_by(QimaoBook.position)
        .offset(offset)
        .limit(limit)
    )
    books = rows.scalars().all()
    return {
        "channel": channel,
        "rank_type": rank_type,
        "count": len(books),
        "books": [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "abstract": b.abstract,
                "category1_name": b.category1_name,
                "category2_name": b.category2_name,
                "thumb_uri": b.thumb_uri,
                "words_num": b.words_num,
                "collect_count": b.collect_count,
                "latest_chapter_title": b.latest_chapter_title,
                "update_time": b.update_time,
                "is_over": b.is_over,
                "is_continue_top": b.is_continue_top,
                "index_change": b.index_change,
                "position": b.position,
            }
            for b in books
        ],
    }


@router.post("/sync")
async def sync_qimao(background_tasks: BackgroundTasks):
    """后台触发七猫全量同步（耗时约 40s）。"""
    async def _run():
        from app.services.qimao_service import sync_qimao_ranks
        await sync_qimao_ranks()
    background_tasks.add_task(_run)
    return {"status": "started", "message": "七猫同步已在后台启动，预计 40s 内完成"}