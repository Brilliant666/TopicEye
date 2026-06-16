from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class AiAnalysisResponse(BaseModel):
    id: int
    content_id: int
    quality_score: Optional[float] = 0.0
    hot_score: Optional[float] = 0.0
    freshness_score: Optional[float] = 0.0
    creator_score: Optional[float] = 0.0
    viral_score: Optional[float] = 0.0
    risk_score: Optional[float] = 0.0
    platform_fit: Optional[Any] = None
    recommended_reason: Optional[str] = None
    summary: Optional[str] = None
    key_points: Optional[Any] = None
    audience_emotion: Optional[str] = None
    creator_angles: Optional[Any] = None
    title_suggestions: Optional[Any] = None
    outline_suggestions: Optional[Any] = None
    xiaohongshu_plan: Optional[Any] = None
    short_video_plan: Optional[Any] = None
    risk_notes: Optional[Any] = None
    # Curation fields
    curation_score: Optional[float] = 0.0
    tags: Optional[Any] = None
    recommendation: Optional[str] = None
    info_density: Optional[float] = 0.0
    actionability: Optional[float] = 0.0
    source_weight: Optional[float] = 0.0
    # Model cascade routing metadata
    analysis_mode: Optional[str] = "pro_only"
    prescreen_model: Optional[str] = None
    final_model: Optional[str] = None
    escalated: Optional[bool] = False
    escalation_reason: Optional[str] = None
    prescreen_confidence: Optional[float] = None
    prescreen_score: Optional[float] = None
    # Round-2 enrichment fields
    enrichment_status: Optional[str] = "pending"
    enrichment: Optional[Any] = None
    # Summary provenance (llm_pro | llm_lite | local_fallback)
    summary_source: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
