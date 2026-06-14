from __future__ import annotations

from app.schemas.analysis import AiAnalysisResponse
from app.schemas.content import ContentResponse


def latest_analysis_from_item(item):
    """Return the latest loaded analysis using the same ordering as DB latest helpers."""
    analyses = list(getattr(item, "analyses", []) or [])
    if not analyses:
        return None
    return max(
        analyses,
        key=lambda analysis: (
            analysis.created_at is not None,
            analysis.created_at,
            analysis.id or 0,
        ),
    )


def content_with_latest_analysis(item, *, include_raw_content: bool = False) -> dict:
    data = ContentResponse.model_validate(item).model_dump()
    if not include_raw_content:
        data["raw_content"] = None
    analysis = latest_analysis_from_item(item)
    if analysis:
        data["analysis"] = AiAnalysisResponse.model_validate(analysis).model_dump()
    return data
