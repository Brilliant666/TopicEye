from __future__ import annotations
from typing import Optional
import enum
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SourceType(str, enum.Enum):
    RSS = "RSS"
    RSSHUB = "RSSHub"
    REDDIT = "Reddit"
    WEBSITE = "网站"
    WECHAT = "公众号"
    XIAOHONGSHU = "小红书"
    X = "X"
    YOUTUBE = "YouTube"
    BILIBILI = "B站"
    CUSTOM = "自定义"


class SourceStatus(str, enum.Enum):
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(Enum(SourceType), nullable=False, default=SourceType.RSS)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    keyword: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    contents: Mapped[list["ContentItem"]] = relationship(back_populates="source", cascade="all, delete-orphan")
