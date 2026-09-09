"""Candidate-only isolation of optional Today material; never repairs published bytes."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace

from app.integrations.rardar.serving_completeness import _capability_audit
from app.integrations.rardar.serving_profiles import (
    ProfileBuildResult,
    _publishable_primary_text,
    _safe_source_text,
    _text_issue_codes,
)
from app.integrations.rardar.serving_schemas import OfficialProjectProfile


def isolate_materials(projects, result: ProfileBuildResult, generation_id: str) -> ProfileBuildResult:
    """Keep independently valid fields and reject identity/evidence corruption outright."""
    values = {}
    for project in projects:
        item = result.profiles[project.githubRepositoryId]
        profile, evidence = item.profile, item.evidence
        if any(
            value.githubRepositoryId != project.githubRepositoryId
            or value.repository != project.repository
            or value.generationId != generation_id
            for value in (profile, evidence)
        ) or str(profile.htmlUrl) != str(project.htmlUrl):
            raise ValueError("Today material identity mismatch")
        raw = (
            json.dumps(
                evidence.model_dump(mode="json", exclude={"digest"}),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        if hashlib.sha256(raw).hexdigest() != evidence.digest or profile.evidenceDigest != evidence.digest:
            raise ValueError("Today material evidence digest mismatch")
        allowed = set(evidence.evidenceIndex)
        data = profile.model_dump(mode="python")
        omitted = []

        def supported(text, refs=None, profile=profile, allowed=allowed, evidence=evidence):
            refs = refs if refs is not None else profile.claimEvidenceRefs.get(text, [])
            return bool(
                text
                and _publishable_primary_text(text)
                and refs
                and set(refs) <= allowed
                and any(ref != "repository" and evidence.evidenceIndex.get(ref, "").strip() for ref in refs)
                and not _text_issue_codes(text)
            )

        summary = profile.identitySummaryZh or profile.officialSummaryZh
        if not supported(summary) or not re.search(r"[\u3400-\u9fff]", summary or ""):
            summary = None
            omitted.append("summary_unavailable")
        data.update(officialSummaryZh=summary, identitySummaryZh=summary)
        position = profile.positioningZh
        if not supported(position, profile.positioningEvidenceRefs) or not profile.positioningIncludedRoles:
            data.update(
                positioningZh=None,
                positioningEvidenceRefs=[],
                positioningIncludedRoles=[],
                positioningExcludedClauses=[],
                positioningSourceMode="insufficient",
                officialPositioningZh=None,
                officialPositioningEvidenceRefs=[],
            )
            omitted.append("positioning_unavailable")
        else:
            data["positioningExcludedClauses"] = [
                c for c in profile.positioningExcludedClauses if set(c.evidenceRefs) <= allowed
            ]
        capabilities = [
            c
            for c in profile.capabilities
            if not any(_capability_audit([c], allowed).values()) and supported(c.detail, c.evidenceRefs)
        ]
        data.update(capabilities=capabilities, capabilityBulletsZh=[c.detail for c in capabilities])
        if len(capabilities) != len(profile.capabilities) or not capabilities:
            omitted.append("capabilities_unavailable_or_isolated")
        for field in ("keyDifferentiators", "rardarDifferentiators"):
            data[field] = [
                c
                for c in getattr(profile, field)
                if not any(_capability_audit([c], allowed).values()) and supported(c.detail, c.evidenceRefs)
            ]
        for text_field, ref_field in (
            ("coreValueZh", "coreValueEvidenceRefs"),
            ("rardarAssessmentZh", "rardarAssessmentEvidenceRefs"),
            ("officialTaglineZh", "officialTaglineEvidenceRefs"),
        ):
            if not supported(getattr(profile, text_field), getattr(profile, ref_field)):
                data[text_field], data[ref_field] = None, []
        data["officialHighlights"] = [
            h
            for h in profile.officialHighlights
            if supported(h.titleZh, h.evidenceRefs) and supported(h.detailZh, h.evidenceRefs)
        ]
        # Preserve author order, not a newly invented compact sequence.
        if data["officialHighlights"] != profile.officialHighlights:
            data["officialHighlights"] = []
        for field in ("productFormsZh", "supportedEnvironmentsZh", "primaryUseCasesZh", "deliveryFormsZh"):
            data[field] = [text for text in getattr(profile, field) if supported(text)]
        data["claimEvidenceRefs"] = {
            claim: refs for claim, refs in profile.claimEvidenceRefs.items() if refs and set(refs) <= allowed
        }
        for field, refs_field in (
            ("positioningZh", "positioningEvidenceRefs"),
            ("officialPositioningZh", "officialPositioningEvidenceRefs"),
            ("officialTaglineZh", "officialTaglineEvidenceRefs"),
            ("coreValueZh", "coreValueEvidenceRefs"),
            ("rardarAssessmentZh", "rardarAssessmentEvidenceRefs"),
        ):
            if data[field]:
                data["claimEvidenceRefs"][data[field]] = data[refs_field]
        for capability in [*data["capabilities"], *data["keyDifferentiators"], *data["rardarDifferentiators"]]:
            data["claimEvidenceRefs"][capability.detail] = capability.evidenceRefs
        for highlight in data["officialHighlights"]:
            data["claimEvidenceRefs"][highlight.titleZh] = highlight.evidenceRefs
            data["claimEvidenceRefs"][highlight.detailZh] = highlight.evidenceRefs
        data["startHere"] = [
            link
            for link in profile.startHere
            if set(link.evidenceRefs) <= allowed
            and str(link.htmlUrl).startswith(str(project.htmlUrl).rstrip("/") + "/")
            and any(evidence.pathRefs.get(ref) == link.path for ref in link.evidenceRefs)
        ]
        original = _safe_source_text(project.description or "", maximum=2000) or None
        state = (
            "complete"
            if summary and data["positioningZh"] and capabilities
            else ("partial" if summary or data["positioningZh"] or capabilities or original else "unavailable")
        )
        data.update(
            profileSchemaVersion="rardar-project-profile-v8",
            materialState=state,
            summarySource="chinese_profile" if summary else "original_description" if original else "unavailable",
            originalDescription=original,
            profileState="complete"
            if state == "complete"
            else "partial"
            if state == "partial"
            else "source_unavailable",
            qualityState="ready" if state == "complete" else "partial" if state == "partial" else "rejected",
            qualityIssues=list(dict.fromkeys([*profile.qualityIssues, *omitted]))[:24],
        )
        if not summary:
            data["translationState"] = "unavailable"
        if not any((summary, data["positioningZh"], capabilities)):
            data["officialNarrativeMode"] = "insufficient"
            data["sourceLabel"] = "受限概括"
        values[project.githubRepositoryId] = replace(item, profile=OfficialProjectProfile.model_validate(data))
    return replace(result, profiles=values)
