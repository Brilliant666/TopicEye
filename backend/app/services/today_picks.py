"""Today-picks business logic — uses scoring_engine for multi-signal ranking."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.models.analysis import AiAnalysis
from app.repositories.content_repo import ContentRepo
from app.schemas.content import ContentResponse
from app.schemas.analysis import AiAnalysisResponse
from app.services.scoring_engine import ScoringInput, score_items

logger = logging.getLogger(__name__)


async def build_today_picks(
    db: AsyncSession, *, category: Optional[str] = None, hours: int = 48,
) -> dict:
    """Return today-picks payload using the multi-signal scoring engine."""
    # ── Fetch candidates ──
    repo = ContentRepo(db)
    items = await repo.list_for_today_picks(hours=hours, category=category)

    # ── Build scoring inputs ──
    scoring_inputs: list[ScoringInput] = []
    item_map: dict[int, ContentItem] = {}

    for item in items:
        if not item.analyses:
            continue

        a = item.analyses[-1]  # latest analysis
        src_w = item.source.weight if item.source else 3

        si = ScoringInput(
            content_id=item.id,
            title=item.title,
            source_id=item.source_id,
            source_name=item.source_name,
            published_at=item.published_at,
            crawled_at=item.crawled_at,
            # Analysis dimensions
            curation_score=a.curation_score or 0,
            info_density=a.info_density or 50,
            actionability=a.actionability or 50,
            source_weight=a.source_weight or 50,
            creator_score=a.creator_score or 0,
            viral_score=a.viral_score or 0,
            freshness_score=a.freshness_score or 0,
            quality_score=a.quality_score or 0,
            hot_score=a.hot_score or 0,
            risk_score=a.risk_score or 0,
            # Source
            source_weight_db=src_w,
        )
        scoring_inputs.append(si)
        item_map[item.id] = item

    if not scoring_inputs:
        return _empty_payload()

    # ── Run scoring pipeline ──
    scored = score_items(scoring_inputs)

    # ── Build response ──
    response_items = []
    selected_count = 0
    for breakdown, si in scored:
        if not breakdown.selected:
            continue

        item = item_map.get(si.content_id)
        if not item:
            continue

        d = ContentResponse.model_validate(item).model_dump()
        if item.analyses:
            a_dict = AiAnalysisResponse.model_validate(item.analyses[-1]).model_dump()
            a_dict["adjusted_curation_score"] = breakdown.final_score
            a_dict["score_breakdown"] = breakdown.to_dict()
            d["analysis"] = a_dict

        d["topic_id"] = item.topic_id
        d["duplicate_of"] = item.duplicate_of
        response_items.append(d)
        selected_count += 1

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
