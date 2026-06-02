from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.favorite import FavoriteStatus, FavoriteTargetType


class FavoriteCreate(BaseModel):
    target_type: FavoriteTargetType
    target_id: Optional[int] = None
    target_key: Optional[str] = Field(default=None, max_length=255)
    title: Optional[str] = Field(default=None, max_length=500)
    url: Optional[str] = Field(default=None, max_length=1024)
    cover_url: Optional[str] = Field(default=None, max_length=1024)
    source_name: Optional[str] = Field(default=None, max_length=255)
    collection_id: Optional[int] = None
    tags: Optional[Any] = None
    note: Optional[str] = None
    status: FavoriteStatus = FavoriteStatus.INBOX
    snapshot: Optional[Any] = None

    @model_validator(mode="after")
    def validate_target_identity(self) -> "FavoriteCreate":
        if self.target_id is None and not self.target_key:
            raise ValueError("target_id or target_key is required")
        return self


class FavoriteUpdate(BaseModel):
    collection_id: Optional[int] = None
    tags: Optional[Any] = None
    note: Optional[str] = None
    status: Optional[FavoriteStatus] = None


class FavoriteReorderRequest(BaseModel):
    status: FavoriteStatus
    ordered_ids: list[int] = Field(min_length=1, max_length=500)


class FavoriteResponse(BaseModel):
    id: int
    target_type: str
    target_id: Optional[int] = None
    target_key: str
    title: str
    url: Optional[str] = None
    cover_url: Optional[str] = None
    source_name: Optional[str] = None
    collection_id: Optional[int] = None
    tags: Optional[Any] = None
    note: Optional[str] = None
    status: str
    position: int
    snapshot: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FavoriteListResponse(BaseModel):
    items: list[FavoriteResponse]
    total: int
    page: int
    page_size: int
