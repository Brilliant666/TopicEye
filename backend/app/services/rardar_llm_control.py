"""Minimal Rardar boundary over TopicEye's existing LLM control plane.

The business boundary deliberately has no provider, endpoint, key, or model
arguments.  Those remain owned by TopicEye's ``llm_models`` configuration and
shared route/failover/rate-limit/retry/circuit/cache/logging implementation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.services.llm._call_engine import _is_deterministic_request_error, _is_rate_limit_error
from app.services.llm._model_cache import _model_cache
from app.services.llm.provider import LlmRouteNotConfiguredError, call_llm_with_metadata
from app.services.llm.strict_json import StrictJSONError, loads_strict_json

RARDAR_ROUTING_GROUP = "rardar"
_JSON_RESPONSE_FORMAT = {"type": "json_object"}


class RardarLLMScene(StrEnum):
    PROJECT_SUMMARY = "rardar_project_summary"
    PROJECT_PROFILE = "rardar_project_profile"
    EXPLOSION_EXPLANATION = "rardar_explosion_explanation"
    FIND_PROJECT_COMPARISON = "rardar_find_project_comparison"
    WORTH_SEEING_GATE = "rardar_worth_seeing_gate"
    WORTH_SEEING_MEANINGFUL_CHANGE = "rardar_worth_seeing_meaningful_change"
    WORTH_SEEING_COPY = "rardar_worth_seeing_copy"


class ReasoningEffort(StrEnum):
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class RardarLLMError(RuntimeError):
    """Stable, non-secret error exposed to Rardar business callers."""

    def __init__(self, code: str, *, classification: str | None = None):
        self.code = code
        self.classification = classification
        super().__init__(code)


@dataclass(frozen=True)
class RardarLLMMetadata:
    scene: str
    routing_group: str
    model_display_name: str | None
    model_id: int | None
    provider: str | None
    reasoning_effort: str | None
    prompt_version: str | None
    schema_version: str | None
    latency_ms: int
    usage: dict[str, Any] | None
    cache_hit: bool
    result_state: str


@dataclass(frozen=True)
class RardarLLMResult:
    content: str
    metadata: RardarLLMMetadata


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class RardarStructuredResult(Generic[T]):
    value: T
    metadata: RardarLLMMetadata


def _scene_value(scene: RardarLLMScene) -> str:
    if not isinstance(scene, RardarLLMScene):
        raise RardarLLMError("rardar_llm_request_rejected")
    return scene.value


def _effort_value(reasoning_effort: ReasoningEffort | None) -> str | None:
    if reasoning_effort is None:
        return None
    if not isinstance(reasoning_effort, ReasoningEffort):
        raise RardarLLMError("rardar_llm_request_rejected")
    return reasoning_effort.value


def _version(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise RardarLLMError("rardar_llm_request_rejected")
    return value.strip()


def _schema_identity(response_model: type[BaseModel], prompt_version: str, schema_version: str) -> str:
    if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
        raise RardarLLMError("rardar_llm_request_rejected")
    canonical_schema = json.dumps(
        response_model.model_json_schema(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    identity = json.dumps(
        {
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "response_schema_sha256": hashlib.sha256(canonical_schema.encode("utf-8")).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _metadata(
    *,
    scene: str,
    effort: str | None,
    provider_metadata: dict[str, Any],
    latency_ms: int,
    prompt_version: str | None = None,
    schema_version: str | None = None,
) -> RardarLLMMetadata:
    return RardarLLMMetadata(
        scene=scene,
        routing_group=RARDAR_ROUTING_GROUP,
        model_display_name=provider_metadata.get("model_name"),
        model_id=provider_metadata.get("model_id"),
        provider=provider_metadata.get("provider"),
        reasoning_effort=effort,
        prompt_version=prompt_version,
        schema_version=schema_version,
        latency_ms=latency_ms,
        usage=provider_metadata.get("usage"),
        cache_hit=bool(provider_metadata.get("cache_hit", False)),
        result_state="cached" if provider_metadata.get("cache_hit") else "completed",
    )


def _map_control_error(error: Exception) -> RardarLLMError:
    if isinstance(error, RardarLLMError):
        return error
    if isinstance(error, LlmRouteNotConfiguredError):
        return RardarLLMError("rardar_llm_not_configured")
    if isinstance(error, ValueError) or _is_deterministic_request_error(error):
        return RardarLLMError("rardar_llm_request_rejected")
    if isinstance(error, TimeoutError | asyncio.TimeoutError) or "timeout" in str(error).casefold():
        return RardarLLMError("rardar_llm_unavailable", classification="timeout")
    if _is_rate_limit_error(error):
        return RardarLLMError("rardar_llm_unavailable", classification="rate_limited")
    return RardarLLMError("rardar_llm_unavailable", classification="provider_error")


async def call_rardar_llm(
    *,
    scene: RardarLLMScene,
    messages: list[dict[str, Any]],
    reasoning_effort: ReasoningEffort | None = None,
) -> RardarLLMResult:
    """Invoke a configured Rardar route through TopicEye's control plane."""
    scene_value = _scene_value(scene)
    effort = _effort_value(reasoning_effort)
    started = time.monotonic()
    try:
        content, provider_metadata = await call_llm_with_metadata(
            messages,
            temperature=None,
            max_tokens=None,
            scene=scene_value,
            routing_group=RARDAR_ROUTING_GROUP,
            reasoning_effort=effort,
            strict_routing_group=True,
        )
    except Exception as exc:
        raise _map_control_error(exc) from None
    return RardarLLMResult(
        content=content,
        metadata=_metadata(
            scene=scene_value,
            effort=effort,
            provider_metadata=provider_metadata,
            latency_ms=int((time.monotonic() - started) * 1000),
        ),
    )


