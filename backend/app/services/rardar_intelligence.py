"""Application service for the read-only Rardar intelligence integration."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, settings
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError, RardarIntelligenceAdapter

_DEMO_BOARD = Path(__file__).parents[1] / "integrations" / "rardar" / "fixtures" / "explosion-board-demo-v1.json"


def _demo_allowed(config: Settings) -> bool:
    return config.RARDAR_DEMO_DATA_ENABLED and not config.is_production


def _load_demo_board() -> ExplosionBoardResponse:
    return ExplosionBoardResponse.model_validate_json(_DEMO_BOARD.read_text(encoding="utf-8"), strict=True)


def load_explosion_board(config: Settings = settings) -> ExplosionBoardResponse:
    """Load one audited Rardar generation without touching TopicEye persistence."""
    try:
        board = RardarIntelligenceAdapter.from_config(config.RARDAR_INTELLIGENCE_DATA_DIR).load_explosion_board()
    except RardarArtifactError as exc:
        if _demo_allowed(config) and exc.code in {
            "rardar_intelligence_not_configured",
            "rardar_intelligence_unavailable",
        }:
            return _load_demo_board()
        raise
    if board.state == "not_ready" and _demo_allowed(config):
        return _load_demo_board()
    return board
