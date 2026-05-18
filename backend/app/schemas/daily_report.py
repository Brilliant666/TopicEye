"""
Daily Report schema — request/response models.
"""
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field


class DailyReportResponse(BaseModel):
    id: int
    report_date: str
    weekday: str
    overview: Optional[str] = None
    takeaway: Optional[str] = None
    keywords: Optional[Any] = None      # parsed JSON array
    trends: Optional[Any] = None         # parsed JSON array
    top_picks: Optional[Any] = None      # parsed JSON array
    platform_tips: Optional[Any] = None  # parsed JSON object
    topic_count: int = 0
    content_count: int = 0
    analyzed_count: int = 0
    status: str = "PENDING"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DailyReportListResponse(BaseModel):
    items: list[DailyReportResponse]
    total: int
