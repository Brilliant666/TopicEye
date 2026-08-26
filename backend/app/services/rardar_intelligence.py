"""Application service for the read-only Rardar intelligence integration."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.integrations.rardar import ExplosionBoardResponse, RardarIntelligenceAdapter


def load_explosion_board(config: Settings = settings) -> ExplosionBoardResponse:
    """Load one audited Rardar generation without touching TopicEye persistence."""
    return RardarIntelligenceAdapter.from_config(config.RARDAR_INTELLIGENCE_DATA_DIR).load_explosion_board()
