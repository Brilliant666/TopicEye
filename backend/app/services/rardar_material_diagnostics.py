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
