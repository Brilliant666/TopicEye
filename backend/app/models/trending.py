"""
TrendingItem — 趋势雷达榜单条目。

和 ContentItem 不同：
- 不走 LLM 分类/精选，纯抓取展示
- 按批次替换（每次同步清空旧数据）
- 有热度值和排名，有自然过期
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, DateTime, Enum, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TrendingCategory(str, enum.Enum):
    HOT = "hot"              # 热点
    TECH = "tech"            # 科技
    FINANCE = "finance"      # 财经
    ENTERTAINMENT = "entertainment"  # 娱乐
    COMMUNITY = "community"  # 社区


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


class TrendingItem(Base):
    __tablename__ = "trending_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 信源标识
    source: Mapped[str] = mapped_column(Enum(TrendingSource), nullable=False, index=True)
    category: Mapped[str] = mapped_column(Enum(TrendingCategory), nullable=False, index=True)
    # 内容
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    hot_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hot_value_raw: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    trend: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # up/down/new/stable
    cover_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # 元数据
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 批次ID，用于清理
