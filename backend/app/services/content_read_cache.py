from __future__ import annotations

from app.services.content_list_cache import invalidate_content_list_cache
from app.services.scoring_flow import invalidate_scoring_flow_cache
from app.services.today_picks_cache import invalidate_today_picks_cache


def invalidate_content_read_caches() -> None:
    """Invalidate cached read models derived from content, analyses, or feedback."""
    invalidate_content_list_cache()
    invalidate_scoring_flow_cache()
    invalidate_today_picks_cache()
