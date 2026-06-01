"""Build read-only explanation payloads for the scoring funnel UI."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.content_repo import ContentRepo
from app.repositories.ignored_repo import IgnoredRepo
from app.services.scoring_engine import CONFIG, ScoreBreakdown, ScoringInput, score_items
from app.services.scoring_inputs import build_scoring_inputs


STAGE_KEYS = ["candidates", "quality", "risk", "freshness", "diversity", "selected"]
STAGE_LABELS = ["候选样本", "质量门槛", "风险降权", "时效衰减", "多样性混排", "精选输出"]


async def build_scoring_flow_payload(
    db: AsyncSession,
    *,
    hours: int,
    limit: int,
    sample_limit: int = 80,
) -> dict[str, Any]:
    """Return scoring funnel stages, candidate samples, and mix pressure data."""
    time_cutoff = datetime.utcnow() - timedelta(hours=hours)
    ignored_ids = await IgnoredRepo(db).list_ignored_ids()
    content_repo = ContentRepo(db)
    _, analyzed_total = await content_repo.list_for_scoring(
        exclude_ids=ignored_ids,
        limit=1,
    )
    items, total = await content_repo.list_for_scoring(
        exclude_ids=ignored_ids,
        time_cutoff=time_cutoff,
        limit=limit,
    )

    scoring_inputs, item_map, feedback_scores = await build_scoring_inputs(db, items)
    scored = score_items(scoring_inputs)

    category_counts = Counter((item.category or "未分类") for _, item in scored)
    source_counts = Counter((item.source_name or "未知来源") for _, item in scored)

    return {
        "total": total,
        "scored": len(scored),
        "hours": hours,
        "diagnostics": build_diagnostics(
            analyzed_total=analyzed_total,
            window_total=total,
            loaded_count=len(items),
            scoring_input_count=len(scoring_inputs),
            scored_count=len(scored),
            ignored_count=len(ignored_ids),
            limit=limit,
            sample_limit=sample_limit,
        ),
        "scoring_config": build_scoring_config_summary(),
        "stages": build_stage_counts(scored),
        "samples": [
            sample
            for breakdown, scoring_input in scored[:sample_limit]
            if (sample := build_sample_payload(
                breakdown,
                scoring_input,
                item_map,
                feedback_scores,
            ))
        ],
        "category_mix": [{"label": k, "count": v} for k, v in category_counts.most_common(8)],
        "source_mix": [{"label": k, "count": v} for k, v in source_counts.most_common(8)],
    }


def build_diagnostics(
    *,
    analyzed_total: int,
    window_total: int,
    loaded_count: int,
    scoring_input_count: int,
    scored_count: int,
    ignored_count: int,
    limit: int,
    sample_limit: int,
) -> dict[str, Any]:
    """Explain why the scoring-flow payload is empty or partial."""
    if analyzed_total <= 0:
        empty_reason = "no_analyzed_content"
    elif window_total <= 0:
        empty_reason = "no_content_in_window"
    elif loaded_count <= 0:
        empty_reason = "candidate_limit_empty"
    elif scoring_input_count <= 0:
        empty_reason = "no_scoring_inputs"
    elif scored_count <= 0:
        empty_reason = "all_candidates_filtered"
    else:
        empty_reason = "ok"

    return {
        "analyzed_total": analyzed_total,
        "window_total": window_total,
        "loaded_count": loaded_count,
        "scoring_input_count": scoring_input_count,
        "scored_count": scored_count,
        "ignored_count": ignored_count,
        "candidate_limit": limit,
        "sample_limit": sample_limit,
        "empty_reason": empty_reason,
        "generated_at": datetime.utcnow().isoformat(),
    }


def build_scoring_config_summary() -> dict[str, Any]:
    """Expose stable scoring knobs for UI explanation, not mutation."""
    keys = (
        "curation_mode",
        "curation_percentile",
        "curation_threshold",
        "min_selected_base_score",
        "quality_gate_min",
        "quality_gate_strong",
        "quality_gate_floor",
        "risk_threshold",
        "risk_soft_start",
        "risk_soft_floor",
        "time_decay_lambda",
        "time_decay_floor",
        "diversity_top_n",
        "same_source_grace",
        "same_category_grace",
    )
    return {key: CONFIG[key] for key in keys}


def build_stage_counts(scored: list[tuple[ScoreBreakdown, ScoringInput]]) -> list[dict[str, Any]]:
    total = len(scored)
    quality_pass = [(breakdown, item) for breakdown, item in scored if breakdown.quality_factor > 0.55]
    risk_pass = [(breakdown, item) for breakdown, item in quality_pass if breakdown.risk_factor > 0.55]
    freshness_pass = [(breakdown, item) for breakdown, item in risk_pass if breakdown.time_decay >= 0.6]
    diversity_pass = [(breakdown, item) for breakdown, item in freshness_pass if breakdown.diversity_factor >= 0.85]
    selected = [(breakdown, item) for breakdown, item in diversity_pass if breakdown.selected]
    counts = [total, len(quality_pass), len(risk_pass), len(freshness_pass), len(diversity_pass), len(selected)]
    return [
        {
            "key": key,
            "label": label,
            "count": count,
            "retention": round(count / total, 4) if total else 0,
        }
        for key, label, count in zip(STAGE_KEYS, STAGE_LABELS, counts)
    ]


def build_sample_payload(
    breakdown: ScoreBreakdown,
    scoring_input: ScoringInput,
    item_map: dict[int, Any],
    feedback_scores: dict[int, float],
) -> Optional[dict[str, Any]]:
    item = item_map.get(scoring_input.content_id)
    if not item:
        return None
    return {
        "id": item.id,
        "title": item.title,
        "url": item.url,
        "source_name": item.source_name,
        "category": item.category or "未分类",
        "selected": breakdown.selected,
        "final_score": breakdown.final_score,
        "threshold_used": breakdown.threshold_used,
        "base_score": breakdown.base_score,
        "source_bonus": breakdown.source_bonus,
        "quality_factor": breakdown.quality_factor,
        "risk_factor": breakdown.risk_factor,
        "time_decay": breakdown.time_decay,
        "diversity_factor": breakdown.diversity_factor,
        "feedback_score": feedback_scores.get(item.id, 0),
        "dimension_scores": breakdown.dimension_scores,
    }
