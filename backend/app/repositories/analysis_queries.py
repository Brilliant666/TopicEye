"""Shared SQL helpers for analysis row selection."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.analysis import AiAnalysis
from app.models.content import ContentItem


def latest_analysis_id_subquery(
    content_model: Any = ContentItem,
    analysis_model: Any = AiAnalysis,
):
    """Return the latest analysis id correlated to a content model."""
    latest_analysis = aliased(analysis_model)
    return (
        select(latest_analysis.id)
        .where(latest_analysis.content_id == content_model.id)
        .order_by(latest_analysis.created_at.desc(), latest_analysis.id.desc())
        .limit(1)
        .correlate(content_model)
        .scalar_subquery()
    )


def latest_analysis_id_for_content_id(
    content_id: Any,
    analysis_model: Any = AiAnalysis,
):
    """Return the latest analysis id for a concrete or correlated content id."""
    latest_analysis = aliased(analysis_model)
    return (
        select(latest_analysis.id)
        .where(latest_analysis.content_id == content_id)
        .order_by(latest_analysis.created_at.desc(), latest_analysis.id.desc())
        .limit(1)
        .correlate_except(latest_analysis)
        .scalar_subquery()
    )
