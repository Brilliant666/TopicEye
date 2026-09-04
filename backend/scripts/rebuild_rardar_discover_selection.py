"""Build, validate, publish, inspect, or roll back local worth-seeing Selection."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.rardar.selection import build_selection, selection_input_digest
from app.integrations.rardar.selection_serving import (
    SelectionServingError,
    SelectionServingLoader,
    artifact_activation_state,
    build_selection_serving,
    install_selection_serving,
    rollback_selection,
)
from app.integrations.rardar.selection_source import SelectionSourceAdapter
from app.services.rardar_llm_control import resolve_rardar_route_identity

StageReporter = Callable[[str], None]
_DEFAULT_BUILD_TIMEOUT_SECONDS = 7200


async def rebuild(
    target: Path,
    *,
    recall_limit: int = 48,
    timeout_seconds: int = _DEFAULT_BUILD_TIMEOUT_SECONDS,
    report_stage: StageReporter | None = None,
    force_retryable: bool = False,
) -> dict[str, object]:
    report = report_stage or (lambda _stage: None)
    target = target.resolve()
    report("source_validation")
    source = SelectionSourceAdapter.from_config(str(target)).load()
    cache_root = target / "selection-profile-cache"
    report("route_and_input_digest")
    route_before = await resolve_rardar_route_identity()
    expected_input = selection_input_digest(
        source,
        cache_root=cache_root,
        model_route_identity=route_before,
        recall_limit=recall_limit,
    )
    loader = SelectionServingLoader(target)
    report("idempotence_check")
    try:
        active = loader.validate_generation()
    except SelectionServingError as exc:
        if exc.code != "rardar_selection_not_configured":
            raise
    else:
        if (
            active.inputDigest == expected_input
            and artifact_activation_state(active) in {"ready", "empty"}
            and not force_retryable
        ):
            report("complete")
            return {
                "status": "healthy",
                "selectionGenerationId": active.selectionGenerationId,
                "sourceObservationSetId": active.sourceObservationSetId,
                "created": False,
                "changed": False,
                "modelCalls": 0,
                "githubRequests": 0,
                "publishedCount": active.publishedCount,
            }
    if not force_retryable and hasattr(loader, "load_latest_attempt_with_etag"):
        try:
            latest_snapshot, _etag = loader.load_latest_attempt_with_etag()
            latest_artifact = loader.load_artifact(latest_snapshot.selectionGenerationId)
        except SelectionServingError:
            pass
        else:
            retry_deferred = latest_snapshot.nextRetryAt is not None and latest_snapshot.nextRetryAt > datetime.now(UTC)
            if (
                artifact_activation_state(latest_artifact) == "degraded"
                and latest_artifact.inputDigest == expected_input
                and retry_deferred
            ):
                report("complete")
                return {
                    "status": "degraded",
                    "state": "degraded",
                    "selectionGenerationId": latest_artifact.selectionGenerationId,
                    "sourceObservationSetId": latest_artifact.sourceObservationSetId,
                    "created": False,
                    "changed": False,
                    "modelCalls": 0,
                    "githubRequests": 0,
                    "publishedCount": 0,
                }
    report("selection_build")
    try:
        built = await asyncio.wait_for(
            build_selection(
                source=source,
                cache_root=cache_root,
                recall_limit=recall_limit,
                model_route_identity=route_before,
                force_retryable=force_retryable,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise SelectionServingError(
            "rardar_selection_build_timeout",
            "The bounded worth-seeing Selection build timed out before activation",
        ) from exc
    report("route_revalidation")
    route_after = await resolve_rardar_route_identity()
    if route_after != route_before:
        raise SelectionServingError(
            "rardar_selection_route_changed",
            "The configured Rardar model route changed during the build",
        )
    serving = build_selection_serving(built)
    report("atomic_activation")
    installed = install_selection_serving(target, serving)
    report("serving_validation")
    validated = loader.validate_generation(installed.selection_generation_id)
    report("complete")
    state = artifact_activation_state(validated)
    return {
        "status": "healthy" if state in {"ready", "empty"} else "degraded",
        "state": state,
        "selectionGenerationId": installed.selection_generation_id,
        "sourceObservationSetId": installed.source_observation_set_id,
        "created": installed.created,
        "changed": installed.changed,
        "modelCalls": validated.usage.modelCalls,
        "githubRequests": validated.usage.githubRequests,
        "publishedCount": validated.publishedCount,
    }


def status(target: Path) -> dict[str, object]:
    loader = SelectionServingLoader(target.resolve())
    try:
        snapshot, _etag = loader.load_latest_attempt_with_etag()
        artifact = loader.validate_generation(snapshot.selectionGenerationId)
    except SelectionServingError as exc:
        if exc.code != "rardar_selection_not_configured":
            try:
                artifact = loader.validate_generation()
            except SelectionServingError:
                raise exc from None
            state = artifact_activation_state(artifact)
            snapshot = None
        else:
            return {
                "mode": "shadow",
                "status": "healthy",
                "state": "not_configured",
                "rawGenerationId": None,
                "servingGenerationId": None,
                "eligibleCount": 0,
                "recalledCount": 0,
                "selectedCount": 0,
                "publishedCount": 0,
                "failedCount": 0,
                "nextAction": "run build-selection",
            }
    else:
        state = artifact_activation_state(artifact)
    return {
        "mode": "shadow",
        "status": "healthy" if state in {"ready", "empty"} else "degraded",
        "state": state,
        "selectionGenerationId": artifact.selectionGenerationId,
        "rawGenerationId": artifact.selectionGenerationId,
        "servingGenerationId": artifact.selectionGenerationId,
        "sourceObservationSetId": artifact.sourceObservationSetId,
        "sourceTodayGenerationId": artifact.todayGenerationId,
        "latestCaptureId": artifact.latestCaptureId,
        "latestCaptureAt": artifact.latestCaptureAt.isoformat(),
        "eligibleCount": artifact.universeCount,
        "recalledCount": artifact.recalledCount,
        "assessedCount": artifact.assessedCount,
        "selectedCount": artifact.decisionCounts.get("SELECT_NOW", 0),
        "publishedCount": artifact.publishedCount,
        "failedCount": sum(artifact.failureSummary.values()),
        "profileReadyCount": artifact.profileReadyCount,
        "profileCoverage": artifact.profileCoverage,
        "systemicFailureCodes": artifact.systemicFailureCodes,
        "currentEligible": artifact.currentEligible,
        "nextRetryAt": snapshot.nextRetryAt.isoformat() if snapshot and snapshot.nextRetryAt else None,
        "nextAction": (
            "review local Discover"
            if state == "ready"
            else "review empty selection evidence"
            if state == "empty"
            else "retry recoverable profile failures"
        ),
        "modelCalls": artifact.usage.modelCalls,
        "githubRequests": artifact.usage.githubRequests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage immutable local Rardar worth-seeing Selection")
    parser.add_argument("command", choices=("build", "status", "rollback"), nargs="?", default="build")
    parser.add_argument("generation", nargs="?")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--recall-limit", type=int, default=48, choices=range(30, 61), metavar="30..60")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=_DEFAULT_BUILD_TIMEOUT_SECONDS,
        choices=range(60, 43201),
        metavar="60..43200",
    )
    parser.add_argument(
        "--retry-retryable-now",
        action="store_true",
        help="Explicitly retry bounded transient profile failures before their next retry time",
    )
    arguments = parser.parse_args()

    def report_stage(stage: str) -> None:
        print(
            json.dumps(
                {"event": "selection_build_stage", "stage": stage, "at": datetime.now(UTC).isoformat()},
                sort_keys=True,
            ),
            file=sys.stderr,
            flush=True,
        )

    try:
        if arguments.command == "build":
            result = asyncio.run(
                rebuild(
                    arguments.target,
                    recall_limit=arguments.recall_limit,
                    timeout_seconds=arguments.timeout_seconds,
                    report_stage=report_stage,
                    force_retryable=arguments.retry_retryable_now,
                )
            )
        elif arguments.command == "status":
            result = status(arguments.target)
        else:
            if not arguments.generation:
                parser.error("rollback requires a generation ID")
            installed = rollback_selection(arguments.target.resolve(), arguments.generation)
            result = {
                "status": "healthy",
                "selectionGenerationId": installed.selection_generation_id,
                "sourceObservationSetId": installed.source_observation_set_id,
                "changed": installed.changed,
            }
    except Exception as exc:
        code = getattr(exc, "code", "rardar_selection_rebuild_failed")
        print(json.dumps({"status": "failed", "code": code}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
