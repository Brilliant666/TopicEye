"""Today-picks business logic backed by DuckDB analytical reads."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.duckdb_service import query_today_picks, query_topics

TODAY_PICKS_THRESHOLD = 55


async def build_today_picks(
    db: AsyncSession, *, category: Optional[str] = None, hours: int = 48, limit: Optional[int] = None,
) -> dict:
    """Return today-picks payload through the fixed DuckDB analytical layer."""
    _ = db
    rows = query_today_picks(
        hours=hours,
        category=category,
        limit=limit,
        curation_threshold=TODAY_PICKS_THRESHOLD,
    )
    if not rows:
        return _empty_payload()

    response_items = [_row_to_content_payload(row) for row in rows]
    topic_map = {topic["id"]: topic for topic in query_topics()}
    return _dedupe_and_pack(response_items, topic_map, limit=limit)


def _empty_payload() -> dict:
    return {
        "items": [], "total": 0, "duplicates_hidden": 0,
        "topics": [], "page": 1, "page_size": 0,
    }


def _row_to_content_payload(row: dict) -> dict:
    content_tags = _decode_json_value(row.get("tags"))
    analysis_tags = _decode_json_value(row.get("ai_tags")) or content_tags
    enrichment = _decode_json_value(row.get("enrichment"))
    analysis = {
        "id": row.get("analysis_id") or 0,
        "content_id": row["id"],
        "quality_score": row.get("quality_score") or 0,
        "hot_score": row.get("hot_score") or 0,
        "freshness_score": row.get("freshness_score") or 0,
        "creator_score": row.get("creator_score") or 0,
        "viral_score": row.get("viral_score") or 0,
        "risk_score": row.get("risk_score") or 0,
        "platform_fit": None,
        "recommended_reason": row.get("recommended_reason"),
        "summary": row.get("ai_summary"),
        "key_points": None,
        "audience_emotion": None,
        "creator_angles": None,
        "title_suggestions": None,
        "outline_suggestions": None,
        "xiaohongshu_plan": None,
        "short_video_plan": None,
        "risk_notes": None,
        "curation_score": row.get("curation_score") or 0,
        "tags": analysis_tags,
        "recommendation": row.get("recommendation"),
        "info_density": row.get("info_density") or 0,
        "actionability": row.get("actionability") or 0,
        "source_weight": row.get("source_weight") or 0,
        "enrichment_status": row.get("enrichment_status") or "pending",
        "enrichment": enrichment,
        "created_at": row.get("analysis_created_at") or row.get("created_at") or datetime.utcnow().isoformat(),
        "adjusted_curation_score": row.get("adjusted_curation_score") or row.get("curation_score") or 0,
        "score_breakdown": _score_breakdown(row),
    }
    return {
        "id": row["id"],
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "source_id": row.get("source_id"),
        "source_name": row.get("source_name"),
        "source_type": row.get("source_type"),
        "platform": row.get("platform"),
        "author": row.get("author"),
        "published_at": row.get("published_at"),
        "crawled_at": row.get("crawled_at"),
        "content_hash": row.get("content_hash"),
        "summary": row.get("summary"),
        "raw_content": row.get("raw_content"),
        "cover_url": row.get("cover_url"),
        "category": row.get("category"),
        "tags": content_tags,
        "language": row.get("language"),
        "status": row.get("status") or "analyzed",
        "is_favorited": bool(row.get("is_favorited")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "topic_id": row.get("topic_id"),
        "duplicate_of": row.get("duplicate_of"),
        "similarity_score": row.get("similarity_score"),
        "analysis": analysis,
        "analyses": [analysis],
    }


def _decode_json_value(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped == "null":
        return None
    if stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _score_breakdown(row: dict) -> dict:
    adjusted = float(row.get("adjusted_curation_score") or row.get("curation_score") or 0)
    curation = float(row.get("curation_score") or 0)
    source_bonus = round(adjusted - curation, 2)
    return {
        "content_id": row["id"],
        "base_score": round(curation, 2),
        "source_bonus": source_bonus,
        "quality_factor": 1.0,
        "risk_factor": 1.0,
        "time_decay": 1.0,
        "diversity_factor": 1.0,
        "final_score": round(adjusted, 2),
        "dimension_scores": {
            "info_density": row.get("info_density") or 0,
            "actionability": row.get("actionability") or 0,
            "creator_value": row.get("creator_score") or 0,
            "viral_potential": row.get("viral_score") or 0,
            "source_authority": row.get("source_weight") or 0,
            "freshness": row.get("freshness_score") or 0,
        },
        "selected": True,
        "threshold_used": TODAY_PICKS_THRESHOLD,
    }


def _dedupe_and_pack(items: list[dict], topic_map: dict, *, limit: Optional[int] = None) -> dict:
    deduped = [i for i in items if not i.get("duplicate_of")]
    duplicates_hidden = len(items) - len(deduped)
    total = len(deduped)
    if limit:
        deduped = deduped[:limit]
    topic_ids = {item.get("topic_id") for item in deduped if item.get("topic_id")}
    visible_topics = [topic for topic in topic_map.values() if topic["id"] in topic_ids]
    return {
        "items": deduped,
        "total": total,
        "duplicates_hidden": duplicates_hidden,
        "topics": visible_topics,
        "page": 1,
        "page_size": len(deduped),
    }
