"""
Daily Report schema — request/response models.
"""
import json
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, field_serializer

from app.services.zhihu_url import normalize_zhihu_url


def _parse_json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize_top_pick_urls(value: Any) -> Any:
    parsed = _parse_json_value(value)
    if isinstance(parsed, list):
        for pick in parsed:
            if isinstance(pick, dict) and "source_url" in pick:
                pick["source_url"] = normalize_zhihu_url(pick.get("source_url"))
    return parsed


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

    @field_serializer("keywords", "trends", "platform_tips")
    def serialize_json_fields(self, value: Any) -> Any:
        return _parse_json_value(value)

    @field_serializer("top_picks")
    def serialize_top_picks(self, value: Any) -> Any:
        return _normalize_top_pick_urls(value)


class DailyReportListResponse(BaseModel):
    items: list[DailyReportResponse]
    total: int


class DailyReportDateSummary(BaseModel):
    """Lightweight summary for the date sidebar."""
    report_date: str
    weekday: str
    takeaway: Optional[str] = None
    status: str = "PENDING"


class DailyReportDatesResponse(BaseModel):
    """Response for the dates-list endpoint."""
    dates: list[DailyReportDateSummary]
