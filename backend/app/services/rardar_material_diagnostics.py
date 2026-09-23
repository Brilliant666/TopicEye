"""Bounded metadata for material failures; never retain exception messages or bodies."""

from __future__ import annotations

import re
from typing import get_args

import httpx
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorType

from app.integrations.rardar import serving_schemas
from app.integrations.rardar.profile_validation_rules import (
    PROFILE_VALIDATION_RULES,
    profile_validation_attempt_evidence,
)
from app.integrations.rardar.serving_profiles import (
    _FIXED_TRANSLATION_RULES,
    _GENERATION_ERROR_CLASSES,
    _GENERATION_ERROR_CODES,
    _GENERATION_VALIDATION_STAGES,
    _GENERATION_VALIDATION_TYPES,
    _OFFICIAL_NARRATIVE_PROMPT_VERSION,
    _OFFICIAL_POSITIONING_PROMPT_VERSION,
    _RARDAR_ASSESSMENT_PROMPT_VERSION,
    OfficialNarrativeTranslation,
    OfficialPositioningTranslation,
    ProfileTranslation,
)

_FIELDS = frozenset(
    field
    for model in vars(serving_schemas).values()
    if isinstance(model, type) and issubclass(model, BaseModel)
    for field in model.model_fields
)
_ERROR_TYPES = frozenset(get_args(ErrorType))
_MODELS = frozenset(
    model.__name__
    for model in vars(serving_schemas).values()
    if isinstance(model, type) and issubclass(model, BaseModel)
)
_CUSTOM_RULES = {code: message for message, code in PROFILE_VALIDATION_RULES.items()}
_SAMPLE_LIMIT = 4
_GENERATION_MODELS = {
    model.__name__: model
    for model in (ProfileTranslation, OfficialNarrativeTranslation, OfficialPositioningTranslation)
}
_GENERATION_CODES = frozenset(
    f"{stage}_{suffix}"
    for stage in ("translation", "positioning")
    for suffix in (
        "budget",
        "empty",
        "evidence_mismatch",
        "invalid_json",
        "provider_error",
        "rate_limited",
        "schema_invalid",
        "timeout",
    )
)
_GENERATION_PROMPT_VERSIONS = frozenset(
    {_RARDAR_ASSESSMENT_PROMPT_VERSION, _OFFICIAL_NARRATIVE_PROMPT_VERSION, _OFFICIAL_POSITIONING_PROMPT_VERSION}
)


def _generation_field_names() -> frozenset[str]:
    names: set[str] = set()

    def collect(node: object) -> None:
        if isinstance(node, dict):
            names.update(node.get("properties", {}))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    for model in _GENERATION_MODELS.values():
        collect(model.model_json_schema())
    return frozenset(names)


_GENERATION_FIELDS = _generation_field_names()


def _safe_generation_field_path(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 160 or not value.startswith("$"):
        return None
    position = 1
    while position < len(value):
        match = re.match(r"\.([A-Za-z][A-Za-z0-9_]*|<extra-field>)|\[(\d{1,5})\]", value[position:])
        if match is None:
            return None
        field = match.group(1)
        if field is not None and field != "<extra-field>" and field not in _GENERATION_FIELDS:
            return None
        position += match.end()
    return value


def _safe_generation_failure(failure: object) -> dict | None:
    stage = getattr(failure, "stage", None)
    code = getattr(failure, "code", None)
    resolved = getattr(failure, "resolved", None)
    if stage not in {"translation", "positioning"} or type(resolved) is not bool:
        return None
    result = {
        "stage": stage,
        "code": code if isinstance(code, str) and code in _GENERATION_CODES else "unknown",
        "resolved": resolved,
        "detail": None,
    }
    detail = getattr(failure, "diagnostic", None)
    if not isinstance(detail, dict):
        return result
    model_class = detail.get("modelClass")
    prompt_version = detail.get("promptVersion")
    digest = detail.get("inputDigest")
    if model_class not in _GENERATION_MODELS or prompt_version not in _GENERATION_PROMPT_VERSIONS:
        return result
    safe = {
        "modelClass": model_class,
        "promptVersion": prompt_version,
        "inputDigest": digest if isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) else None,
        "errorCode": detail.get("errorCode") if detail.get("errorCode") in _GENERATION_ERROR_CODES else None,
        "classification": (
            detail.get("classification") if detail.get("classification") in _GENERATION_ERROR_CLASSES else None
        ),
        "validationStage": (
            detail.get("validationStage") if detail.get("validationStage") in _GENERATION_VALIDATION_STAGES else None
        ),
        "fieldPath": _safe_generation_field_path(detail.get("fieldPath")),
        "validationType": (
            detail.get("validationType") if detail.get("validationType") in _GENERATION_VALIDATION_TYPES else None
        ),
        "ruleCode": detail.get("ruleCode") if detail.get("ruleCode") in _FIXED_TRANSLATION_RULES else None,
    }
    result["detail"] = safe
    return result


