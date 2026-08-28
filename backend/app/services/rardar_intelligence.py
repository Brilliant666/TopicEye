"""Application service for the read-only Rardar intelligence integration."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, settings
from app.integrations.rardar import ExplosionBoardResponse, RardarArtifactError
from app.integrations.rardar.schemas import ExactExplosionProject
from app.integrations.rardar.serving import ServingProjectionLoader, build_serving_projection
from app.integrations.rardar.serving_schemas import ServingProjectDetail, ServingTodaySnapshot

_DEMO_BOARD = Path(__file__).parents[1] / "integrations" / "rardar" / "fixtures" / "explosion-board-demo-v1.json"


def _demo_allowed(config: Settings) -> bool:
    return config.RARDAR_DATA_MODE == "demo" and not config.is_production


def _load_demo_board() -> ExplosionBoardResponse:
    return ExplosionBoardResponse.model_validate_json(_DEMO_BOARD.read_text(encoding="utf-8"), strict=True)


def load_explosion_board(config: Settings = settings) -> ExplosionBoardResponse:
    """Load the compact serving projection without re-auditing raw captures."""
    if _demo_allowed(config):
        return _load_demo_board()
    try:
        snapshot, _etag = ServingProjectionLoader(config.RARDAR_INTELLIGENCE_DATA_DIR).load_today_with_etag()
    except RardarArtifactError as exc:
        if config.RARDAR_DATA_MODE == "real" and exc.code in {
            "rardar_intelligence_not_configured",
            "rardar_intelligence_unavailable",
            "rardar_serving_unavailable",
        }:
            return ExplosionBoardResponse(
                state="not_synced",
                reason="real_data_not_synced",
                dataMode="real",
                dataLabel="真实数据尚未同步",
            )
        raise
    return ExplosionBoardResponse(
        state=snapshot.state,
        reason=snapshot.reason,
        generationId=snapshot.generationId,
        publishedAt=snapshot.publishedAt,
        capturedAt=snapshot.capturedAt,
        window=snapshot.window,
        coverage=snapshot.coverage,
        exactRanked=[
            ExactExplosionProject.model_validate(
                project.model_dump(
                    exclude={
                        "profileState",
                        "officialSummaryZh",
                        "sourceLabel",
                        "sourceLanguage",
                        "capabilityBulletsZh",
                        "translationState",
                    }
                ),
                strict=True,
            )
            for project in snapshot.exactRanked
        ],
        pendingRanked=snapshot.pendingRanked,
        conflictCount=snapshot.conflictCount,
        sourceStatus=snapshot.sourceStatus,
        dataMode="real",
        dataLabel=snapshot.dataLabel,
        syncedAt=snapshot.syncedAt,
        sourceHost=snapshot.sourceHost,
        manifestSha256=snapshot.manifestSha256,
        artifactSha256=snapshot.artifactSha256,
    )


def load_today_snapshot(config: Settings = settings) -> tuple[ServingTodaySnapshot, str]:
    if _demo_allowed(config):
        board = _load_demo_board()
        built = build_serving_projection(
            board=board,
            source_manifest_sha256=board.manifestSha256 or "a" * 64,
            source_explosion_sha256=board.artifactSha256 or "b" * 64,
            synced_at=board.syncedAt,
            source_host=board.sourceHost,
            cache_root=Path("."),
        )
        snapshot = ServingTodaySnapshot.model_validate_json(built.files["today.json"], strict=True)
        return snapshot, f'"{built.manifest_sha256}"'
    return ServingProjectionLoader(config.RARDAR_INTELLIGENCE_DATA_DIR).load_today_with_etag()


def load_project_detail(
    github_repository_id: int,
    generation_id: str,
    config: Settings = settings,
) -> tuple[ServingProjectDetail, str]:
    if _demo_allowed(config):
        board = _load_demo_board()
        built = build_serving_projection(
            board=board,
            source_manifest_sha256=board.manifestSha256 or "a" * 64,
            source_explosion_sha256=board.artifactSha256 or "b" * 64,
            synced_at=board.syncedAt,
            source_host=board.sourceHost,
            cache_root=Path("."),
        )
        from app.integrations.rardar.serving import _strict_model
        from app.integrations.rardar.serving_schemas import ProjectEvidenceProjection, ServingProjectRecord

        project_raw = built.files.get(f"projects/{github_repository_id}.json")
        evidence_raw = built.files.get(f"evidence/{github_repository_id}.json")
        if project_raw is None or evidence_raw is None or generation_id != board.generationId:
            raise RardarArtifactError("rardar_serving_project_not_found", "Project is absent from this snapshot")
        record = _strict_model(project_raw, ServingProjectRecord, "rardar_serving_project_invalid")
        evidence = _strict_model(evidence_raw, ProjectEvidenceProjection, "rardar_serving_evidence_invalid")
        return (
            ServingProjectDetail(
                schemaVersion=1,
                generationId=generation_id,
                servingGenerationId=built.serving_generation_id,
                project=record.project,
                profile=record.profile,
                evidence=evidence,
            ),
            f'"{built.manifest_sha256}"',
        )
    return ServingProjectionLoader(config.RARDAR_INTELLIGENCE_DATA_DIR).load_project_with_etag(
        github_repository_id,
        generation_id,
    )
