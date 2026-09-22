"""Reviewed fixed validation reasons; never persist arbitrary exception messages.

Codes are a diagnostic contract, independent of Pydantic error types. New rules
must be explicitly registered here; unknown messages remain unknown.
"""

import re
from contextlib import contextmanager

from pydantic import ValidationError


def _safe_attempt_evidence(value: object) -> dict:
    """Only immutable identifiers, never paths, source text or model inputs."""
    if not isinstance(value, dict):
        return {}
    result = {}
    patterns = {
        "generationId": r"[A-Za-z0-9_.:-]{1,160}",
        "evidenceDigest": r"[a-f0-9]{64}",
        "readmeBlobSha": r"[A-Fa-f0-9]{7,64}",
    }
    for key, pattern in patterns.items():
        item = value.get(key)
        if isinstance(item, str) and re.fullmatch(pattern, item):
            result[key] = item
    identifier = value.get("githubRepositoryId")
    if type(identifier) is int and identifier > 0:
        result["githubRepositoryId"] = identifier
    return result


def annotate_profile_validation(error: ValidationError, evidence: object) -> None:
    """Bind the actual construction attempt; never replace or reclassify it."""
    try:
        value = {
            "generationId": getattr(evidence, "generationId", None),
            "evidenceDigest": getattr(evidence, "digest", None),
            "readmeBlobSha": getattr(evidence, "readmeBlobSha", None),
            "githubRepositoryId": getattr(evidence, "githubRepositoryId", None),
        }
        error.rardar_attempt_evidence = _safe_attempt_evidence(value)
    except Exception:
        # Diagnostic enrichment must not mask the original validation failure.
        return


def profile_validation_attempt_evidence(error: Exception) -> dict:
    """Revalidate at persistence boundary; do not trust arbitrary attributes."""
    return _safe_attempt_evidence(getattr(error, "rardar_attempt_evidence", None))


@contextmanager
def profile_validation_context(evidence: object):
    """Keep the original model error, with a bounded link to its source revision."""
    try:
        yield
    except ValidationError as error:
        annotate_profile_validation(error, evidence)
        raise


