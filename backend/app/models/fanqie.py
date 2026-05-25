"""
番茄小说榜单数据模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FanqieCategory(Base):
    """番茄分类。"""
    __tablename__ = "fanqie_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fanqie_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # "1141"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "西方奇幻"
    group: Mapped[str] = mapped_column(String(20), nullable=False)  # "male" / "female"
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_fanqie_cat_group", "group"),
    )


class FanqieBook(Base):
    """番茄榜单图书。"""
    __tablename__ = "fanqie_books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # "7320218217488600126"
    book_name: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(200))
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[str] = mapped_column(String(20), nullable=False)  # fanqie_id like "1141"
    category_name: Mapped[str] = mapped_column(String(100), nullable=True)
    thumb_uri: Mapped[Optional[str]] = mapped_column(String(1000))
    read_count: Mapped[Optional[str]] = mapped_column(String(50))  # "417817"
    word_number: Mapped[Optional[str]] = mapped_column(String(50))  # "2626537"
    last_chapter_title: Mapped[Optional[str]] = mapped_column(String(500))
    last_chapter_update_time: Mapped[Optional[int]] = mapped_column(Integer)
    current_pos: Mapped[int] = mapped_column(Integer, default=0)  # 榜单排名
    rank_type: Mapped[str] = mapped_column(String(30), nullable=False)  # male_reading / male_new / female_reading / female_new
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # 四个榜单各一个 pos
    male_reading_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    male_new_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    female_reading_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    female_new_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_fanqie_book_ranktype", "rank_type"),
        Index("ix_fanqie_book_cat", "category_id"),
    )