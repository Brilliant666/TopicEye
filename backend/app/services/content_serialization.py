from __future__ import annotations

from app.schemas.analysis import AiAnalysisResponse
from app.schemas.content import ContentResponse


def content_with_latest_analysis(item) -> dict:
    data = ContentResponse.model_validate(item).model_dump()
    if item.analyses:
        data["analysis"] = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
    return data
