"""
番茄小说榜单 API。
提供分类列表、四大榜单、各分类书单。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.fanqie import FanqieCategory, FanqieBook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fanqie", tags=["番茄小说"])


# ── Pydantic 模型 ──────────────────────────────────────────────

class BookItem(BaseModel):
    book_id: str
    book_name: str
    author: str
    abstract: Optional[str]
    category_id: str
    category_name: Optional[str]
    thumb_uri: Optional[str]
    read_count: Optional[str]
    word_number: Optional[str]
    last_chapter_title: Optional[str]
    current_pos: int
    male_reading_pos: Optional[int]
    male_new_pos: Optional[int]
    female_reading_pos: Optional[int]
    female_new_pos: Optional[int]

    class Config:
        from_attributes = True


class CategoryItem(BaseModel):
    fanqie_id: str
    name: str
    group: str
    display_order: int

    class Config:
        from_attributes = True


class RankingItem(BaseModel):
    type: str
    label: str
    books: list[BookItem]


# ── API 端点 ───────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """返回所有番茄分类（按 group 和 display_order 排序）。"""
    result = await db.execute(
        select(FanqieCategory).order_by(
            FanqieCategory.group,
            FanqieCategory.display_order,
        )
    )
    cats = result.scalars().all()
    return [
        {"fanqie_id": c.fanqie_id, "name": c.name, "group": c.group}
        for c in cats
    ]


@router.get("/rankings")
async def list_rankings(
    type: Optional[str] = Query(None, description="male_reading/male_new/female_reading/female_new"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    返回四大榜单（或指定某榜单）。
    type 可选：male_reading / male_new / female_reading / female_new
    """
    types = [type] if type else ["male_reading", "male_new", "female_reading", "female_new"]
    labels = {
        "male_reading": "男频阅读榜",
        "male_new": "男频新书榜",
        "female_reading": "女频阅读榜",
        "female_new": "女频新书榜",
    }

    out = {}
    for rt in types:
        result = await db.execute(
            select(FanqieBook)
            .where(FanqieBook.rank_type == rt)
            .order_by(FanqieBook.current_pos)
            .limit(100)
        )
        books = result.scalars().all()
        out[rt] = {
            "label": labels.get(rt, rt),
            "count": len(books),
            "books": [
                {
                    "book_id": b.book_id,
                    "book_name": b.book_name,
                    "author": b.author,
                    "abstract": b.abstract,
                    "thumb_uri": b.thumb_uri,
                    "read_count": b.read_count,
                    "word_number": b.word_number,
                    "last_chapter_title": b.last_chapter_title,
                    "current_pos": b.current_pos,
                }
                for b in books
            ],
        }
    return out


@router.get("/category/{fanqie_id}/books")
async def category_books(
    fanqie_id: str,
    db: AsyncSession = Depends(get_db),
    rank_type: Optional[str] = Query(None, description="male_new/male_reading/female_new/female_reading"),
    gender: Optional[str] = Query(None, description="male / female"),
    limit: int = Query(20, le=100),
) -> dict:
    """
    返回指定分类下的图书。
    rank_type 可选，默认返回所有榜单类型。
    """
    query = select(FanqieBook).where(
        FanqieBook.category_id == fanqie_id,
    )

    if rank_type:
        query = query.where(FanqieBook.rank_type == rank_type)
    else:
        # 默认返回新书榜（有数据的）
        query = query.where(FanqieBook.rank_type.in_([
            "male_new", "female_new", "male_reading", "female_reading",
        ]))

    query = query.order_by(FanqieBook.current_pos).limit(limit)

    result = await db.execute(query)
    books = result.scalars().all()

    return {
        "fanqie_id": fanqie_id,
        "count": len(books),
        "books": [
            {
                "book_id": b.book_id,
                "book_name": b.book_name,
                "author": b.author,
                "abstract": b.abstract,
                "thumb_uri": b.thumb_uri,
                "read_count": b.read_count,
                "word_number": b.word_number,
                "last_chapter_title": b.last_chapter_title,
                "current_pos": b.current_pos,
                "rank_type": b.rank_type,
                "male_reading_pos": b.male_reading_pos,
                "female_reading_pos": b.female_reading_pos,
            }
            for b in books
        ],
    }


@router.post("/sync")
async def trigger_sync():
    """手动触发全量同步。"""
    import asyncio
    from app.services.fanqie_service import full_sync
    result = await full_sync()
    return result