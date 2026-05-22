"""
Scoring engine for content curation — multi-signal weighted ranking.

Design inspired by multi-stage recommendation pipelines:
  1. Base score: 6-dimension weighted sum + source quality bonus
  2. Time decay: exponential decay favouring fresher content
  3. Source diversity penalty: down-rank when same source dominates
  4. Risk filter: hard-exclude high-risk items (risk_score > 70)

All tuning constants live in the CONFIG dict at the top for easy adjustment.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional


# ── Tunable configuration ────────────────────────────────────────────

CONFIG = {
    # 6-dimension weights (must sum to 1.0)
    "w_info_density": 0.25,    # 信息密度
    "w_actionability": 0.20,   # 可操作性
    "w_creator_value": 0.18,   # 创作者价值
    "w_viral_potential": 0.15,  # 爆文潜力
    "w_source_authority": 0.12, # 来源权威度
    "w_freshness": 0.10,        # 时效新鲜度

    # Source weight mapping (source.weight 1-5 → bonus)
    "source_weight_bonus_factor": 6.0,  # per weight-unit above 3

    # Time decay
    "time_decay_lambda": 0.02,  # decay rate: exp(-lambda * hours)
    "time_decay_floor": 0.3,    # minimum time decay (never fully kill)

    # Source diversity
    "diversity_penalty_base": 0.85,  # multiplier per same-source duplicate in top-N
    "diversity_top_n": 50,           # count diversity within top-N candidates

    # Risk
    "risk_threshold": 70,  # hard-exclude above this

    # Curation threshold (minimum final score to be selected)
    "curation_threshold": 55,  # slightly lower than before, because scores are now more calibrated

    # Fallback: when curation_score is 0 but other scores exist
    "fallback_use_avg": True,

    # ── Percentile-based curation mode ──
    "curation_mode": "percentile",       # "percentile" | "fixed"
    "curation_percentile": 75,           # top ~25% selected (P75 and above)

    # ── User feedback signal ──
    "w_feedback": 0.15,                  # 15% weight for feedback_score
}


# ── Data containers ──────────────────────────────────────────────────

class ScoringInput:
    """Lightweight input for the scorer — avoids ORM coupling."""

    __slots__ = (
        "content_id", "title", "source_id", "source_name", "published_at",
        "crawled_at",
        # Analysis dimensions
        "curation_score", "info_density", "actionability", "source_weight",
        "creator_score", "viral_score", "freshness_score", "quality_score",
        "hot_score", "risk_score",
        # Source
        "source_weight_db",  # Source.weight from DB (1-5)
        # Feedback & source accuracy signals
        "feedback_score",     # user feedback signal (0+, default 0)
        "source_accuracy",    # source historical accuracy (0-1, default 0.5)
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            if slot == "feedback_score":
                setattr(self, slot, kwargs.get(slot, 0))
            elif slot == "source_accuracy":
                setattr(self, slot, kwargs.get(slot, 0.5))
            else:
                setattr(self, slot, kwargs.get(slot, 0))


class ScoreBreakdown:
    """Structured breakdown of how a score was computed — for API response & UI."""

    __slots__ = (
        "content_id",
        "base_score",           # weighted 6-dim sum
        "source_bonus",         # source.weight adjustment
        "time_decay",           # time decay multiplier (0-1)
        "diversity_factor",     # diversity penalty multiplier (0-1)
        "final_score",          # base_score + source_bonus) * time_decay * diversity
        "dimension_scores",     # dict of individual dimension contributions
        "selected",             # whether it passes the threshold
        "threshold_used",       # actual curation threshold applied (for frontend)
    )

    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


# ── Scoring functions ────────────────────────────────────────────────

def _compute_base_score(item: ScoringInput) -> tuple[float, dict]:
    """Compute weighted 6-dimension base score."""
    cfg = CONFIG

    # When curation_score exists and is > 0, prefer it as the primary signal
    # but blend with individual dimensions for more nuance
    cs = item.curation_score or 0

    dimensions = {
        "info_density": (item.info_density or 50) * cfg["w_info_density"],
        "actionability": (item.actionability or 50) * cfg["w_actionability"],
        "creator_value": (item.creator_score or 50) * cfg["w_creator_value"],
        "viral_potential": (item.viral_score or 50) * cfg["w_viral_potential"],
        "source_authority": (item.source_weight or 50) * cfg["w_source_authority"],
        "freshness": (item.freshness_score or 50) * cfg["w_freshness"],
    }

    dim_sum = sum(dimensions.values())

    # Blend: if LLM gave a curation_score, weight it 60% + 40% dimension sum
    # Otherwise, use pure dimension sum
    if cs > 0:
        base = cs * 0.6 + dim_sum * 0.4
    elif cfg["fallback_use_avg"]:
        # Fallback: average of available scores
        scores = [
            item.creator_score or 0, item.viral_score or 0,
            item.quality_score or 0, item.hot_score or 0,
        ]
        avg = sum(s for s in scores if s > 0) / max(1, sum(1 for s in scores if s > 0))
        base = avg * 0.5 + dim_sum * 0.5
    else:
        base = dim_sum

    # ── User feedback signal adjustment ──
    feedback_adjustment = (item.feedback_score or 0) * cfg["w_feedback"]
    base += feedback_adjustment

    # ── Source historical accuracy factor ──
    # accuracy_factor range: 0.8 (low accuracy) – 1.2 (high accuracy)
    accuracy_factor = 0.8 + (item.source_accuracy or 0.5) * 0.4
    base *= accuracy_factor

    return base, dimensions


def _compute_source_bonus(item: ScoringInput) -> float:
    """Bonus (or penalty) based on Source.weight from DB (1-5)."""
    cfg = CONFIG
    w = item.source_weight_db or 3  # default weight = 3
    return (w - 3) * cfg["source_weight_bonus_factor"]


def _compute_percentile_threshold(base_scores: list[float], percentile: float) -> float:
    """
    Compute the value at the given percentile from a list of base scores.
    Items with base_score >= this value are in the top (100 - percentile)%.
    Returns the fixed curation_threshold as fallback if the list is empty.
    """
    if not base_scores:
        return CONFIG["curation_threshold"]

    sorted_scores = sorted(base_scores)
    n = len(sorted_scores)
    # Use nearest-rank method: rank = ceil(percentile/100 * n)
    rank = min(math.ceil(percentile / 100.0 * n), n)
    return round(sorted_scores[rank - 1], 2)


def _compute_time_decay(item: ScoringInput, now: Optional[datetime] = None) -> float:
    """Exponential time decay: fresher content gets higher score."""
    cfg = CONFIG
    if now is None:
        now = datetime.utcnow()

    # Use published_at if available, otherwise crawled_at
    t = item.published_at or item.crawled_at or now
    if isinstance(t, str):
        t = datetime.fromisoformat(t.replace("Z", ""))

    hours = max(0, (now - t).total_seconds() / 3600)
    decay = math.exp(-cfg["time_decay_lambda"] * hours)
    return max(cfg["time_decay_floor"], min(1.0, decay))


def _compute_diversity_penalty(
    items: list[ScoringInput],
    prelim_scores: list[float],
) -> list[float]:
    """Down-rank items from sources that appear too often in top-N."""
    cfg = CONFIG
    top_n = cfg["diversity_top_n"]

    # Sort by prelim score to determine top-N
    indexed = sorted(enumerate(prelim_scores), key=lambda x: x[1], reverse=True)

    source_counts: dict[Optional[int], int] = {}
    factors = [1.0] * len(items)

    for rank, (idx, score) in enumerate(indexed):
        if rank >= top_n:
            break
        src_id = items[idx].source_id
        count = source_counts.get(src_id, 0)
        if count > 0:
            # Each additional item from the same source gets progressively penalized
            factors[idx] = cfg["diversity_penalty_base"] ** count
        source_counts[src_id] = count + 1

    return factors


def score_items(items: list[ScoringInput]) -> list[tuple[ScoreBreakdown, ScoringInput]]:
    """
    Score a batch of items through the full pipeline.

    Returns list of (ScoreBreakdown, ScoringInput) sorted by final_score desc.
    """
    cfg = CONFIG
    now = datetime.utcnow()

    # Phase 1: Filter high-risk items
    safe_items = [it for it in items if (it.risk_score or 0) <= cfg["risk_threshold"]]

    # Phase 2: Compute base score + source bonus + time decay
    prelim_scores: list[float] = []
    breakdowns: list[ScoreBreakdown] = []

    for item in safe_items:
        base, dims = _compute_base_score(item)
        source_bonus = _compute_source_bonus(item)
        time_decay = _compute_time_decay(item, now)

        prelim = (base + source_bonus) * time_decay
        prelim_scores.append(prelim)

        bd = ScoreBreakdown(
            content_id=item.content_id,
            base_score=round(base, 2),
            source_bonus=round(source_bonus, 2),
            time_decay=round(time_decay, 4),
            diversity_factor=1.0,  # placeholder, filled in phase 3
            final_score=0.0,
            dimension_scores={k: round(v, 2) for k, v in dims.items()},
            selected=False,
        )
        breakdowns.append(bd)

    # Phase 3: Source diversity penalty
    diversity_factors = _compute_diversity_penalty(safe_items, prelim_scores)

    # Phase 4: Compute final score
    results: list[tuple[ScoreBreakdown, ScoringInput]] = []
    for i, (bd, item) in enumerate(zip(breakdowns, safe_items)):
        bd.diversity_factor = round(diversity_factors[i], 4)
        bd.final_score = round(
            prelim_scores[i] * diversity_factors[i], 2
        )
        results.append((bd, item))

    # Sort by final_score descending
    results.sort(key=lambda x: x[0].final_score, reverse=True)

    # Phase 5: Determine threshold and mark selected
    if cfg["curation_mode"] == "percentile":
        # Use final_score ranking: top (100 - percentile)% are selected
        # e.g. curation_percentile=70 → top 30% selected
        final_scores = [bd.final_score for bd, _ in results]
        actual_threshold = _compute_percentile_threshold(
            final_scores, cfg["curation_percentile"]
        )
    else:
        actual_threshold = cfg["curation_threshold"]

    for bd, item in results:
        bd.threshold_used = round(actual_threshold, 2)
        bd.selected = bd.final_score >= actual_threshold

    return results


def score_low_follower_viral(
    items: list[ScoringInput],
) -> list[tuple[ScoreBreakdown, ScoringInput]]:
    """
    Low-Follower Viral (LFV) discovery — find content that broke through
    despite being posted by low-reach sources.

    Algorithm:
        lfv_score = (
            viral_score * 0.45        # raw viral potential
            + creator_score * 0.30    #选题 value for creators
            + quality_score * 0.25    # content quality
        ) * obscure_factor * freshness_boost

    obscure_factor  = max(0.05, 1 - source_weight_normalized)
                   (0.05 = minimum, to never fully zero out authoritative sources)
    source_weight_normalized = source_weight / 100  (0-1, high = authoritative)

    freshness_boost = 1 + freshness_score / 200  (1.0-1.5)

    High LFV = high virality/quality + low source authority (obscure creator)
    """
    now = datetime.utcnow()
    cfg = CONFIG
    results: list[tuple[ScoreBreakdown, ScoringInput]] = []

    # Filter high-risk items
    safe_items = [it for it in items if (it.risk_score or 0) <= cfg["risk_threshold"]]

    for item in safe_items:
        vs = item.viral_score or 0
        cs = item.creator_score or 0
        qs = item.quality_score or 0
        fs = item.freshness_score or 0
        sw = item.source_weight or 50  # analysis source_weight (0-100)

        # Weighted content score
        content_score = vs * 0.45 + cs * 0.30 + qs * 0.25

        # Obscure factor: low source_weight → high obscure factor
        obscure_factor = max(0.05, 1 - sw / 100)

        # Freshness boost
        freshness_boost = 1 + fs / 200

        lfv_score = round(content_score * obscure_factor * freshness_boost, 2)

        # Time decay (same as main pipeline)
        time_decay = _compute_time_decay(item, now)

        final_score = round(lfv_score * time_decay, 2)

        bd = ScoreBreakdown(
            content_id=item.content_id,
            base_score=round(content_score, 2),
            source_bonus=round(obscure_factor, 4),
            time_decay=round(time_decay, 4),
            diversity_factor=1.0,
            final_score=final_score,
            dimension_scores={
                "viral_score": vs,
                "creator_score": cs,
                "quality_score": qs,
                "source_weight": sw,
                "obscure_factor": round(obscure_factor, 4),
                "freshness_boost": round(freshness_boost, 4),
            },
            selected=final_score >= 30,  # permissive threshold for discovery
        )
        results.append((bd, item))

    results.sort(key=lambda x: x[0].final_score, reverse=True)
    return results
