from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.source import SourceType, SourceStatus


class SourceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    source_type: SourceType = SourceType.RSS
    url: str = Field(..., max_length=1024)
    keyword: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    weight: int = Field(default=3, ge=1, le=5)
    enabled: bool = True


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[SourceType] = None
    url: Optional[str] = None
    keyword: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    weight: Optional[int] = Field(default=None, ge=1, le=5)
    status: Optional[SourceStatus] = None
    enabled: Optional[bool] = None


class SourceResponse(BaseModel):
    id: int
    name: str
    source_type: str
    url: str
    keyword: Optional[str] = None
    platform: Optional[str] = None
    category: Optional[str] = None
    weight: int
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


class SyncResultResponse(BaseModel):
    """Result of syncing a single source."""
    fetched: int
    new: int
    duplicates: int
    source_info: SourceResponse

    model_config = {"from_attributes": True}
