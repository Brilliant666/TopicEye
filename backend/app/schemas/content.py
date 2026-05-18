from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.schemas.analysis import AiAnalysisResponse


class ContentResponse(BaseModel):
    id: int
    title: str
    url: str
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    platform: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    crawled_at: datetime
    content_hash: Optional[str] = None
    summary: Optional[str] = None
    raw_content: Optional[str] = None
    cover_url: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[Any] = None
    language: Optional[str] = None
    status: str
    is_favorited: bool = False
    created_at: datetime
    updated_at: datetime
    analysis: Optional[AiAnalysisResponse] = None

    model_config = {"from_attributes": True}


class ContentMetricsResponse(BaseModel):
    id: int
    content_id: int
    views: Optional[int] = 0
    likes: Optional[int] = 0
    comments: Optional[int] = 0
    shares: Optional[int] = 0
    favorites: Optional[int] = 0
    followers_count: Optional[int] = 0
    engagement_rate: Optional[float] = 0.0
    explosion_ratio: Optional[float] = 0.0
    snapshot_at: datetime

    model_config = {"from_attributes": True}


class ContentDetailResponse(ContentResponse):
    metrics: list[ContentMetricsResponse] = []


class ContentListResponse(BaseModel):
    items: list[ContentResponse]
    total: int
    page: int
    page_size: int
