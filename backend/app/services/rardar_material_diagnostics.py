"""Bounded metadata for material failures; never retain exception messages or bodies."""

from __future__ import annotations

import re
from typing import get_args

import httpx
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorType

from app.integrations.rardar import serving_schemas

_FIELDS = frozenset(
    field
    for model in vars(serving_schemas).values()
    if isinstance(model, type) and issubclass(model, BaseModel)
    for field in model.model_fields
)
_ERROR_TYPES = frozenset(get_args(ErrorType))
_SAMPLE_LIMIT = 4


def material_failure_diagnostic(error: Exception, *, project: dict, stage: str, collected=None) -> dict:
    """Describe only facts available at this catch, not a reconstructed upstream response."""
    result = {
        "schemaVersion": 1,
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
        details = error.errors(include_url=False, include_context=False, include_input=False)
        result["validationErrorCount"] = len(details)
        result["validationErrorsOmitted"] = max(0, len(details) - _SAMPLE_LIMIT)
        for detail in details[:_SAMPLE_LIMIT]:
            loc = detail.get("loc", ())
            result["validationErrors"].append(
                {
                    "type": detail["type"] if detail["type"] in _ERROR_TYPES else "custom_error",
                    "loc": [part if type(part) is int or part in _FIELDS else "<field>" for part in loc[:12]],
                    "locationLimited": len(loc) > 12,
                }
            )
    return result
