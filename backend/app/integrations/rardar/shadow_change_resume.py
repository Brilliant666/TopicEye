"""Read-only origin verification for the explicitly authorized six-change resume."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.integrations.rardar.adapter import _SafeRoot
from app.integrations.rardar.meaningful_change import change_context
from app.integrations.rardar.selection import (
    _contract_versions,
    _source_identities,
    build_candidate_universe,
    negative_control_cases,
)
from app.integrations.rardar.selection_schemas import SelectionGateResult, SelectionTimeliness
from app.integrations.rardar.shadow_cohort import ShadowIntegrityError, healthy_pool
from app.integrations.rardar.shadow_schemas import ShadowReviewArtifact
from app.services.llm.provider_budget import ProviderBudgetLedger, digest

RESUME_VERSION = "meaningful-change-evidence-v1"
ARTIFACT_NAME = "shadow-review-artifact-change-v4.json"


def signed_json(root: Path, relative: str) -> dict:
    value = json.loads(_SafeRoot(str(root)).read_stable(relative, maximum_bytes=8 * 1024 * 1024))
    if value.get("digest") != digest({k: v for k, v in value.items() if k != "digest"}):
        raise ShadowIntegrityError("shadow_resume_digest_invalid")
    return value


@dataclass
class ResumeInputs:
    source_freeze: dict
    cohort: dict
    source: object
    recalled: list
    pool: list
    origin: ShadowReviewArtifact
    origin_binding: str
    change_contexts: dict
    run_dir: Path

    def legacy(self, key: str) -> dict | None:
        if key.startswith("timeliness-") and int(key.split("-")[1]) in self.change_contexts:
            return None
        if key.startswith("copy-"):
            return None
        row = signed_json(self.run_dir, f"stage-receipts/{key}.json")
        if (
            row.get("binding") != self.origin_binding
            or row.get("key") != key
            or row.get("state") not in {"started", "completed"}
        ):
            raise ShadowIntegrityError("shadow_legacy_receipt_binding_invalid")
        if key.startswith("timeliness-") and row.get("attempts") != 0:
            raise ShadowIntegrityError("shadow_unapproved_meaningful_retry")
        return row


def load_resume_inputs(mirror: Path, run_dir: Path, ledger: ProviderBudgetLedger, route: str) -> ResumeInputs:
    """Never calls freeze, a provider, profile generation, or a migration."""
    source_freeze = signed_json(run_dir, "shadow-source-freeze-manifest.json")
    cohort = signed_json(run_dir, "shadow-review-cohort-manifest.json")
    origin = ShadowReviewArtifact.model_validate_json(
        _SafeRoot(str(run_dir)).read_stable("shadow-review-artifact.json", maximum_bytes=8 * 1024 * 1024),
        strict=True,
    )
    if (
        origin.sourceFreezeDigest != source_freeze["digest"]
        or origin.cohortManifestDigest != cohort["digest"]
        or cohort["sourceFreezeDigest"] != source_freeze["digest"]
        or origin.cohortAssessed != 16
        or origin.negativeControlCount != 6
        or origin.negativeControlViolations
        or origin.providerBudget["attempted"] != 28
        or origin.providerBudget["runId"] != ledger.run_id
        or origin.reviewable
        or cohort.get("selectionPolicyVersion") != origin.policyVersions
        or source_freeze.get("negativeControlsDigest") != digest(negative_control_cases())
    ):
        raise ShadowIntegrityError("shadow_resume_origin_invalid")
    current_policies = _contract_versions()
    if any(v != current_policies.get(k) for k, v in origin.policyVersions.items() if k != "timelinessPrompt"):
        raise ShadowIntegrityError("shadow_resume_unapproved_policy_change")
    origin_binding = digest(
        {
            "source": source_freeze["digest"],
            "cohort": cohort["digest"],
            "route": route,
            "policy": origin.policyVersions,
            "runId": ledger.run_id,
        }
    )
    saved_binding = json.loads(_SafeRoot(str(run_dir)).read_stable("shadow-run-binding.json", maximum_bytes=4096))
    if saved_binding != {"binding": origin_binding}:
        raise ShadowIntegrityError("shadow_resume_model_route_or_origin_changed")
    before = origin.providerBudget["stageBreakdown"]
    budget = ledger.snapshot()
    _, events = ledger._replay()
    if (
        origin.providerBudget["journalDigest"] not in {event["digest"] for event in events}
        or origin.providerBudget["createdAt"] != budget["createdAt"]
    ):
        raise ShadowIntegrityError("shadow_resume_original_ledger_missing")
    now = budget["stageBreakdown"]
    if (
        before != {"negative_control": 6, "scope_value": 16, "meaningful_change": 6, "user_copy": 0, "format_retry": 0}
        or any(now[k] != before[k] for k in ("negative_control", "scope_value", "format_retry"))
        or not 0 <= now["meaningful_change"] - before["meaningful_change"] <= 6
        or not 0 <= now["user_copy"] <= 6
        or not 28 <= budget["attempted"] <= 40
    ):
        raise ShadowIntegrityError("shadow_resume_budget_changed")
    source, recalled, pool = healthy_pool(mirror)
    universe, _ = build_candidate_universe(source)
    if (
        source.source_observation_set_id != source_freeze["sourceObservation"]
        or source.today_generation_id != source_freeze["sourceTodayGeneration"]
        or source.today_published_set_digest != source_freeze["todayTop20Digest"]
        or _source_identities(source, universe)["sourceCaptureDigests"] != source_freeze["sourceCaptureDigests"]
        or len(pool) != origin.healthyProfileCount
        or len(recalled) != origin.fullRecallCount
        or digest([r.model_dump(mode="json") for r in recalled]) != source_freeze["recallSetDigest"]
        or len(universe) != source_freeze["fullCandidateUniverseCount"]
        or digest(
            [
                {"path": r.relative_path, "sha256": r.file_digest, "profileRevision": r.collected.profile_revision}
                for r in pool
            ]
        )
        != source_freeze["healthyProfileSetDigest"]
    ):
        raise ShadowIntegrityError("shadow_resume_source_changed")
    safe = _SafeRoot(str(mirror))
    for item in source_freeze["profileInventory"]:
        if hashlib.sha256(safe.read_stable(item["path"], maximum_bytes=4 * 1024 * 1024)).hexdigest() != item["sha256"]:
            raise ShadowIntegrityError("shadow_resume_profile_changed")
    selected = {item["githubRepositoryId"]: item for item in cohort["items"]}
    original = {a.candidate.githubRepositoryId: a for a in origin.assessments}
    if set(selected) != set(original):
        raise ShadowIntegrityError("shadow_resume_cohort_changed")
    contexts = {}
    for row in pool:
        identifier = row.candidate.githubRepositoryId
        if identifier not in selected:
            continue
        item = selected[identifier]
        old = original[identifier]
        if (
            row.candidate != old.candidate
            or row.file_digest != item["profileFileSha256"]
            or row.collected.profile_revision != item["profileRevision"]
            or digest([e.model_dump(mode="json") for e in row.releases]) != item["releaseEvidenceDigest"]
        ):
            raise ShadowIntegrityError("shadow_resume_candidate_binding_changed")
        if item["meaningfulChangeCandidate"]:
            prior = signed_json(run_dir, f"stage-receipts/timeliness-{identifier}.json")
            if (
                prior.get("binding") != origin_binding
                or prior.get("key") != f"timeliness-{identifier}"
                or prior.get("state") != "completed"
                or prior.get("failure") != "wrong_assessment_evidence"
                or prior.get("value") != old.timeliness.model_dump(mode="json")
            ):
                raise ShadowIntegrityError("shadow_resume_unapproved_candidate")
            if list(row.releases) != old.timelinessEvidence:
                raise ShadowIntegrityError("shadow_resume_evidence_changed")
            contexts[identifier] = change_context(row.candidate, list(row.releases), route)
    if len(contexts) != 6:
        raise ShadowIntegrityError("shadow_resume_requires_six_frozen_changes")
    inputs = ResumeInputs(source_freeze, cohort, source, recalled, pool, origin, origin_binding, contexts, run_dir)
    # Preflight every reused receipt before the first new change dispatch. A late
    # corrupted deterministic receipt must not consume part of the remaining budget.
    for index in range(1, 7):
        receipt = inputs.legacy(f"negative-{index}")
        if receipt["state"] != "completed" or receipt.get("failure") is not None:
            raise ShadowIntegrityError("shadow_resume_control_receipt_invalid")
        SelectionGateResult.model_validate(receipt["value"], strict=True)
    for identifier, old in original.items():
        receipt = inputs.legacy(f"gate-{identifier}")
        if receipt["state"] == "started":
            if old.gate is not None or old.failureCode != "process_interrupted":
                raise ShadowIntegrityError("shadow_resume_gate_receipt_changed")
        elif (
            receipt["value"] != (old.gate.model_dump(mode="json") if old.gate else None)
            or receipt["attempts"] != old.gateAttempts
        ):
            raise ShadowIntegrityError("shadow_resume_gate_receipt_changed")
        if identifier not in contexts:
            receipt = inputs.legacy(f"timeliness-{identifier}")
            if (
                receipt["state"] != "completed"
                or receipt["failure"] is not None
                or SelectionTimeliness.model_validate(receipt["value"], strict=True) != old.timeliness
            ):
                raise ShadowIntegrityError("shadow_resume_timeliness_receipt_changed")
    return inputs
