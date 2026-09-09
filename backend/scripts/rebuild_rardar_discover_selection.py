"""Build, validate, publish, inspect, or roll back local worth-seeing Selection."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.rardar.selection import (
    build_selection,
    default_recall_batch_id,
    selection_input_digest,
)
from app.integrations.rardar.selection_execution import selection_writer
from app.integrations.rardar.selection_serving import (
    SelectionServingError,
    SelectionServingLoader,
    artifact_activation_state,
    build_selection_serving,
    install_selection_serving,
    rollback_selection,
)
from app.integrations.rardar.selection_source import SelectionSourceAdapter
from app.integrations.rardar.serving import ServingProjectionLoader
from app.services.rardar_llm_control import resolve_rardar_route_identity

StageReporter = Callable[[str], None]
_DEFAULT_BUILD_TIMEOUT_SECONDS = 7200


def _cache_replay_binding_mismatches(active, replay) -> list[str]:
    """Compare stable evidence/result bindings, not the mutable cache inventory."""

    fields = (
        "sourceObservationSetId",
        "todayGenerationId",
        "sourceFactDigest",
        "profileRevisionSetDigest",
        "profileBindingSetDigest",
        "assessmentResultDigest",
        "modelRouteIdentity",
        "contractVersions",
        "protocolMode",
        "candidateUniverseVersion",
        "recallBatchId",
        "executionMode",
        "recalledCandidateIds",
        "processedCandidateIds",
        "unprocessedCandidateIds",
    )
    return [field for field in fields if getattr(active, field) != getattr(replay, field)]


def _cache_replay_hits(artifact) -> tuple[int, int, int]:
    profile_hits = sum(item.profileCacheState == "hit" for item in artifact.assessments)
    gate_hits = sum(item.gate is not None and item.gateCacheHit for item in artifact.assessments)
    copy_hits = sum(item.copyResult is not None and item.copyCacheHit for item in artifact.assessments)
    expected_profile_hits = (
        artifact.profileReadyCount if artifact.profileReadyCount is not None else artifact.assessedCount
    )
    if (
        artifact.usage.modelCalls != 0
        or profile_hits != expected_profile_hits
        or gate_hits != artifact.gateAssessedCount
        or any(
            item.publicationDisposition == "publish" and (item.copyResult is None or not item.copyCacheHit)
            for item in artifact.assessments
        )
    ):
        raise SelectionServingError(
            "rardar_selection_cache_verification_miss",
            "Cache verification found a per-project Profile, Value, or copy miss",
        )
    return profile_hits, gate_hits, copy_hits


async def rebuild(target: Path, **kwargs) -> dict[str, object]:
    with selection_writer(target):
        return await _rebuild(target, **kwargs)


async def _rebuild(
    target: Path,
    *,
    recall_limit: int = 48,
    recall_batch_id: str | None = None,
    timeout_seconds: int = _DEFAULT_BUILD_TIMEOUT_SECONDS,
    report_stage: StageReporter | None = None,
    force_retryable: bool = False,
    process_candidate_ids: tuple[int, ...] | None = None,
    verify_cache_reuse: bool = False,
    provider_calls_allowed: bool = True,
    expected_source_id: str | None = None,
    expected_today_generation: str | None = None,
    expected_route_identity: str | None = None,
) -> dict[str, object]:
    report = report_stage or (lambda _stage: None)
    target = target.resolve()
    report("source_validation")
    source = SelectionSourceAdapter.from_config(str(target)).load()

    def verify_frozen_source():
        current = SelectionSourceAdapter.from_config(str(target)).load()
        if current.source_observation_set_id != source.source_observation_set_id or (
            expected_source_id is not None and current.source_observation_set_id != expected_source_id
        ):
            raise SelectionServingError("rardar_selection_source_changed", "Selection source changed")
        if expected_today_generation is not None:
            today, _etag = ServingProjectionLoader(str(target)).load_today_with_etag()
            if (
                today.generationId != expected_today_generation
                or current.today_generation_id != expected_today_generation
            ):
                raise SelectionServingError("rardar_selection_source_changed", "Today source changed")

    verify_frozen_source()
    recall_batch_id = recall_batch_id or default_recall_batch_id(source)
    cache_root = target / "selection-profile-cache"
    report("route_and_input_digest")
    route_before = await resolve_rardar_route_identity()
    if expected_route_identity is not None and route_before != expected_route_identity:
        raise SelectionServingError("rardar_selection_route_changed", "Configured route changed after confirmation")
    expected_input = selection_input_digest(
        source,
        cache_root=cache_root,
        model_route_identity=route_before,
        recall_limit=recall_limit,
        recall_batch_id=recall_batch_id,
        process_candidate_ids=process_candidate_ids,
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
            and not verify_cache_reuse
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
    if not force_retryable and not verify_cache_reuse and hasattr(loader, "load_latest_attempt_with_etag"):
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
                recall_batch_id=recall_batch_id,
                model_route_identity=route_before,
                force_retryable=force_retryable,
                process_candidate_ids=process_candidate_ids,
                provider_calls_allowed=provider_calls_allowed and not verify_cache_reuse,
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
    if verify_cache_reuse:
        try:
            active = loader.validate_generation()
        except SelectionServingError as exc:
            raise SelectionServingError(
                "rardar_selection_cache_verification_requires_current",
                "Cache verification requires a validated current Selection",
            ) from exc
        if _cache_replay_binding_mismatches(active, built.artifact):
            raise SelectionServingError(
                "rardar_selection_cache_verification_mismatch",
                "Per-project cache replay did not reproduce the active Selection inputs and results",
            )
        profile_hits, gate_hits, copy_hits = _cache_replay_hits(built.artifact)
        report("complete")
        return {
            "status": "healthy",
            "state": artifact_activation_state(active),
            "selectionGenerationId": active.selectionGenerationId,
            "sourceObservationSetId": active.sourceObservationSetId,
            "created": False,
            "changed": False,
            "cacheVerification": True,
            "modelCalls": built.artifact.usage.modelCalls,
            "cacheHits": built.artifact.usage.cacheHits,
            "profileCacheHits": profile_hits,
            "gateCacheHits": gate_hits,
            "copyCacheHits": copy_hits,
            "githubRequests": built.artifact.usage.githubRequests,
            "publishedCount": active.publishedCount,
            "processedCandidateIds": list(active.processedCandidateIds),
        }
    serving = build_selection_serving(built)
    verify_frozen_source()
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
        "recallBatchId": validated.recallBatchId,
        "executionMode": validated.executionMode,
        "processedCandidateIds": list(validated.processedCandidateIds),
        "unprocessedCandidateIds": list(validated.unprocessedCandidateIds),
        "cacheHits": validated.usage.cacheHits,
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
        "executionMode": artifact.executionMode,
        "processedCandidateIds": list(artifact.processedCandidateIds),
        "unprocessedCandidateIds": list(artifact.unprocessedCandidateIds),
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
        "--recall-batch-id",
        help="Stable explicit batch identity; defaults to the current source revision",
    )
    parser.add_argument(
        "--process-candidate-id",
        dest="process_candidate_ids",
        type=int,
        action="append",
        help="Explicit small-batch numeric repository ID; repeat exactly six times in stable recall order",
    )
    parser.add_argument(
        "--verify-cache-reuse",
        action="store_true",
        help="Traverse per-project caches with Provider calls disabled; validate against current without publishing",
    )
    parser.add_argument(
        "--provider-calls-disabled",
        action="store_true",
        help="Fail closed on any model cache miss while retaining normal validated publication behavior",
    )
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
                    recall_batch_id=arguments.recall_batch_id,
                    timeout_seconds=arguments.timeout_seconds,
                    report_stage=report_stage,
                    force_retryable=arguments.retry_retryable_now,
                    process_candidate_ids=(
                        tuple(arguments.process_candidate_ids) if arguments.process_candidate_ids is not None else None
                    ),
                    verify_cache_reuse=arguments.verify_cache_reuse,
                    provider_calls_allowed=not arguments.provider_calls_disabled,
                )
            )
        elif arguments.command == "status":
            result = status(arguments.target)
        else:
            if not arguments.generation:
                parser.error("rollback requires a generation ID")
            with selection_writer(arguments.target):
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