def material_failure_diagnostic(error: Exception, *, project: dict, stage: str, collected=None) -> dict:
    """Diagnostic failure cannot replace the business error or repeat paid work."""
    try:
        return _material_failure_diagnostic(error, project=project, stage=stage, collected=collected)
    except Exception:
        return {"schemaVersion": 2, "stage": "unknown", "diagnosticStatus": "unavailable"}


def _material_failure_diagnostic(error: Exception, *, project: dict, stage: str, collected=None) -> dict:
    """Describe only facts available at this catch, not a reconstructed upstream response."""
    result = {
        "schemaVersion": 2,
        "stage": stage if stage in {"source", "profile"} else "unknown",
        "errorClass": type(error).__name__[:64],
        "projectId": project.get("projectId"),
        "httpStatus": None,
        "host": None,
        "endpointCategory": None,
        "profileGenerationId": None,
        "profileGeneratedAt": None,
        "validationErrors": [],
        "validationErrorCount": None,
        "validationErrorsOmitted": None,
        "modelClass": None,
        "attemptEvidence": None,
        "generationFailures": [],
        "generationFailureCount": None,
        "generationFailuresOmitted": None,
    }
    if isinstance(error, httpx.HTTPError):
        if isinstance(error, httpx.HTTPStatusError):
            result["httpStatus"] = error.response.status_code
        try:
            url = error.request.url
        except RuntimeError:  # HTTP errors may legitimately have no request.
            url = None
        if url is not None and url.host in {"api.github.com", "raw.githubusercontent.com", "github.com"}:
            result["host"] = url.host
            result["endpointCategory"] = (
                "repository_metadata"
                if url.host == "api.github.com" and re.fullmatch(r"/repos/[^/]+/[^/]+", url.path)
                else "github_source"
            )
    profile = getattr(collected, "profile", None)
    # Only an actually collected profile identifies the attempted revision;
    # the existing project profile might instead be a previous retained version.
    if profile is not None:
        generation = getattr(profile, "generationId", None)
        if isinstance(generation, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", generation):
            result["profileGenerationId"] = generation
        generated_at = getattr(profile, "generatedAt", None)
        if hasattr(generated_at, "isoformat"):
            result["profileGeneratedAt"] = generated_at.isoformat()
    failures = getattr(collected, "generation_failures", None)
    if isinstance(failures, tuple | list):
        reviewed = [item for failure in failures if (item := _safe_generation_failure(failure)) is not None]
        result["generationFailureCount"] = len(reviewed)
        result["generationFailures"] = reviewed[:_SAMPLE_LIMIT]
        result["generationFailuresOmitted"] = max(0, len(reviewed) - _SAMPLE_LIMIT)
    if isinstance(error, ValidationError):
        result["attemptEvidence"] = profile_validation_attempt_evidence(error) or None
        result["modelClass"] = error.title if error.title in _MODELS else "unknown"
        details = error.errors(include_url=False, include_context=False, include_input=False)
        result["validationErrorCount"] = len(details)
        result["validationErrorsOmitted"] = max(0, len(details) - _SAMPLE_LIMIT)
        for detail in details[:_SAMPLE_LIMIT]:
            loc = detail.get("loc", ())
            # Only exact fixed literals are recognized. Never copy a dynamic
            # message, input or ctx.error into durable diagnostics.
            message = detail.get("msg", "")
            fixed = message.removeprefix("Value error, ")
            rule = PROFILE_VALIDATION_RULES.get(fixed) if error.title in _MODELS else None
            if detail["type"] in _CUSTOM_RULES and error.title in _MODELS:
                rule = detail["type"]
                fixed = _CUSTOM_RULES[rule]
            result["validationErrors"].append(
                {
                    "type": detail["type"]
                    if detail["type"] in _ERROR_TYPES or rule == detail["type"]
                    else "custom_error",
                    "loc": [part if type(part) is int or part in _FIELDS else "<field>" for part in loc[:12]],
                    "locationLimited": len(loc) > 12,
                    "ruleCode": rule or "unknown",
                    "safeExplanation": fixed if rule else None,
                }
            )
    return result
