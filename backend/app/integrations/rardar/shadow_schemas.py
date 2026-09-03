"""Local cohort review is explicitly not a production Selection publication."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.integrations.rardar.selection_schemas import (
    SelectionAssessment,
    SelectionProjectContext,
    SelectionServingCard,
    StrictSelectionModel,
)
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ProjectEvidenceProjection
from app.services.llm.provider_budget import digest


class ShadowReviewArtifact(StrictSelectionModel):
    schemaVersion: Literal[1]
    mode: Literal["local_shadow_review"]
    productionEligible: Literal[False]
    state: Literal["degraded"]
    shadowReviewState: Literal["ready", "empty", "incomplete"]
    reviewable: bool
    shadowReviewGeneration: str = Field(pattern=r"^shadow-[a-f0-9]{32}$")
    sourceFreezeDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    sourceObservation: str
    sourceTodayGeneration: str
    latestCaptureAt: AwareDatetime
    fullCandidateUniverseCount: int = Field(ge=16, le=500)
    fullRecallCount: int = Field(ge=16, le=60)
    healthyProfileCount: int = Field(ge=16, le=60)
    unresolvedProfileCount: int = Field(ge=0, le=60)
    cohortVersion: Literal["shadow-review-cohort-v1"]
    cohortManifestDigest: str = Field(pattern=r"^[a-f0-9]{64}$")
    cohortSize: Literal[16]
    cohortProfileReady: Literal[16]
    cohortAssessed: int = Field(ge=0, le=16)
    cohortStructuredSuccess: int = Field(ge=0, le=16)
    cohortUncertainFallbacks: int = Field(ge=0, le=16)
    negativeControlCount: int = Field(ge=0, le=6)
    negativeControlViolations: list[str] = Field(max_length=6)
    negativeControls: list[dict[str, Any]] = Field(max_length=6)
    providerBudget: dict[str, Any]
    semanticDecisionCounts: dict[str, int]
    previewCount: int = Field(ge=0, le=6)
    previewItems: list[SelectionServingCard] = Field(max_length=6)
    nonPreviewItems: list[int] = Field(max_length=16)
    unresolvedProfiles: list[dict[str, Any]] = Field(max_length=60)
    assessments: list[SelectionAssessment] = Field(max_length=16)
    contexts: list[SelectionProjectContext] = Field(max_length=6)
    generatedAt: AwareDatetime
    policyVersions: dict[str, str]
    audit: dict[str, Any]
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def audit_contract(self):
        if self.digest != digest(self.model_dump(mode="json", exclude={"digest"})):
            raise ValueError("shadow artifact digest mismatch")
        names = [row.get("name") for row in self.negativeControls]
        if len(names) != self.negativeControlCount or len(names) != len(set(names)):
            raise ValueError("shadow negative control inventory mismatch")
        expected_controls = {
            "out_of_product_scope",
            "identity_or_source_invalid",
            "marketing_only",
            "popularity_only",
            "weak_evidence",
            "not_reusable_or_actionable",
        }
        if not set(names) <= expected_controls:
            raise ValueError("shadow negative control names mismatch")
        violations = [row["name"] for row in self.negativeControls if not row.get("passed")]
        if self.negativeControlViolations != violations or any(
            row.get("passed")
            and (
                row.get("decision") != "REJECT"
                if row["name"] == "out_of_product_scope"
                else row.get("decision") not in {"REJECT", "UNCERTAIN"}
            )
            for row in self.negativeControls
        ):
            raise ValueError("shadow negative controls mismatch")
        budget = self.providerBudget
        if any(
            type(budget.get(key)) is not int or budget[key] < 0
            for key in ("limit", "reserved", "attempted", "completed", "succeeded", "failed", "cacheHits", "remaining")
        ):
            raise ValueError("shadow budget counters invalid")
        if (
            budget.get("digest") != digest({key: value for key, value in budget.items() if key != "digest"})
            or budget.get("limit") != 40
            or not 0 <= budget.get("attempted", -1) <= budget.get("reserved", -1) <= 40
            or budget.get("remaining") != 40 - budget["reserved"]
        ):
            raise ValueError("shadow budget invalid")
        ids = [item.candidate.githubRepositoryId for item in self.assessments]
        if len(ids) != len(set(ids)) or len(ids) != self.cohortAssessed:
            raise ValueError("shadow cohort terminal count mismatch")
        if self.cohortStructuredSuccess + self.cohortUncertainFallbacks != self.cohortAssessed:
            raise ValueError("shadow structured count mismatch")
        if (
            self.healthyProfileCount + self.unresolvedProfileCount != self.fullRecallCount
            or len(self.unresolvedProfiles) != self.unresolvedProfileCount
        ):
            raise ValueError("shadow full coverage mismatch")
        counts = Counter(item.semanticDecision for item in self.assessments)
        if any(
            self.semanticDecisionCounts.get(key) != counts[key]
            for key in ("SELECT_NOW", "WORTHWHILE_NOT_NOW", "REJECT", "UNCERTAIN")
        ):
            raise ValueError("shadow decision counts mismatch")
        preview_ids = [item.githubRepositoryId for item in self.previewItems]
        published = [item for item in self.assessments if item.publicationDisposition == "publish"]
        if (
            self.previewCount != len(preview_ids)
            or len(preview_ids) != len(set(preview_ids))
            or set(preview_ids) != {item.candidate.githubRepositoryId for item in published}
            or set(self.nonPreviewItems) != set(ids) - set(preview_ids)
        ):
            raise ValueError("shadow preview inventory mismatch")
        if {item.card.githubRepositoryId for item in self.contexts} != set(preview_ids):
            raise ValueError("shadow detail inventory mismatch")
        by_id = {item.candidate.githubRepositoryId: item for item in published}
        cards = {item.githubRepositoryId: item for item in self.previewItems}
        for context in self.contexts:
            assessment = by_id[context.card.githubRepositoryId]
            import json

            profile = OfficialProjectProfile.model_validate_json(json.dumps(context.canonicalProfile), strict=True)
            evidence = ProjectEvidenceProjection.model_validate_json(json.dumps(context.canonicalEvidence), strict=True)
            if (
                profile.githubRepositoryId != context.card.githubRepositoryId
                or evidence.githubRepositoryId != profile.githubRepositoryId
                or profile.repository != context.card.repository
                or profile.evidenceDigest != evidence.digest
            ):
                raise ValueError("shadow canonical profile mismatch")
            if (
                context.card != cards[context.card.githubRepositoryId]
                or context.selectionGenerationId != self.shadowReviewGeneration
                or context.sourceObservationSetId != self.sourceObservation
                or context.selectionEvidenceDigest != assessment.selectionEvidenceDigest
                or context.evidence
                != assessment.valueEvidence + assessment.timelinessEvidence + assessment.peerEvidence
                or assessment.semanticDecision != "SELECT_NOW"
            ):
                raise ValueError("shadow detail evidence mismatch")
        ready = (
            self.cohortAssessed == 16
            and self.negativeControlCount == 6
            and not self.negativeControlViolations
            and self.audit.get("momentumLeakage") == 0
            and self.audit.get("evidenceViolations") == 0
            and self.audit.get("systemicProviderFailure") is False
            and not self.audit.get("budgetExhausted", False)
        )
        expected = ("ready" if preview_ids else "empty") if ready else "incomplete"
        if self.shadowReviewState != expected or self.reviewable != ready:
            raise ValueError("shadow reviewability mismatch")
        if not ready and preview_ids:
            raise ValueError("incomplete shadow cannot expose preview")
        return self
