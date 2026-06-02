"""Today-picks business logic — uses scoring_engine for multi-signal ranking."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.content_repo import ContentRepo
from app.services.content_serialization import content_with_latest_analysis
from app.services.scoring_engine import score_items
from app.services.scoring_inputs import build_scoring_inputs


async def build_today_picks(
    db: AsyncSession, *, category: Optional[str] = None, hours: int = 48,
) -> dict:
    """Return today-picks payload using the multi-signal scoring engine."""
    # ── Fetch candidates ──
    repo = ContentRepo(db)
    items = await repo.list_for_today_picks(hours=hours, category=category)

    scoring_inputs, item_map, _ = await build_scoring_inputs(db, items)

    if not scoring_inputs:
        return _empty_payload()

    # ── Run scoring pipeline ──
    scored = score_items(scoring_inputs)

    # ── Build response ──
    response_items = []
    for breakdown, si in scored:
        if not breakdown.selected:
            continue

        item = item_map.get(si.content_id)
        if not item:
            continue

        d = content_with_latest_analysis(item)
        if d.get("analysis"):
            d["analysis"]["adjusted_curation_score"] = breakdown.final_score
            d["analysis"]["score_breakdown"] = breakdown.to_dict()

        d["topic_id"] = item.topic_id
        d["duplicate_of"] = item.duplicate_of
        response_items.append(d)

    # ── Topics ──
    from app.models.topic import TopicGroup
    topic_rows = (await db.execute(
        select(TopicGroup).order_by(TopicGroup.best_score.desc())
    )).scalars().all()
    topic_map = {
        t.id: {
            "id": t.id, "name": t.name, "summary": t.summary,
            "keywords": t.keywords, "best_score": t.best_score,
        }
        for t in topic_rows
    }

    return _dedupe_and_pack(response_items, topic_map)


def _empty_payload() -> dict:
    return {
        "items": [], "total": 0, "duplicates_hidden": 0,
        "topics": [], "page": 1, "page_size": 0,
    }


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
