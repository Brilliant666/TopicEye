from __future__ import annotations

import logging
import time
from typing import Any

from app.core.database import async_session
from app.repositories.content_repo import ContentRepo
from app.repositories.source_repo import SourceRepository
from app.schemas.source import SourceListResponse
from app.services.json_cache import set_cached_json

logger = logging.getLogger(__name__)


async def warmup_read_caches() -> dict[str, Any]:
    """Warm hot read caches without blocking application startup."""
    started_at = time.perf_counter()
    warmed: list[str] = []
    errors: list[str] = []

    async with async_session() as db:
        try:
            await warmup_sources_list(db)
            warmed.append("sources:list:1:20")
        except Exception as exc:
            logger.warning("Source list cache warmup skipped: %s", exc)
            errors.append(f"sources:{exc}")

        try:
            await warmup_content_favorites(db)
            warmed.append("contents:favorites:list:1:20")
        except Exception as exc:
            logger.warning("Content favorites cache warmup skipped: %s", exc)
            errors.append(f"favorites:{exc}")

        try:
            await warmup_stats_overview(db)
            warmed.append("stats:overview:7")
        except Exception as exc:
            logger.warning("Stats overview cache warmup skipped: %s", exc)
            errors.append(f"stats:{exc}")

        try:
            await warmup_scoring_flow(db)
            warmed.append("scoring-flow:48:160")
        except Exception as exc:
            logger.warning("Scoring flow cache warmup skipped: %s", exc)
            errors.append(f"scoring-flow:{exc}")

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info("Read cache warmup completed in %.1fms: %s", elapsed_ms, ", ".join(warmed) or "none")
    return {"warmed": warmed, "errors": errors, "elapsed_ms": elapsed_ms}


async def warmup_sources_list(db) -> None:
    repo = SourceRepository(db)
    items, total = await repo.list_paginated(
        page=1,
        page_size=20,
        filters={},
        sort_by="sort_order",
        sort_order="asc",
    )
    payload = SourceListResponse(items=items, total=total, page=1, page_size=20).model_dump()
    set_cached_json("sources:list:1:20:::None:", payload)


async def warmup_content_favorites(db) -> None:
    from app.api.v1.contents import _with_analysis

    items, total = await ContentRepo(db).list_favorites(page=1, page_size=20)
    payload = {
        "items": [_with_analysis(item) for item in items],
        "total": total,
        "page": 1,
        "page_size": 20,
    }
    set_cached_json("contents:favorites:list:1:20", payload)


async def warmup_stats_overview(db) -> None:
    from app.api.v1.stats import build_overview_payload

    payload = await build_overview_payload(db, days=7)
    set_cached_json("stats:overview:7", payload)


async def warmup_scoring_flow(db) -> None:
    from app.services.scoring_flow import build_scoring_flow_payload

    await build_scoring_flow_payload(db, hours=48, limit=160)
