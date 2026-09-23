"""Private material recovery under the normal paid dispatch guard.

An operator-reviewed, root-owned host grant is passed through the private CLI.
The writable application data mount is never treated as authorization.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import settings
from app.integrations.rardar.project_identity import canonical_repository, project_id_for_repository
from app.services.llm.provider_budget import atomic, digest, file_lock, plain
from app.services.rardar_github_client import github_material_client
from app.services.rardar_material_diagnostics import material_failure_diagnostic

MAX_REQUESTS_PER_REPOSITORY = 6
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,119}\Z")
_GRANT_FIELDS = frozenset(
    {
        "schemaVersion",
        "authorizationId",
        "repository",
        "projectId",
        "mode",
        "maxProviderRequests",
        "priorReceiptSha256",
        "approvedPlanDigest",
        "approvedAt",
        "expiresAt",
        "reason",
    }
)


def _receipt_paths(root: Path, repository: str, authorization_id: str | None = None) -> tuple[Path, Path | None]:
    old = root / "material-corrections-v1" / f"{repository.replace('/', '--')}.json"
    plain(old, missing=True)
    if authorization_id is None:
        return old, None
    if not _OPERATION.fullmatch(authorization_id):
        raise ValueError("material_recovery_authorization_id_invalid")
    new = root / "material-corrections-v2" / f"{authorization_id}.json"
    plain(new, missing=True)
    return old, new


def _prior_receipt_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    raw = path.read_bytes()
    if len(raw) > 16_384:
        raise ValueError("material_recovery_prior_receipt_oversized")
    return hashlib.sha256(raw).hexdigest()


def _validate_grant(
    value: object, *, repository: str, project_id: str, mode: str, plan_digest: str, prior_digest: str | None
) -> dict:
    if not isinstance(value, dict) or set(value) != _GRANT_FIELDS or value.get("schemaVersion") != 1:
        raise ValueError("material_recovery_grant_schema_invalid")
    if not isinstance(value.get("authorizationId"), str):
        raise ValueError("material_recovery_grant_schema_invalid")
    if not _OPERATION.fullmatch(value["authorizationId"]):
        raise ValueError("material_recovery_authorization_id_invalid")
    if (
        value["repository"] != repository
        or value["projectId"] != project_id
        or value["mode"] != mode
        or value["approvedPlanDigest"] != plan_digest
        or value["priorReceiptSha256"] != prior_digest
        or type(value["maxProviderRequests"]) is not int
        or not 0 <= value["maxProviderRequests"] <= MAX_REQUESTS_PER_REPOSITORY
        or (mode == "generate" and value["maxProviderRequests"] == 0)
        or (mode == "cache-only" and value["maxProviderRequests"] != 0)
    ):
        raise ValueError("material_recovery_grant_scope_mismatch")
    if not isinstance(value["reason"], str) or not 8 <= len(value["reason"]) <= 240:
        raise ValueError("material_recovery_grant_reason_invalid")
    try:
        approved = datetime.fromisoformat(value["approvedAt"])
        expires = datetime.fromisoformat(value["expiresAt"])
    except (TypeError, ValueError) as exc:
        raise ValueError("material_recovery_grant_time_invalid") from exc
    now = datetime.now(UTC)
    if (
        approved.tzinfo is None
        or expires.tzinfo is None
        or approved > now
        or expires <= now
        or (expires - approved).total_seconds() > 86_400
    ):
        raise ValueError("material_recovery_grant_expired")
    return value


async def preview(repository: str, *, mode: str = "generate") -> dict:
    """Read-only, content-bound plan; this does not initialize a daily ledger."""
    from app.core.database import async_session
    from app.integrations.rardar import serving_profiles, trending_metadata
    from app.services.llm.daily_provider_budget import daily_budget_status
    from app.services.rardar_cache_reassembly import _source_witness, _stage_hashes
    from app.services.rardar_daily_operations import operation_root
    from app.services.rardar_llm_control import resolve_rardar_route_identity
    from app.services.rardar_trending import detail, saved_materials

    name = canonical_repository(repository)
    if mode not in {"cache-only", "generate"}:
        raise ValueError("material_recovery_mode_invalid")
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("material_correction_data_dir_unconfigured")
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    project_id = project_id_for_repository(name)
    fact = detail(project_id, None, historical=True)
    if fact.get("repository") != name or fact.get("projectId") != project_id:
        raise ValueError("material_recovery_fact_identity_mismatch")
    metadata = trending_metadata.read(target, fact)
    if metadata is None or metadata["githubRepositoryId"] != fact.get("githubRepositoryId"):
        raise ValueError("material_recovery_metadata_mismatch")
    existing = saved_materials(target, repositories={name}).get(name)
    old, _ = _receipt_paths(operation_root(), name)
    prior = _prior_receipt_digest(old)
    cache_root = target / "profile-cache"
    stage_hashes = _stage_hashes(cache_root, metadata["githubRepositoryId"])
    source_digest = None
    source_status = "missing"
    try:
        introduction, _ = _source_witness(cache_root, name, metadata["githubRepositoryId"])
        source_digest = introduction["evidence"]["digest"]
        source_status = "saved_and_bound"
    except (FileNotFoundError, KeyError, ValueError):
        if mode == "cache-only":
            raise
    stages = {key.split("/", 1)[0] for key in stage_hashes}
    missing = (
        []
        if existing and existing.get("materialState") == "complete"
        else [
            label
            for label, needed in (
                ("source", source_status != "saved_and_bound"),
                ("assessment", "rardar-assessments" not in stages),
            )
            if needed
        ]
    )
    route = await resolve_rardar_route_identity()
    core = {
        "schemaVersion": 1,
        "repository": name,
        "projectId": project_id,
        "githubRepositoryId": metadata["githubRepositoryId"],
        "mode": mode,
        "sourceGeneration": (existing or {}).get("material", {}).get("sourceGeneration"),
        "sourceEvidenceDigest": source_digest,
        "sourceStatus": source_status,
        "stageHashes": stage_hashes,
        "ruleVersions": serving_profiles._profile_identity_versions(),
        "routeIdentity": route,
        "existingMaterialDigest": digest(existing),
        "priorReceiptSha256": prior,
        "writeScope": ["profile-cache/profile-store/v2", "daily-operations/material-corrections-v2"],
    }
    if mode == "cache-only":
        from app.services.rardar_cache_reassembly import preview as cache_preview

        cache_plan, *_ = await cache_preview(name)
        core["cachePlanDigest"] = cache_plan.get("planDigest")
    core["planDigest"] = digest(core)
    if mode == "generate":
        async with async_session() as db:
            budget = await daily_budget_status(db)
    else:
        budget = {}
    return {
        **core,
        "state": "reused" if existing and existing.get("materialState") == "complete" else "incomplete",
        "missingStages": missing,
        "proposedPositioning": cache_plan.get("positioning") if mode == "cache-only" else None,
        "proposedEvidenceRefs": cache_plan.get("positioningEvidenceRefs") if mode == "cache-only" else None,
        "sourceRequests": "0" if mode == "cache-only" else "bounded; actual count known after execution",
        "providerRequestsMaximum": 0 if mode == "cache-only" else 6,
        "currentlyAvailableProviderRequests": 0
        if mode == "cache-only"
        else min(6, budget.get("backgroundRemaining", 0)),
        "budget": {
            key: budget.get(key)
            for key in ("day", "configured", "remaining", "backgroundRemaining", "interactiveReserve")
        },
        "admission": "ready"
        if mode == "cache-only" or budget.get("backgroundRemaining", 0) > 0
        else "budget_unavailable",
    }


async def apply_once(repository: str, *, mode: str, expected_plan_digest: str, operator_grant: dict) -> dict:
    """Spend at most one work slice; never debit or reset natural retry history.

    The receipt is written *before* any source/model request. An interrupted
    attempt remains spent rather than silently opening a second slice.
    """
    from app.integrations.rardar.serving_profiles import _digest
    from app.services.llm.daily_provider_budget import (
        ProviderWorkYield,
        daily_execution_budget,
        work_slice,
    )
    from app.services.rardar_daily_operations import operation_root
    from app.services.rardar_llm_control import resolve_rardar_route_identity
    from app.services.rardar_trending import (
        _collect_project_material,
        _history_with_materials,
        project_material,
        saved_materials,
    )

    name = canonical_repository(repository)
    if mode not in {"cache-only", "generate"} or not _SHA.fullmatch(expected_plan_digest):
        raise ValueError("material_recovery_apply_parameters_invalid")
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("material_correction_data_dir_unconfigured")
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    root = operation_root()
    plain(root)
    if not root.is_dir():
        raise ValueError("material_recovery_runtime_root_unavailable")

    with file_lock(root / "writer.lock", blocking=False):
        authorization_id = operator_grant.get("authorizationId") if isinstance(operator_grant, dict) else None
        if not isinstance(authorization_id, str):
            raise ValueError("material_recovery_grant_schema_invalid")
        _, receipt_path = _receipt_paths(root, name, authorization_id)
        assert receipt_path is not None
        if receipt_path.exists():
            prior = json.loads(receipt_path.read_bytes())
            if (
                prior.get("grantDigest") != digest(operator_grant)
                or prior.get("repository") != name
                or operator_grant.get("mode") != mode
            ):
                raise ValueError("material_recovery_receipt_grant_mismatch")
            return {
                "status": "already_attempted",
                "repository": name,
                "receipt": receipt_path.name,
                "originalStatus": prior.get("status"),
                "providerRequests": prior.get("providerRequests"),
            }
        plan = await preview(name, mode=mode)
        if plan["state"] == "reused":
            return {"status": "reused", "repository": name, "providerRequests": 0, "sourceRequests": 0}
        if plan["planDigest"] != expected_plan_digest:
            raise ValueError("material_recovery_plan_stale")
        grant = _validate_grant(
            operator_grant,
            repository=name,
            project_id=plan["projectId"],
            mode=mode,
            plan_digest=expected_plan_digest,
            prior_digest=plan["priorReceiptSha256"],
        )
        if mode == "cache-only":
            from app.services.rardar_cache_reassembly import apply_locked

            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt = {
                "schemaVersion": 2,
                "authorizationId": grant["authorizationId"],
                "grantDigest": digest(grant),
                "planDigest": expected_plan_digest,
                "priorReceiptSha256": plan["priorReceiptSha256"],
                "repository": name,
                "projectId": plan["projectId"],
                "startedAt": datetime.now(UTC).isoformat(),
                "status": "started",
                "providerRequests": 0,
                "sourceRequests": 0,
            }
            atomic(receipt_path, receipt)
            try:
                result = await apply_locked(name, plan["cachePlanDigest"])
                receipt.update(
                    status="completed" if result.get("materialState") == "complete" else "reused",
                    sourceGeneration=result.get("sourceGeneration"),
                    materialState=result.get("materialState", "complete"),
                    profileRevision=result.get("profileRevision"),
                )
            except Exception as exc:
                safe_code = str(exc) if isinstance(exc, ValueError) else ""
                receipt.update(
                    status="failed",
                    errorCode=safe_code if re.fullmatch(r"cache_reassembly_[a-z0-9_]+", safe_code) else "unknown",
                )
            finally:
                receipt["completedAt"] = datetime.now(UTC).isoformat()
                atomic(receipt_path, receipt)
            return {
                key: receipt.get(key)
                for key in (
                    "status",
                    "repository",
                    "projectId",
                    "providerRequests",
                    "sourceRequests",
                    "errorCode",
                    "materialState",
                    "profileRevision",
                )
            }
        current = _history_with_materials(target, saved_materials(target, repositories={name}), repositories={name})
        project = next((item for item in current["projects"] if item["repository"] == name), None)
        if project is None:
            raise LookupError("material_correction_project_not_found")

        budget = await daily_execution_budget("rardar_project_profile")
        if budget is None or budget[0].snapshot()["remaining"] <= 0:
            return {"status": "pending", "repository": name, "reason": "daily_budget_unavailable"}
        route = await resolve_rardar_route_identity()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schemaVersion": 2,
            "authorizationId": grant["authorizationId"],
            "grantDigest": digest(grant),
            "planDigest": expected_plan_digest,
            "priorReceiptSha256": plan["priorReceiptSha256"],
            "repository": name,
            "projectId": project["projectId"],
            "sourceGeneration": current["generationId"],
            "startedAt": datetime.now(UTC).isoformat(),
            "status": "started",
            "providerRequests": 0,
            "sourceRequests": 0,
        }
        atomic(receipt_path, receipt)
        source_requests = 0
        collected = None
        with work_slice(max_requests=grant["maxProviderRequests"], background=True) as work:
            try:
                async with github_material_client(settings.GITHUB_TOKEN) as client:

                    async def count_source(_request) -> None:
                        nonlocal source_requests
                        source_requests += 1

                    client.event_hooks["request"].append(count_source)
                    collected = await _collect_project_material(target, project, current["generationId"], client, route)
                material = project_material(collected.profile, collected.evidence)
                displayed = _history_with_materials(
                    target, saved_materials(target, repositories={name}), repositories={name}
                )
                saved = next(
                    (item for item in displayed["projects"] if item["projectId"] == project["projectId"]), None
                )
                if (
                    saved is None
                    or saved.get("materialState") != "complete"
                    or not ((saved.get("profile") or {}).get("positioning"))
                ):
                    raise ValueError("material_recovery_readback_incomplete")
                receipt.update(
                    status="completed",
                    sourceRevision=material["material"]["sourceRevision"],
                    profileDigest=_digest(collected.profile.model_dump(mode="json")),
                    materialState=saved["materialState"],
                    qualityState=collected.profile.qualityState,
                )
            except ProviderWorkYield as exc:
                receipt.update(status="yielded", errorCode=exc.code)
            except Exception as exc:
                error_code = (
                    getattr(collected, "profile_failure_code", None) or getattr(exc, "code", None) or type(exc).__name__
                )
                stage = "source" if isinstance(exc, httpx.HTTPError) else "profile"
                receipt.update(
                    status="failed",
                    stage=stage,
                    errorCode=error_code,
                    outerErrorCode=(
                        str(exc)
                        if isinstance(exc, ValueError)
                        and str(exc)
                        in {
                            "historical_profile_binding_invalid",
                            "historical_profile_reference_invalid",
                            "historical_profile_link_invalid",
                            "historical_profile_not_readable",
                            "material_recovery_readback_incomplete",
                        }
                        else "unknown"
                    ),
                    diagnostic=material_failure_diagnostic(exc, project=project, stage=stage, collected=collected),
                )
            finally:
                receipt.update(
                    completedAt=datetime.now(UTC).isoformat(),
                    providerRequests=work.used_requests,
                    sourceRequests=source_requests,
                )
                atomic(receipt_path, receipt)
        return {
            key: receipt.get(key)
            for key in (
                "status",
                "repository",
                "projectId",
                "providerRequests",
                "sourceRequests",
                "errorCode",
                "outerErrorCode",
                "stage",
                "diagnostic",
                "materialState",
                "qualityState",
            )
        }
