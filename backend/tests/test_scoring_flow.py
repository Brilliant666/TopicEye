from app.services.scoring_engine import ScoreBreakdown, ScoringInput
from app.services.scoring_flow import (
    build_diagnostics,
    build_sample_payload,
    build_scoring_config_summary,
    build_stage_counts,
)


def _breakdown(content_id: int, **overrides) -> ScoreBreakdown:
    data = {
        "content_id": content_id,
        "base_score": 70,
        "source_bonus": 0,
        "quality_factor": 1.0,
        "risk_factor": 1.0,
        "time_decay": 0.9,
        "diversity_factor": 1.0,
        "final_score": 70,
        "dimension_scores": {"info_density": 20},
        "selected": True,
        "threshold_used": 60,
    }
    data.update(overrides)
    return ScoreBreakdown(**data)


def _scoring_input(content_id: int) -> ScoringInput:
    return ScoringInput(content_id=content_id, title=f"item {content_id}", source_name="source")


class _Content:
    id = 1
    title = "候选内容"
    url = "https://example.com"
    source_name = "知乎"
    category = "AI"


def test_build_stage_counts_uses_consistent_funnel_keys():
    scored = [
        (_breakdown(1), _scoring_input(1)),
        (_breakdown(2, quality_factor=0.55, selected=False), _scoring_input(2)),
        (_breakdown(3, risk_factor=0.55, selected=False), _scoring_input(3)),
    ]

    stages = build_stage_counts(scored)

    assert [stage["key"] for stage in stages] == [
        "candidates",
        "quality",
        "risk",
        "freshness",
        "diversity",
        "selected",
    ]
    assert stages[0]["count"] == 3
    assert stages[1]["count"] == 2
    assert stages[-1]["count"] == 1


def test_build_sample_payload_keeps_breakdown_and_feedback_fields():
    breakdown = _breakdown(1)
    scoring_input = _scoring_input(1)

    sample = build_sample_payload(
        breakdown,
        scoring_input,
        {1: _Content()},
        {1: 20.0},
    )

    assert sample["title"] == "候选内容"
    assert sample["source_name"] == "知乎"
    assert sample["feedback_score"] == 20.0
    assert sample["dimension_scores"] == {"info_density": 20}


def test_build_diagnostics_explains_empty_window():
    diagnostics = build_diagnostics(
        analyzed_total=12,
        window_total=0,
        loaded_count=0,
        scoring_input_count=0,
        scored_count=0,
        ignored_count=3,
        limit=160,
        sample_limit=80,
    )

    assert diagnostics["empty_reason"] == "no_content_in_window"
    assert diagnostics["analyzed_total"] == 12
    assert diagnostics["ignored_count"] == 3
    assert diagnostics["candidate_limit"] == 160


def test_build_scoring_config_summary_exposes_readonly_thresholds():
    config = build_scoring_config_summary()

    assert config["curation_mode"] in {"percentile", "fixed"}
    assert "curation_threshold" in config
    assert "risk_threshold" in config
    assert "quality_gate_floor" in config
