"""One-use, allowlisted material correction under the normal paid dispatch guard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import settings
from app.integrations.rardar.project_identity import canonical_repository
from app.services.llm.provider_budget import atomic, file_lock
from app.services.rardar_github_client import github_material_client
from app.services.rardar_material_diagnostics import material_failure_diagnostic

ALLOWED_REPOSITORIES = frozenset(
    {
        "albert-weasker/niubigeo",
        "anthropics/financial-services",
        "craterserpentglow/discord-server-raider",
    }
)
MAX_REQUESTS_PER_REPOSITORY = 6


async def apply_once(repository: str) -> dict:
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
    if name not in ALLOWED_REPOSITORIES:
        raise ValueError("material_correction_repository_not_allowed")
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise ValueError("material_correction_data_dir_unconfigured")
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    receipt_dir = root / "material-corrections-v1"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / (name.replace("/", "--") + ".json")

    with file_lock(root / "writer.lock", blocking=False):
        if receipt_path.exists():
            return {"status": "already_attempted", "repository": name, "receipt": receipt_path.name}
        current = _history_with_materials(target, saved_materials(target))
        project = next((item for item in current["projects"] if item["repository"] == name), None)
        if project is None:
            raise LookupError("material_correction_project_not_found")
        if project.get("displayProfile") is not None and project.get("materialState") != "partial":
            return {"status": "reused", "repository": name, "providerRequests": 0, "sourceRequests": 0}

        budget = await daily_execution_budget("rardar_project_profile")
        if budget is None or budget[0].snapshot()["remaining"] <= 0:
            return {"status": "pending", "repository": name, "reason": "daily_budget_unavailable"}
        route = await resolve_rardar_route_identity()
        receipt = {
            "schemaVersion": 1,
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
        with work_slice(max_requests=MAX_REQUESTS_PER_REPOSITORY, background=True) as work:
            try:
                async with github_material_client(settings.GITHUB_TOKEN) as client:

                    async def count_source(_request) -> None:
                        nonlocal source_requests
                        source_requests += 1

                    client.event_hooks["request"].append(count_source)
                    collected = await _collect_project_material(target, project, current["generationId"], client, route)
                material = project_material(collected.profile, collected.evidence)
                displayed = _history_with_materials(target, saved_materials(target))
                saved = next(
                    (item for item in displayed["projects"] if item["projectId"] == project["projectId"]), None
                )
                if (
                    saved is None
                    or saved.get("materialState") != "complete"
                    or not ((saved.get("profile") or {}).get("positioning"))
                ):
                    raise ValueError("material_correction_readback_incomplete")
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
                "stage",
                "diagnostic",
                "materialState",
                "qualityState",
            )
        }
