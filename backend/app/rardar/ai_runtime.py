"""Structured Rardar AI calls through TopicEye's real LLM control chain."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.core.database import async_session
from app.core.product_profile import get_product_profile
from app.models.rardar_poc import RardarAIRequest
from app.rardar.schemas import AIEnvelope, AIResultState
from app.repositories.rardar_poc_repo import RardarAIRequestRepository
from app.services.llm.mock_sub2api import get_mock_trace, request_input_hash
from app.services.llm.provider import call_llm_json_with_metadata


class RardarAIError(RuntimeError):
    def __init__(self, code: str, state: AIResultState, message: str):
        self.code = code
        self.state = state
        super().__init__(message)


@dataclass(frozen=True)
class RardarAIOutcome:
    result: BaseModel | dict[str, Any]
    audit: dict[str, Any]


def _error_classification(exc: Exception) -> tuple[str, AIResultState]:
    from app.services.llm.circuit_breaker import CircuitOpenError

    if isinstance(exc, CircuitOpenError):
        return "circuit_open", AIResultState.CIRCUIT_OPEN
    message = str(exc).lower()
    if "429" in message or "rate limit" in message:
        return "provider_rate_limited", AIResultState.FAILED
    if "timeout" in message:
        return "provider_timeout", AIResultState.FAILED
    if "503" in message or "5xx" in message:
        return "provider_5xx", AIResultState.FAILED
    return "provider_error", AIResultState.FAILED


async def _record_request(
    *,
    request_id: str,
    effort: str,
    scene: str,
    input_hash: str,
    latency_ms: int,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    attempt_count: int,
    result_state: AIResultState,
    error_code: str | None,
) -> None:
    profile = get_product_profile()
    async with async_session() as db:
        repo = RardarAIRequestRepository(db)
        await repo.add(
            RardarAIRequest(
                request_id=request_id,
                provider=profile.ai_provider,
                base_url_identifier="api.cosflow.icu/mock-no-network",
                model=profile.ai_model,
                reasoning_effort=effort,
                scene=scene,
                input_hash=input_hash,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                cached_tokens=cached_tokens,
                output_tokens=output_tokens,
                attempt_count=attempt_count,
                result_state=result_state.value,
                error_code=error_code,
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def call_rardar_ai(
    *,
    scene: str,
    reasoning_effort: str,
    payload: dict[str, Any],
    result_model: type[BaseModel] | None,
) -> RardarAIOutcome:
    if reasoning_effort not in {"medium", "high", "xhigh"}:
        raise ValueError("unsupported Rardar reasoning effort")
    profile = get_product_profile()
    messages = [
        {
            "role": "system",
            "content": "Return one JSON envelope. Facts and AI judgment must remain distinct.",
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]
    input_hash = request_input_hash(
        messages=messages,
        scene=scene,
        reasoning_effort=reasoning_effort,
    )
    trace_before = get_mock_trace(input_hash)
    started = time.perf_counter()
    metadata: dict[str, Any] = {}
    try:
        raw_result, metadata = await call_llm_json_with_metadata(
            messages,
            temperature=0.0,
            max_tokens=2400,
            scene=scene,
            routing_group=profile.ai_routing_group,
            reasoning_effort=reasoning_effort,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if isinstance(raw_result, dict) and "raw_response" in raw_result:
            raise RardarAIError(
                "invalid_provider_json",
                AIResultState.INVALID_JSON,
                "Mock provider returned invalid JSON",
            )
        try:
            envelope = AIEnvelope.model_validate_json(json.dumps(raw_result, ensure_ascii=False, sort_keys=True))
        except ValidationError as exc:
            raise RardarAIError(
                "provider_schema_mismatch",
                AIResultState.SCHEMA_MISMATCH,
                "Mock provider envelope failed local Schema validation",
            ) from exc
        if envelope.providerTrace.reasoningEffort != reasoning_effort:
            raise RardarAIError(
                "reasoning_effort_mismatch",
                AIResultState.SCHEMA_MISMATCH,
                "Provider did not preserve requested reasoning effort",
            )
        if envelope.providerTrace.model != profile.ai_model:
            raise RardarAIError(
                "provider_model_mismatch",
                AIResultState.SCHEMA_MISMATCH,
                "Provider did not preserve the fixed POC model",
            )
        if result_model is None:
            if not isinstance(envelope.result, dict) or not envelope.result:
                raise RardarAIError(
                    "empty_provider_result",
                    AIResultState.SCHEMA_MISMATCH,
                    "Provider result must be a non-empty object",
                )
            parsed_result: BaseModel | dict[str, Any] = envelope.result
        else:
            try:
                parsed_result = result_model.model_validate_json(
                    json.dumps(envelope.result, ensure_ascii=False, sort_keys=True)
                )
            except ValidationError as exc:
                raise RardarAIError(
                    "result_schema_mismatch",
                    AIResultState.SCHEMA_MISMATCH,
                    "Provider result failed local Schema validation",
                ) from exc

        cache_hit = bool(metadata.get("cache_hit"))
        request_id = (
            f"mock_cache_{hashlib.sha256(f'{input_hash}:{uuid4().hex}'.encode()).hexdigest()[:32]}"
            if cache_hit
            else envelope.providerTrace.requestId
        )
        state = AIResultState.CACHE_HIT if cache_hit else AIResultState.READY
        cached_tokens = envelope.providerTrace.inputTokens if cache_hit else envelope.providerTrace.cachedTokens
        await _record_request(
            request_id=request_id,
            effort=reasoning_effort,
            scene=scene,
            input_hash=input_hash,
            latency_ms=latency_ms,
            input_tokens=envelope.providerTrace.inputTokens,
            cached_tokens=cached_tokens,
            output_tokens=envelope.providerTrace.outputTokens,
            attempt_count=0 if cache_hit else envelope.providerTrace.attemptCount,
            result_state=state,
            error_code=None,
        )
        return RardarAIOutcome(
            result=parsed_result,
            audit={
                "requestId": request_id,
                "provider": profile.ai_provider,
                "model": profile.ai_model,
                "reasoningEffort": reasoning_effort,
                "scene": scene,
                "inputHash": input_hash,
                "latencyMs": latency_ms,
                "usage": {
                    "inputTokens": envelope.providerTrace.inputTokens,
                    "cachedTokens": cached_tokens,
                    "outputTokens": envelope.providerTrace.outputTokens,
                },
                "attemptCount": 0 if cache_hit else envelope.providerTrace.attemptCount,
                "resultState": state.value,
            },
        )
    except RardarAIError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        trace = get_mock_trace(input_hash)
        current_trace = trace if trace != trace_before else None
        cache_hit = bool(metadata.get("cache_hit"))
        request_id = f"mock_invalid_{uuid4().hex}" if cache_hit or current_trace is None else current_trace.request_id
        await _record_request(
            request_id=request_id,
            effort=reasoning_effort,
            scene=scene,
            input_hash=input_hash,
            latency_ms=latency_ms,
            input_tokens=current_trace.input_tokens if current_trace else 0,
            cached_tokens=current_trace.input_tokens if cache_hit and current_trace else 0,
            output_tokens=current_trace.output_tokens if current_trace else 0,
            attempt_count=current_trace.attempt_count if current_trace else 0,
            result_state=exc.state,
            error_code=exc.code,
        )
        raise
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        error_code, state = _error_classification(exc)
        trace = get_mock_trace(input_hash)
        current_trace = trace if trace != trace_before else None
        request_id = current_trace.request_id if current_trace else f"mock_skipped_{uuid4().hex}"
        await _record_request(
            request_id=request_id,
            effort=reasoning_effort,
            scene=scene,
            input_hash=input_hash,
            latency_ms=latency_ms,
            input_tokens=current_trace.input_tokens if current_trace else 0,
            cached_tokens=0,
            output_tokens=current_trace.output_tokens if current_trace else 0,
            attempt_count=current_trace.attempt_count if current_trace else 0,
            result_state=state,
            error_code=error_code,
        )
        raise RardarAIError(error_code, state, str(exc)) from exc
