"""
TrendingSnapshot — 趋势雷达历史快照。

每天凌晨自动保存一份全量快照，保留15天。
用于：对比昨日排名、判断话题趋势（上升/下降/新上榜）。

和 TrendingItem 的区别：
- TrendingItem：实时数据，每次同步替换
- TrendingSnapshot：历史存档，永久保留15天
"""
from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import String, Integer, DateTime, Date, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TrendingSource(str, enum.Enum):
    WEIBO = "weibo"
    BAIDU = "baidu"
    DOUYIN = "douyin"
    TOUTIAO = "toutiao"
    ZHIHU = "zhihu"
    HUPU = "hupu"
    TIEBA = "tieba"
    ITHOME = "ithome"
    KR36 = "36kr"
    BILIBILI = "bilibili"
    JUEJIN = "juejin"
    SSPAI = "sspai"
    HACKERNEWS = "hackernews"
    GITHUB = "github"
    WALLSTREETCN = "wallstreetcn"
    CLS = "cls"
    XUEQIU = "xueqiu"
    EASTMONEY = "eastmoney"
    DOUBAN = "douban"
    IQIYI = "iqiyi"


class TrendingCategory(str, enum.Enum):
    HOT = "hot"
    TECH = "tech"
    FINANCE = "finance"
    ENTERTAINMENT = "entertainment"
    COMMUNITY = "community"


class TrendingItem(Base):
    __tablename__ = "trending_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Enum(TrendingSource), nullable=False, index=True)
    category: Mapped[str] = mapped_column(Enum(TrendingCategory), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    hot_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hot_value_raw: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    trend: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # up/down/new/stable
    cover_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)


class TrendingSnapshot(Base):
    """
    趋势雷达每日快照。
    每天保存一条记录，包含该日该平台的全量榜单（JSON数组）。
    保留15天，APScheduler 定时清理超期数据。
    """
    __tablename__ = "trending_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(Enum(TrendingSource), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="hot")
    # items JSON 格式: [{"rank":1,"title":"...","url":"...","hot_value":123456,"hot_value_raw":"123万"}, ...]
    items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # 唯一约束：每天每个source只有一条快照
    __table_args__ = (
        # 复合唯一: (snapshot_date, source)
        # SQLite 不支持带表达式的唯一约束，用程序层控制
    )