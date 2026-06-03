from __future__ import annotations

from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
from pydantic import BaseModel, Field, field_validator
from app.models.source import SourceType, SourceStatus


def normalize_source_url_value(value: str) -> str:
    url = value.strip()
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in {"http", "https"} and parts.netloc:
        netloc = parts.netloc.lower()
        return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))
    raise ValueError("信源 URL 必须以 http:// 或 https:// 开头")


def normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


class SourceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    source_type: SourceType = SourceType.RSS
    url: str = Field(..., max_length=1024)
    keyword: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    weight: int = Field(default=3, ge=1, le=5)
    sort_order: Optional[int] = Field(default=None, ge=0)
    fetch_interval_minutes: int = Field(default=60, ge=5, le=1440)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("信源名称不能为空")
        return name

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return normalize_source_url_value(value)

    @field_validator("keyword", "platform", "category")
    @classmethod
    def normalize_optional_text_fields(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional_text(value)


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[SourceType] = None
    url: Optional[str] = None
    keyword: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=1, le=5)
    sort_order: Optional[int] = Field(default=None, ge=0)
    fetch_interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    status: Optional[SourceStatus] = None
    sync_error: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("信源名称不能为空")
        return name

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return normalize_source_url_value(value)

    @field_validator("keyword", "platform", "category", "sync_error")
    @classmethod
    def normalize_optional_text_fields(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional_text(value)


class SourceResponse(BaseModel):
    id: int
    name: str
    source_type: str
    url: str
    keyword: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    weight: int
    sort_order: int
    fetch_interval_minutes: int
    status: str
    last_sync_at: Optional[datetime] = None
    sync_error: Optional[str] = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int
    page: int
    page_size: int


class SourceReorderRequest(BaseModel):
    ordered_ids: list[int] = Field(..., min_length=1)


class SyncResultResponse(BaseModel):
    """Result of syncing a single source."""
    fetched: int
    new: int
    duplicates: int
    source_info: SourceResponse

    model_config = {"from_attributes": True}
