"""Today-picks business logic — separated from the route for clarity."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.content_repo import ContentRepo
from app.schemas.content import ContentResponse
from app.schemas.analysis import AiAnalysisResponse

CURATION_THRESHOLD = 60
WEIGHT_BONUS = 8


async def build_today_picks(
    db: AsyncSession, *, category: Optional[str] = None, hours: int = 48,
) -> dict:
    """Return today-picks payload. Tries DuckDB first, falls back to SQLite."""
    # ── DuckDB fast path ──
    payload = await _duckdb_path(hours=hours, category=category)
    if payload is not None:
        return payload

    # ── SQLite fallback ──
    return await _sqlite_path(db, hours=hours, category=category)


async def _duckdb_path(hours: int, category: Optional[str]) -> Optional[dict]:
    """Try DuckDB analytical layer. Returns None on failure."""
    try:
        from app.services.duckdb_service import query_today_picks, query_topics
        duckdb_items = query_today_picks(hours=hours)
        if not duckdb_items:
            return None
        if category:
            duckdb_items = [i for i in duckdb_items if i.get("category") == category]
        topic_map = {t["id"]: t for t in query_topics()}
        response_items = _transform_duckdb_rows(duckdb_items)
        return _dedupe_and_pack(response_items, topic_map)
    except Exception:
        return None


async def _sqlite_path(db: AsyncSession, hours: int, category: Optional[str]) -> dict:
    """SQLite fallback: score items by adjusted curation_score."""
    from app.models.topic import TopicGroup

    repo = ContentRepo(db)
    items = await repo.list_for_today_picks(hours=hours, category=category)

    scored: list[tuple] = []
    for item in items:
        if not item.analyses:
            continue
        a = item.analyses[-1]
        cs = a.curation_score or 0
        src_w = item.source.weight if item.source else 3
        adj = cs + (src_w - 3) * WEIGHT_BONUS
        if cs == 0:
            adj = ((a.creator_score or 0) + (a.viral_score or 0)) / 2 + (src_w - 3) * WEIGHT_BONUS
        if adj >= CURATION_THRESHOLD:
            scored.append((item, adj))
    scored.sort(key=lambda x: x[1], reverse=True)

    response_items = []
    for item, adj_score in scored:
        d = ContentResponse.model_validate(item).model_dump()
        if item.analyses:
            a_dict = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
            a_dict["adjusted_curation_score"] = round(adj_score, 1)
            d["analysis"] = a_dict
        d["topic_id"] = item.topic_id
        d["duplicate_of"] = item.duplicate_of
        response_items.append(d)

    topic_rows = (await db.execute(
        select(TopicGroup).order_by(TopicGroup.best_score.desc())
    )).scalars().all()
    topic_map = {
        t.id: {"id": t.id, "name": t.name, "summary": t.summary,
               "keywords": t.keywords, "best_score": t.best_score}
        for t in topic_rows
    }
    return _dedupe_and_pack(response_items, topic_map)


def _transform_duckdb_rows(duckdb_items: list) -> list[dict]:
    """Transform DuckDB rows into the same response shape as the SQLite path."""
    pick_keys = ("quality_score", "hot_score", "freshness_score", "creator_score",
                 "viral_score", "risk_score", "curation_score", "info_density",
                 "actionability", "recommended_reason", "recommendation")
    item_keys = ("id", "title", "url", "source_id", "source_name", "source_type",
                 "platform", "author", "published_at", "crawled_at", "summary",
                 "category", "tags", "topic_id", "duplicate_of", "similarity_score")
    results = []
    for item in duckdb_items:
        analysis = {k: item.get(k) for k in pick_keys}
        analysis.update({
            "summary": item.get("ai_summary"), "tags": item.get("ai_tags"),
            "enrichment_status": item.get("enrichment_status"),
            "enrichment": item.get("enrichment"),
            "adjusted_curation_score": item.get("adjusted_curation_score"),
        })
        results.append({k: item.get(k) for k in item_keys} | {"analysis": analysis})
    return results


def _dedupe_and_pack(items: list[dict], topic_map: dict) -> dict:
    deduped = [i for i in items if not i.get("duplicate_of")]
    return {
        "items": deduped,
        "total": len(deduped),
        "duplicates_hidden": len(items) - len(deduped),
        "topics": list(topic_map.values()),
        "page": 1,
        "page_size": len(deduped),
    }
