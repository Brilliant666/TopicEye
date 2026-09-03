"""Bounded cohort execution; accepted Selection judgments remain unchanged.

Stage receipts are durable run progress, not a second model cache. A started
receipt without a result is terminal UNCERTAIN after a crash: no silent replay.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.integrations.rardar.selection import (
    SelectionBuildError,
    _contract_versions,
    _copy,
    _negative_control_candidate,
    _pack,
    _primary_reason,
    _run_gate,
    _timeliness,
    _Usage,
    _value_evidence,
    negative_control_cases,
    semantic_decision,
)
from app.integrations.rardar.selection_schemas import (
    SelectionAssessment,
    SelectionCopyResult,
    SelectionEvidenceAlias,
    SelectionGateResult,
    SelectionProjectContext,
    SelectionTimeliness,
)
from app.integrations.rardar.selection_serving import _card
from app.integrations.rardar.shadow_cohort import COHORT_VERSION, ShadowIntegrityError, freeze, healthy_pool
from app.integrations.rardar.shadow_schemas import ShadowReviewArtifact
from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    atomic,
    budget_stage,
    digest,
    file_lock,
    plain,
)
from app.services.rardar_llm_control import call_rardar_prompt_json


def neutral_timeliness() -> SelectionTimeliness:
    return SelectionTimeliness(
        verdict="none",
        confidence="high",
        reasonCodes=["no_strong_why_now"],
        evidenceIds=[],
        meaningfulChange=None,
        strongSignals=[],
        weakSignals=[],
    )


class StageReceipts:
    def __init__(self, root: Path, binding: str):
        self.root = root / "stage-receipts"
        plain(self.root, missing=True)
        self.root.mkdir(exist_ok=True)
        self.binding = binding

    async def run(self, key: str, operation, model: type[BaseModel]):
        path = self.root / f"{key}.json"
        plain(path, missing=True)
        if path.exists():
            receipt = json.loads(path.read_bytes())
            if receipt.get("binding") != self.binding or receipt.get("digest") != digest(
                {k: v for k, v in receipt.items() if k != "digest"}
            ):
                raise ShadowIntegrityError("shadow_receipt_invalid")
            if receipt["state"] == "started":
                return None, 0, "process_interrupted"
            value = model.model_validate_json(json.dumps(receipt["value"]), strict=True) if receipt["value"] else None
            return value, receipt["attempts"], receipt["failure"]
        receipt = {"binding": self.binding, "state": "started", "key": key}
        receipt["digest"] = digest(receipt)
        atomic(path, receipt)
        result = await operation()
        value, attempts = result[:2]
        failure = result[2] if len(result) == 3 else (None if value is not None else "copy_invalid")
        receipt = {
            "binding": self.binding,
            "state": "completed",
            "key": key,
            "value": value.model_dump(mode="json") if value is not None else None,
            "attempts": attempts,
            "failure": failure,
        }
        receipt["digest"] = digest(receipt)
        atomic(path, receipt)
        return value, attempts, failure


async def _build_shadow_review(
    mirror: Path, run_dir: Path, ledger: ProviderBudgetLedger, *, route_identity: str, caller=call_rardar_prompt_json
) -> ShadowReviewArtifact:
    # A second script cannot execute the same run concurrently, even between calls.
    with file_lock(run_dir / "shadow-run.lock", blocking=False):
        source_freeze, cohort = freeze(mirror, run_dir)
        source, _recalled, pool = healthy_pool(mirror)
        pool_by_id = {row.candidate.githubRepositoryId: row for row in pool}
        selected = [pool_by_id[row["githubRepositoryId"]] for row in cohort["items"]]
        binding = digest(
            {
                "source": source_freeze["digest"],
                "cohort": cohort["digest"],
                "route": route_identity,
                "policy": _contract_versions(),
                "runId": ledger.run_id,
            }
        )
        run_path = run_dir / "shadow-run-binding.json"
        if run_path.exists():
            if json.loads(run_path.read_bytes()) != {"binding": binding}:
                raise ShadowIntegrityError("shadow_run_binding_changed")
        else:
            atomic(run_path, {"binding": binding})
        completed_path = run_dir / "shadow-review-artifact.json"
        if completed_path.exists():
            artifact = ShadowReviewArtifact.model_validate_json(completed_path.read_bytes(), strict=True)
            if artifact.providerBudget != ledger.snapshot() or artifact.cohortManifestDigest != cohort["digest"]:
                raise ShadowIntegrityError("shadow_completed_run_changed")
            return artifact  # Same run/artifact: zero provider calls, no new ledger.
        receipts = StageReceipts(run_dir, binding)
        usage = _Usage()
        controls: list[dict[str, Any]] = []
        for index, (name, text) in enumerate(negative_control_cases(), 1):
            candidate = _negative_control_candidate(index, text)
            evidence = [
                SelectionEvidenceAlias(
                    evidenceId="E01",
                    sourceType="description",
                    sourcePath="control.description",
                    sourceRevision=f"negative-control-v1-{index}",
                    excerpt=text,
                    githubRepositoryId=candidate.githubRepositoryId,
                )
            ]
            with budget_stage("negative_control"):
                gate, attempts, failure = await receipts.run(
                    f"negative-{index}",
                    lambda c=candidate, e=evidence: _run_gate(c, e, usage, caller, format_retry=False),
                    SelectionGateResult,
                )
            decision = semantic_decision(gate, neutral_timeliness(), failure)
            passed = (
                gate is not None
                and failure is None
                and (decision == "REJECT" if name == "out_of_product_scope" else decision in {"REJECT", "UNCERTAIN"})
            )
            controls.append(
                {"name": name, "decision": decision, "passed": passed, "attempts": attempts, "failure": failure}
            )
        violations = [row["name"] for row in controls if not row["passed"]]
        if violations:
            atomic(run_dir / "negative-control-results.json", {"controls": controls, "violations": violations})
            raise ShadowIntegrityError("shadow_negative_controls_failed")

        # All value judgments precede change assessments; no temporal facts enter value payloads.
        gates: dict[int, tuple[Any, int, Any]] = {}
        value_evidence = {}
        for row in selected:
            identifier = row.candidate.githubRepositoryId
            evidence = _value_evidence(row.candidate, row.collected)
            value_evidence[identifier] = evidence
            with budget_stage("scope_value"):
                gates[identifier] = await receipts.run(
                    f"gate-{identifier}",
                    lambda r=row, e=evidence: _run_gate(r.candidate, e, usage, caller),
                    SelectionGateResult,
                )
        assessments = []
        change_ids = {row["githubRepositoryId"] for row in cohort["items"] if row["meaningfulChangeCandidate"]}
        for row in selected:
            candidate = row.candidate
            identifier = candidate.githubRepositoryId
            evidence = list(row.releases) if identifier in change_ids else []
            with budget_stage("meaningful_change"):
                timely, change_attempts, change_failure = await receipts.run(
                    f"timeliness-{identifier}",
                    lambda c=candidate, e=evidence: _timeliness(c, e, usage, caller),
                    SelectionTimeliness,
                )
            gate, gate_attempts, failure = gates[identifier]
            failure = failure or change_failure
            timely = timely or neutral_timeliness()
            decision = semantic_decision(gate, timely, failure)
            primary, supporting = _primary_reason(gate)
            if decision in {"SELECT_NOW", "WORTHWHILE_NOT_NOW"} and primary is None:
                decision, failure = "UNCERTAIN", failure or "weak_evidence"
            assessments.append(
                SelectionAssessment(
                    candidate=candidate,
                    selectionEvidenceDigest=digest(
                        {
                            "binding": binding,
                            "id": identifier,
                            "value": [item.model_dump(mode="json") for item in value_evidence[identifier]],
                            "timeliness": [item.model_dump(mode="json") for item in evidence],
                            "profileRevision": row.collected.profile_revision,
                        }
                    ),
                    peerContextDigest="0" * 64,
                    valueEvidence=value_evidence[identifier],
                    timelinessEvidence=evidence,
                    peerEvidence=[],
                    gate=gate,
                    timeliness=timely,
                    semanticDecision=decision,
                    primaryReason=primary if decision in {"SELECT_NOW", "WORTHWHILE_NOT_NOW"} else None,
                    supportingReasons=supporting if decision in {"SELECT_NOW", "WORTHWHILE_NOT_NOW"} else [],
                    publicationDisposition="not_eligible",
                    rejectReason=(
                        "out_of_product_scope" if gate and gate.scopeStatus == "out_of_scope" else "no_clear_value"
                    )
                    if decision == "REJECT"
                    else None,
                    failureCode=failure,
                    gateAttempts=gate_attempts,
                    meaningfulChangeAttempts=change_attempts,
                    copyAttempts=0,
                    category=row.category,
                    categorySource="research_derived",
                    productFormsZh=row.collected.profile.productFormsZh[:3],
                )
            )
            atomic(
                run_dir / f"assessment-{identifier}.json",
                {
                    "binding": binding,
                    "assessment": assessments[-1].model_dump(mode="json"),
                    "digest": digest({"binding": binding, "assessment": assessments[-1].model_dump(mode="json")}),
                },
            )
        peer_digest = digest(
            [
                {"id": a.candidate.githubRepositoryId, "decision": a.semanticDecision, "primary": a.primaryReason}
                for a in assessments
            ]
        )
        packed = _pack([a.model_copy(update={"peerContextDigest": peer_digest}) for a in assessments])
        preview_ids = {
            a.candidate.githubRepositoryId
            for a in sorted(packed, key=lambda a: a.displayOrder or 999)
            if a.publicationDisposition == "publish" and (a.displayOrder or 999) <= 6
        }
        finished = []
        for assessment in packed:
            identifier = assessment.candidate.githubRepositoryId
            if assessment.publicationDisposition == "publish" and identifier not in preview_ids:
                assessment = assessment.model_copy(
                    update={"publicationDisposition": "suppress_capacity", "displayOrder": None}
                )
            if identifier in preview_ids:
                with budget_stage("user_copy"):
                    copy, attempts, failure = await receipts.run(
                        f"copy-{identifier}",
                        lambda a=assessment, i=identifier: _copy(a, pool_by_id[i].collected, usage, caller),
                        SelectionCopyResult,
                    )
                assessment = assessment.model_copy(update={"copyResult": copy, "copyAttempts": attempts})
                if copy is None:
                    # Membership was frozen before copy: hide missing text, never replace the project.
                    assessment = assessment.model_copy(update={"failureCode": failure})
            finished.append(SelectionAssessment.model_validate(assessment.model_dump(mode="python"), strict=True))
        failures = Counter(a.failureCode for a in finished if a.failureCode)
        semantic_failures = Counter(a.failureCode for a in assessments if a.failureCode)
        systemic = any(
            count >= 4
            for code, count in semantic_failures.items()
            if code
            in {"provider_timeout", "provider_transport_failure", "provider_protocol_rejected", "process_interrupted"}
        )
        evidence_violations = sum(
            a.failureCode in {"invalid_evidence_alias", "wrong_assessment_evidence"} for a in finished
        )
        ready = not systemic and evidence_violations == 0
        if not ready:
            finished = [
                a.model_copy(
                    update={"publicationDisposition": "not_eligible", "displayOrder": None, "copyResult": None}
                )
                for a in finished
            ]
        now = datetime.now(UTC)
        generation = (
            f"shadow-{digest({'binding': binding, 'results': [a.model_dump(mode='json') for a in finished]})[:32]}"
        )
        cards, contexts = [], []
        for assessment in sorted(finished, key=lambda a: a.displayOrder or 999):
            if assessment.publicationDisposition != "publish":
                continue
            collected = pool_by_id[assessment.candidate.githubRepositoryId].collected
            card = _card(assessment, collected.profile)
            if assessment.copyResult is None:
                card = card.model_copy(update={"whyWorthSeeingZh": None, "reusableAssets": [], "bestFit": []})
            cards.append(card)
            contexts.append(
                SelectionProjectContext(
                    schemaVersion=1,
                    selectionGenerationId=generation,
                    sourceObservationSetId=source.source_observation_set_id,
                    generatedAt=now,
                    card=card,
                    selectionEvidenceDigest=assessment.selectionEvidenceDigest,
                    timelinessReasonCodes=assessment.timeliness.reasonCodes,
                    evidence=assessment.valueEvidence + assessment.timelinessEvidence + assessment.peerEvidence,
                    canonicalProfile=collected.profile.model_dump(mode="json"),
                    canonicalEvidence=collected.evidence.model_dump(mode="json"),
                )
            )
        payload = {
            "schemaVersion": 1,
            "mode": "local_shadow_review",
            "productionEligible": False,
            "state": "degraded",
            "shadowReviewState": ("ready" if cards else "empty") if ready else "incomplete",
            "reviewable": ready,
            "shadowReviewGeneration": generation,
            "sourceFreezeDigest": source_freeze["digest"],
            "sourceObservation": source.source_observation_set_id,
            "sourceTodayGeneration": source.today_generation_id,
            "latestCaptureAt": source.latest_capture_at.replace("+00:00", "Z"),
            "fullCandidateUniverseCount": source_freeze["fullCandidateUniverseCount"],
            "fullRecallCount": source_freeze["fullRecallCount"],
            "healthyProfileCount": len(pool),
            "unresolvedProfileCount": len(source_freeze["unresolvedProfiles"]),
            "cohortVersion": COHORT_VERSION,
            "cohortManifestDigest": cohort["digest"],
            "cohortSize": 16,
            "cohortProfileReady": 16,
            "cohortAssessed": len(finished),
            "cohortStructuredSuccess": sum(a.gate is not None for a in finished),
            "cohortUncertainFallbacks": sum(a.gate is None for a in finished),
            "negativeControlCount": 6,
            "negativeControlViolations": violations,
            "negativeControls": controls,
            "providerBudget": ledger.snapshot(),
            "semanticDecisionCounts": {
                key: sum(a.semanticDecision == key for a in finished)
                for key in ("SELECT_NOW", "WORTHWHILE_NOT_NOW", "REJECT", "UNCERTAIN")
            },
            "previewCount": len(cards),
            "previewItems": [c.model_dump(mode="json") for c in cards],
            "nonPreviewItems": [
                a.candidate.githubRepositoryId for a in finished if a.publicationDisposition != "publish"
            ],
            "unresolvedProfiles": source_freeze["unresolvedProfiles"],
            "assessments": [a.model_dump(mode="json") for a in finished],
            "contexts": [c.model_dump(mode="json") for c in contexts],
            "generatedAt": now.isoformat().replace("+00:00", "Z"),
            "policyVersions": _contract_versions(),
            "audit": {
                "momentumLeakage": 0,
                "evidenceViolations": evidence_violations,
                "systemicProviderFailure": systemic,
                "profileModelCalls": 0,
                "githubRequests": 0,
                "fullCurrentChanged": False,
                "failureHistogram": dict(failures),
            },
        }
        payload["digest"] = digest(payload)
        artifact = ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)
        atomic(completed_path, artifact.model_dump(mode="json"))
        return artifact


async def build_shadow_review(
    mirror: Path, run_dir: Path, ledger: ProviderBudgetLedger, *, route_identity: str, caller=call_rardar_prompt_json
) -> ShadowReviewArtifact:
    try:
        return await _build_shadow_review(mirror, run_dir, ledger, route_identity=route_identity, caller=caller)
    except (ProviderBudgetError, SelectionBuildError) as exc:
        if "exhausted" not in exc.code:
            raise
        # Preserve completed semantics; unstarted projects are not fabricated as negatives.
        with file_lock(run_dir / "shadow-run.lock", blocking=False):
            source_freeze, cohort = freeze(mirror, run_dir)
            source, _recalled, pool = healthy_pool(mirror)
            binding = json.loads((run_dir / "shadow-run-binding.json").read_bytes())["binding"]
            assessments = []
            for row in cohort["items"]:
                path = run_dir / f"assessment-{row['githubRepositoryId']}.json"
                plain(path, missing=True)
                if not path.exists():
                    continue
                receipt = json.loads(path.read_bytes())
                if receipt["binding"] != binding or receipt["digest"] != digest(
                    {k: v for k, v in receipt.items() if k != "digest"}
                ):
                    raise ShadowIntegrityError("shadow_receipt_invalid") from None
                assessments.append(
                    SelectionAssessment.model_validate_json(json.dumps(receipt["assessment"]), strict=True)
                )
            controls = []
            for index, (name, _text) in enumerate(negative_control_cases(), 1):
                path = run_dir / "stage-receipts" / f"negative-{index}.json"
                plain(path, missing=True)
                if not path.exists():
                    continue
                receipt = json.loads(path.read_bytes())
                if receipt.get("state") != "completed":
                    continue
                gate = (
                    SelectionGateResult.model_validate_json(json.dumps(receipt["value"]), strict=True)
                    if receipt["value"]
                    else None
                )
                decision = semantic_decision(gate, neutral_timeliness(), receipt["failure"])
                passed = (
                    gate is not None
                    and receipt["failure"] is None
                    and (
                        decision == "REJECT" if name == "out_of_product_scope" else decision in {"REJECT", "UNCERTAIN"}
                    )
                )
                controls.append({"name": name, "decision": decision, "passed": passed})
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            payload = {
                "schemaVersion": 1,
                "mode": "local_shadow_review",
                "productionEligible": False,
                "state": "degraded",
                "shadowReviewState": "incomplete",
                "reviewable": False,
                "shadowReviewGeneration": f"shadow-{digest({'binding': binding, 'stop': exc.code})[:32]}",
                "sourceFreezeDigest": source_freeze["digest"],
                "sourceObservation": source.source_observation_set_id,
                "sourceTodayGeneration": source.today_generation_id,
                "latestCaptureAt": source.latest_capture_at.replace("+00:00", "Z"),
                "fullCandidateUniverseCount": source_freeze["fullCandidateUniverseCount"],
                "fullRecallCount": source_freeze["fullRecallCount"],
                "healthyProfileCount": len(pool),
                "unresolvedProfileCount": len(source_freeze["unresolvedProfiles"]),
                "cohortVersion": COHORT_VERSION,
                "cohortManifestDigest": cohort["digest"],
                "cohortSize": 16,
                "cohortProfileReady": 16,
                "cohortAssessed": len(assessments),
                "cohortStructuredSuccess": sum(a.gate is not None for a in assessments),
                "cohortUncertainFallbacks": sum(a.gate is None for a in assessments),
                "negativeControlCount": len(controls),
                "negativeControlViolations": [c["name"] for c in controls if not c["passed"]],
                "negativeControls": controls,
                "providerBudget": ledger.snapshot(),
                "semanticDecisionCounts": {
                    key: sum(a.semanticDecision == key for a in assessments)
                    for key in ("SELECT_NOW", "WORTHWHILE_NOT_NOW", "REJECT", "UNCERTAIN")
                },
                "previewCount": 0,
                "previewItems": [],
                "nonPreviewItems": [a.candidate.githubRepositoryId for a in assessments],
                "unresolvedProfiles": source_freeze["unresolvedProfiles"],
                "assessments": [a.model_dump(mode="json") for a in assessments],
                "contexts": [],
                "generatedAt": now,
                "policyVersions": _contract_versions(),
                "audit": {
                    "momentumLeakage": 0,
                    "evidenceViolations": 0,
                    "systemicProviderFailure": False,
                    "budgetExhausted": True,
                    "profileModelCalls": 0,
                    "githubRequests": 0,
                    "fullCurrentChanged": False,
                    "failureHistogram": {exc.code: 1},
                },
            }
            payload["digest"] = digest(payload)
            artifact = ShadowReviewArtifact.model_validate_json(json.dumps(payload), strict=True)
            atomic(run_dir / "shadow-review-artifact.json", artifact.model_dump(mode="json"))
            return artifact
