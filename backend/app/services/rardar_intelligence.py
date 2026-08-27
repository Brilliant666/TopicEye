"""Application service for the read-only Rardar intelligence integration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.config import Settings, settings
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError, RardarIntelligenceAdapter
from app.integrations.rardar.sync import load_sync_metadata

_DEMO_BOARD = Path(__file__).parents[1] / "integrations" / "rardar" / "fixtures" / "explosion-board-demo-v1.json"


def _demo_allowed(config: Settings) -> bool:
    return config.RARDAR_DATA_MODE == "demo" and not config.is_production


def _load_demo_board() -> ExplosionBoardResponse:
    return ExplosionBoardResponse.model_validate_json(_DEMO_BOARD.read_text(encoding="utf-8"), strict=True)


def load_explosion_board(config: Settings = settings) -> ExplosionBoardResponse:
    """Load one audited Rardar generation without touching TopicEye persistence."""
    if _demo_allowed(config):
        return _load_demo_board()
    try:
        board = RardarIntelligenceAdapter.from_config(config.RARDAR_INTELLIGENCE_DATA_DIR).load_explosion_board()
    except RardarArtifactError as exc:
        if config.RARDAR_DATA_MODE == "real" and exc.code in {
            "rardar_intelligence_not_configured",
            "rardar_intelligence_unavailable",
        }:
            return ExplosionBoardResponse(
                state="not_synced",
                reason="real_data_not_synced",
                dataMode="real",
                dataLabel="真实数据尚未同步",
            )
        raise
    if board.generationId:
        metadata = load_sync_metadata(config.RARDAR_INTELLIGENCE_DATA_DIR, board.generationId)
        if metadata:
            board = board.model_copy(
                update={
                    "syncedAt": datetime.fromisoformat(metadata["syncedAt"]),
                    "sourceHost": metadata["sourceHost"],
                    "manifestSha256": metadata["manifestSha256"],
                    "artifactSha256": metadata["artifactSha256"],
                    "dataLabel": "Rardar 生产快照",
                }
            )
    return board