async def resolve_rardar_route_identity() -> str:
    """Return a secret-free fingerprint of the complete configured Rardar route."""

    models = await _model_cache.get_route_models(RARDAR_ROUTING_GROUP, fallback_to_any=False)
    if not models:
        raise RardarLLMError("rardar_llm_not_configured")
    route = [
        {
            "id": model.id,
            "name": model.name,
            "provider": model.provider,
            "modelId": model.model_id,
            "apiBaseSha256": hashlib.sha256((model.api_base or "").encode("utf-8")).hexdigest(),
            "priority": model.routing_priority,
            "temperature": model.temperature,
            "maxTokens": model.max_tokens,
            "extraParams": model.extra_params,
        }
        for model in models
    ]
    canonical = json.dumps(route, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def call_rardar_prompt_json(
    *,
    scene: RardarLLMScene,
    messages: list[dict[str, Any]],
    reasoning_effort: ReasoningEffort | None = None,
    cache_identity: str,
) -> RardarLLMResult:
    """Request JSON mode while leaving strict parsing and schema validation to the caller."""

    scene_value = _scene_value(scene)
    effort = _effort_value(reasoning_effort)
    started = time.monotonic()
    try:
        content, provider_metadata = await call_llm_with_metadata(
            messages,
            temperature=None,
            max_tokens=None,
            scene=scene_value,
            routing_group=RARDAR_ROUTING_GROUP,
            response_format=_JSON_RESPONSE_FORMAT,
            reasoning_effort=effort,
            cache_identity=cache_identity,
            strict_routing_group=True,
        )
    except Exception as exc:
        raise _map_control_error(exc) from None
    return RardarLLMResult(
        content=content,
        metadata=_metadata(
            scene=scene_value,
            effort=effort,
            provider_metadata=provider_metadata,
            latency_ms=int((time.monotonic() - started) * 1000),
        ),
    )


async def call_rardar_structured(
    *,
    scene: RardarLLMScene,
    messages: list[dict[str, Any]],
    response_model: type[T],
    prompt_version: str,
    schema_version: str,
    reasoning_effort: ReasoningEffort | None = None,
) -> RardarStructuredResult[T]:
    """Invoke the shared JSON mode, then enforce the caller's Pydantic schema."""
    scene_value = _scene_value(scene)
    effort = _effort_value(reasoning_effort)
    prompt_version = _version(prompt_version)
    schema_version = _version(schema_version)
    cache_identity = _schema_identity(response_model, prompt_version, schema_version)
    started = time.monotonic()
    try:
        raw, provider_metadata = await call_llm_with_metadata(
            messages,
            temperature=None,
            max_tokens=None,
            scene=scene_value,
            routing_group=RARDAR_ROUTING_GROUP,
            response_format=_JSON_RESPONSE_FORMAT,
            reasoning_effort=effort,
            cache_identity=cache_identity,
            strict_routing_group=True,
        )
        parsed = loads_strict_json(raw)
        value = response_model.model_validate(parsed, strict=True)
    except StrictJSONError as exc:
        classification = "empty" if "empty" in str(exc).casefold() else "invalid_json"
        raise RardarLLMError("rardar_llm_invalid_output", classification=classification) from None
    except ValidationError:
        raise RardarLLMError("rardar_llm_invalid_output", classification="schema_invalid") from None
    except Exception as exc:
        raise _map_control_error(exc) from None
    return RardarStructuredResult(
        value=value,
        metadata=_metadata(
            scene=scene_value,
            effort=effort,
            provider_metadata=provider_metadata,
            latency_ms=int((time.monotonic() - started) * 1000),
            prompt_version=prompt_version,
            schema_version=schema_version,
        ),
    )
