"""Explosion-board composition without changing the authoritative fact order."""

from __future__ import annotations

from app.core.product_profile import get_product_profile
from app.rardar.ai_runtime import RardarAIError, call_rardar_ai
from app.rardar.artifact_adapter import RardarIntelligenceAdapter
from app.rardar.schemas import AIProjectProfile


async def build_explosion_board(*, ai_scenario: str = "success") -> dict:
    profile = get_product_profile()
    artifact = RardarIntelligenceAdapter(profile.fixture_root).load_explosion_board()
    exact_top: list[dict] = []
    for project in artifact.exactTop:
        payload = {
            "mockScenario": ai_scenario,
            "repository": project.repository,
            "projectId": project.projectId,
            "sourceRevision": artifact.artifactRevision,
            "evidenceRefs": [f"{source.kind}:{source.label}" for source in project.sourceProvenance],
            "facts": {
                "rank": project.rank,
                "observedStarDelta": project.observedStarDelta,
                "totalStars": project.totalStars,
                "pushedAt": project.pushedAt.isoformat(),
            },
        }
        try:
            outcome = await call_rardar_ai(
                scene="rardar_explosion_reason",
                reasoning_effort="high",
                payload=payload,
                result_model=AIProjectProfile,
            )
            ai_payload = {
                "state": outcome.audit["resultState"],
                "profile": outcome.result.model_dump(mode="json"),
                "audit": outcome.audit,
            }
        except RardarAIError as exc:
            ai_payload = {
                "state": exc.state.value,
                "profile": None,
                "errorCode": exc.code,
                "label": "AI 分析暂不可用；事实排名与仓库证据仍然有效",
            }
        exact_top.append({**project.model_dump(mode="json"), "ai": ai_payload})

    return {
        "productProfile": profile.key,
        "generationId": artifact.generationId,
        "artifactVersion": artifact.artifactVersion,
        "artifactRevision": artifact.artifactRevision,
        "schemaVersion": artifact.schemaVersion,
        "capturedAt": artifact.capturedAt.isoformat(),
        "publishedAt": artifact.publishedAt.isoformat(),
        "windowStartedAt": artifact.windowStartedAt.isoformat(),
        "windowEndedAt": artifact.windowEndedAt.isoformat(),
        "rankingContract": "observedStarDelta DESC, totalStars DESC, repository ASC",
        "aiChangesRanking": False,
        "exactTop": exact_top,
        "firstSeenPending": [item.model_dump(mode="json") for item in artifact.firstSeenPending],
        "coverageState": artifact.coverageState,
        "sourceSummary": artifact.sourceSummary,
        "coverage": artifact.coverage.model_dump(mode="json"),
    }
