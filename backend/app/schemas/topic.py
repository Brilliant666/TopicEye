from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class TopicAssetResponse(BaseModel):
    id: int
    content_id: int
    topic_title: Optional[str] = None
    topic_type: Optional[str] = None
    target_platforms: Optional[Any] = None
    target_audience: Optional[str] = None
    creator_score: Optional[float] = 0.0
    viral_score: Optional[float] = 0.0
    status: str
    is_favorited: bool = False
    is_used: bool = False
    feedback: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicDetailResponse(TopicAssetResponse):
    pass


class TopicListResponse(BaseModel):
    items: list[TopicAssetResponse]
    total: int
    page: int
    page_size: int