PROFILE_VALIDATION_RULES = {
    "capability detail must not repeat its title": "profile_capability_detail_must_not_repeat_its_title",
    "capability evidence refs must be unique and bounded": "profile_capability_evidence_refs_must_be_unique_and_bounded",
    "capability short detail must explain its title": "profile_capability_short_detail_must_explain_its_title",
    "capability text must be complete": "profile_capability_text_must_be_complete",
    "Chinese capability title is too long": "profile_chinese_capability_title_is_too_long",
    "Chinese summary count cannot exceed total": "profile_chinese_summary_count_cannot_exceed_total",
    "excluded positioning clause must be complete": "profile_excluded_positioning_clause_must_be_complete",
    "excluded positioning evidence refs must be unique and bounded": "profile_excluded_positioning_evidence_refs_must_be_unique_and_bounded",
    "legacy profile requires a summary": "profile_legacy_profile_requires_a_summary",
    "legacy Serving requires a summary": "profile_legacy_serving_requires_a_summary",
    "legacy summary must project from identity summary": "profile_legacy_summary_must_project_from_identity_summary",
    "official highlight evidence refs must be unique and bounded": "profile_official_highlight_evidence_refs_must_be_unique_and_bounded",
    "official highlight text must be complete": "profile_official_highlight_text_must_be_complete",
    "profile core value requires evidence": "profile_profile_core_value_requires_evidence",
    "profile inventory must match summary": "profile_profile_inventory_must_match_summary",
    "profile narrative counts must be absent or equal total": "profile_profile_narrative_counts_must_be_absent_or_equal_total",
    "profile quality counts must be absent or equal total": "profile_profile_quality_counts_must_be_absent_or_equal_total",
    "profile quality issues must be unique and bounded": "profile_profile_quality_issues_must_be_unique_and_bounded",
    "profile state counts must equal total": "profile_profile_state_counts_must_equal_total",
    "profile v4 requires identity and quality state": "profile_profile_v4_requires_identity_and_quality_state",
    "profile v5 requires both narrative prompt versions": "profile_profile_v5_requires_both_narrative_prompt_versions",
    "profile v7 requires sourced capabilities": "profile_profile_v7_requires_sourced_capabilities",
    "project and evidence inventories must match": "profile_project_and_evidence_inventories_must_match",
    "project evidence digest is inconsistent": "profile_project_evidence_digest_is_inconsistent",
    "project generation is inconsistent": "profile_project_generation_is_inconsistent",
    "project identity is inconsistent": "profile_project_identity_is_inconsistent",
    "project material contract version is inconsistent": "profile_project_material_contract_version_is_inconsistent",
    "project profile projection is inconsistent": "profile_project_profile_projection_is_inconsistent",
    "ready profile requires evidence-backed semantic layers": "profile_ready_profile_requires_evidence_backed_semantic_layers",
    "rejected profile must not expose rejected semantic claims": "profile_rejected_profile_must_not_expose_rejected_semantic_claims",
    "rejected profile requires a stable quality reason": "profile_rejected_profile_requires_a_stable_quality_reason",
    "Serving v4 core value requires evidence": "profile_serving_v4_core_value_requires_evidence",
    "Serving v4 identity projection is inconsistent": "profile_serving_v4_identity_projection_is_inconsistent",
    "Serving v4 quality issues must be unique and bounded": "profile_serving_v4_quality_issues_must_be_unique_and_bounded",
    "Serving v4 quality summary is inconsistent": "profile_serving_v4_quality_summary_is_inconsistent",
    "Serving v4 ready project is incomplete": "profile_serving_v4_ready_project_is_incomplete",
    "Serving v4 rejected project exposes unsafe claims": "profile_serving_v4_rejected_project_exposes_unsafe_claims",
    "Serving v4 requires projected profile quality": "profile_serving_v4_requires_projected_profile_quality",
    "Serving v5 assessment compatibility projection is invalid": "profile_serving_v5_assessment_compatibility_projection_is_invalid",
    "Serving v5 assessment evidence projection is invalid": "profile_serving_v5_assessment_evidence_projection_is_invalid",
    "Serving v5 Chinese official highlights must preserve author text": "profile_serving_v5_chinese_official_highlights_must_preserve_author_text",
    "Serving v5 differentiator compatibility projection is invalid": "profile_serving_v5_differentiator_compatibility_projection_is_invalid",
    "Serving v5 identity compatibility projection is invalid": "profile_serving_v5_identity_compatibility_projection_is_invalid",
    "Serving v5 insufficient profile must expose safe facts only": "profile_serving_v5_insufficient_profile_must_expose_safe_facts_only",
    "Serving v5 narrative issues must be unique": "profile_serving_v5_narrative_issues_must_be_unique",
    "Serving v5 narrative source label is invalid": "profile_serving_v5_narrative_source_label_is_invalid",
    "Serving v5 narrative summary is inconsistent": "profile_serving_v5_narrative_summary_is_inconsistent",
    "Serving v5 official highlight order is invalid": "profile_serving_v5_official_highlight_order_is_invalid",
    "Serving v5 official narrative is incomplete": "profile_serving_v5_official_narrative_is_incomplete",
    "Serving v5 requires an official narrative mode": "profile_serving_v5_requires_an_official_narrative_mode",
    "Serving v6 insufficient positioning must expose no claims": "profile_serving_v6_insufficient_positioning_must_expose_no_claims",
    "Serving v6 legacy positioning evidence projection is inconsistent": "profile_serving_v6_legacy_positioning_evidence_projection_is_inconsistent",
    "Serving v6 legacy positioning text projection is inconsistent": "profile_serving_v6_legacy_positioning_text_projection_is_inconsistent",
    "Serving v6 positioning evidence refs must be unique": "profile_serving_v6_positioning_evidence_refs_must_be_unique",
    "Serving v6 positioning must not repeat the identity summary": "profile_serving_v6_positioning_must_not_repeat_the_identity_summary",
    "Serving v6 positioning requires a mechanism or primary outcome": "profile_serving_v6_positioning_requires_a_mechanism_or_primary_outcome",
    "Serving v6 positioning requires text, evidence, and semantic roles": "profile_serving_v6_positioning_requires_text_evidence_and_semantic_roles",
    "Serving v6 positioning roles must be unique": "profile_serving_v6_positioning_roles_must_be_unique",
    "Serving v6 requires a field-level positioning source mode": "profile_serving_v6_requires_a_field_level_positioning_source_mode",
    "Serving v7 exact Top 20 requires sourced capabilities": "profile_serving_v7_exact_top_20_requires_sourced_capabilities",
    "Serving v8 assessment compatibility projection is inconsistent": "profile_serving_v8_assessment_compatibility_projection_is_inconsistent",
    "Serving v8 capabilities must project to legacy details": "profile_serving_v8_capabilities_must_project_to_legacy_details",
    "Serving v8 Chinese summary requires a saved claim reference": "profile_serving_v8_chinese_summary_requires_a_saved_claim_reference",
    "Serving v8 Chinese summary requires Chinese content": "profile_serving_v8_chinese_summary_requires_chinese_content",
    "Serving v8 differentiator compatibility projection is inconsistent": "profile_serving_v8_differentiator_compatibility_projection_is_inconsistent",
    "Serving v8 identity projection is inconsistent": "profile_serving_v8_identity_projection_is_inconsistent",
    "Serving v8 material state is inconsistent": "profile_serving_v8_material_state_is_inconsistent",
    "Serving v8 narrative issues must be unique": "profile_serving_v8_narrative_issues_must_be_unique",
    "Serving v8 narrative source attribution is inconsistent": "profile_serving_v8_narrative_source_attribution_is_inconsistent",
    "Serving v8 narrative summary is inconsistent": "profile_serving_v8_narrative_summary_is_inconsistent",
    "Serving v8 official Chinese highlights must preserve source text": "profile_serving_v8_official_chinese_highlights_must_preserve_source_text",
    "Serving v8 official highlight order is invalid": "profile_serving_v8_official_highlight_order_is_invalid",
    "Serving v8 original or unavailable summary must not masquerade as Chinese": "profile_serving_v8_original_or_unavailable_summary_must_not_masquerade_as_chinese",
    "Serving v8 original summary requires original description": "profile_serving_v8_original_summary_requires_original_description",
    "Serving v8 present capabilities require a source mode": "profile_serving_v8_present_capabilities_require_a_source_mode",
    "Serving v8 present claims require evidence and absent claims cannot have references": "profile_serving_v8_present_claims_require_evidence_and_absent_claims_cannot_have_references",
    "Serving v8 profile state summary is inconsistent": "profile_serving_v8_profile_state_summary_is_inconsistent",
    "Serving v8 profile summary is inconsistent": "profile_serving_v8_profile_summary_is_inconsistent",
    "Serving v8 quality issues must be unique and bounded": "profile_serving_v8_quality_issues_must_be_unique_and_bounded",
    "Serving v8 quality summary is inconsistent": "profile_serving_v8_quality_summary_is_inconsistent",
    "Serving v8 requires explicit material states": "profile_serving_v8_requires_explicit_material_states",
    "Serving v8 summary source contradicts available description": "profile_serving_v8_summary_source_contradicts_available_description",
    "Serving v8 tagline identity projection is inconsistent": "profile_serving_v8_tagline_identity_projection_is_inconsistent",
    "structured capabilities must project to legacy capability details": "profile_structured_capabilities_must_project_to_legacy_capability_details",
}
