from __future__ import annotations

from app.services.source_cache import invalidate_source_list_cache
from app.services.stats_cache import invalidate_stats_cache


def invalidate_source_read_caches() -> None:
    """Invalidate cached read models derived from sources or source health."""
    invalidate_source_list_cache()
    invalidate_stats_cache()
