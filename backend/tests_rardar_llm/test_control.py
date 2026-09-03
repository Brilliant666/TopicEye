from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from litellm.exceptions import BadRequestError, UnsupportedParamsError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import wait_none

from app.api.v1 import llm_models as llm_models_api
from app.core import database
from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.models.llm_model import LlmCallLog, LlmModel
from app.services.llm import _call_engine, provider
from app.services.llm.circuit_breaker import get_llm_circuit_breaker, reset_llm_circuit_breakers
from app.services.llm.response_cache import get_llm_cache
from app.services.rardar_llm_control import (
    RardarLLMError,
    RardarLLMScene,
    ReasoningEffort,
    call_rardar_llm,
    call_rardar_prompt_json,
    call_rardar_structured,
    resolve_rardar_route_identity,
)
from app.services.secret_store import encrypt_secret

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence"
TEST_KEY = "sk-test-rardar-control-not-real"


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    count: int


class AlternatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    count: int
    note: str | None = None


class ControlHarness:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def add_model(
        self,
        *,
        name: str,
        provider_name: str = "openai",
        model_id: str | None = None,
        api_base: str = "https://provider.invalid/v1",
        routing_group: str = "rardar",
        priority: int = 100,
        enabled: bool = True,
        api_key: str = TEST_KEY,
        temperature: float = 0.17,
        max_tokens: int = 777,
    ) -> int:
        async with self.sessions() as session:
            model = LlmModel(
                name=name,
                provider=provider_name,
                model_id=model_id or f"{provider_name}/{name}",
                api_key=encrypt_secret(api_key),
                api_base=api_base,
                enabled=enabled,
                routing_group=routing_group,
                routing_priority=priority,
                cooldown_seconds=1,
                temperature=temperature,
                max_tokens=max_tokens,
                requests_per_minute=120,
            )
            session.add(model)
            await session.commit()
            return model.id

    async def set_enabled(self, model_id: int, enabled: bool) -> None:
        async with self.sessions() as session:
            model = await session.get(LlmModel, model_id)
            assert model is not None
            model.enabled = enabled
            await session.commit()

    async def reload_routes(self) -> None:
        await provider.invalidate_model_cache()
        await provider._model_cache.refresh()

    async def logs(self) -> list[LlmCallLog]:
        async with self.sessions() as session:
            return list((await session.scalars(select(LlmCallLog).order_by(LlmCallLog.id))).all())


@pytest_asyncio.fixture
async def control_plane(monkeypatch) -> ControlHarness:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(LlmModel.__table__.create)
        await connection.run_sync(LlmCallLog.__table__.create)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session", sessions)

    provider._model_cache._route_models = []
    provider._model_cache._last_refresh = time.monotonic()
    provider._failover.reset()
    reset_llm_circuit_breakers()
    get_llm_cache().clear()
    provider.reset_completion_semaphore()
    provider.reset_model_rate_limiters()
    provider.reset_token_rate_limiter()
    yield ControlHarness(sessions)
    provider._model_cache._route_models = []
    provider._model_cache._last_refresh = time.monotonic()
    provider._failover.reset()
    reset_llm_circuit_breakers()
    get_llm_cache().clear()
    await engine.dispose()


def _response(content: str, model: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=model,
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
    )


def _patch_no_wait_retry(monkeypatch) -> None:
    monkeypatch.setattr(provider, "_call_with_retry", _call_engine._call_with_retry.retry_with(wait=wait_none()))


@pytest.mark.asyncio
async def test_selection_shared_budget_counts_actual_retry_cache_and_exhaustion(control_plane, monkeypatch, tmp_path):
    from app.services.llm.provider_budget import ProviderBudgetLedger

    ledger = ProviderBudgetLedger.initialize(tmp_path / "run" / "provider-budget.json", "mock-executions")
    monkeypatch.setenv("RARDAR_LLM_RUN_ID", ledger.run_id)
    monkeypatch.setenv("RARDAR_LLM_BUDGET_PATH", str(ledger.path))
    monkeypatch.setenv("RARDAR_LLM_BUDGET_LIMIT", "40")
    await control_plane.add_model(name="budget-route")
    await control_plane.reload_routes()
    _patch_no_wait_retry(monkeypatch)
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        assert kwargs["num_retries"] == 0
        if len(calls) == 1:
            raise TimeoutError("mock network attempt timed out")
        return _response("{}", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", completion)

    async def call(text):
        return await call_rardar_prompt_json(
            scene=RardarLLMScene.WORTH_SEEING_GATE,
            messages=[{"role": "user", "content": text}],
            reasoning_effort=ReasoningEffort.HIGH,
            cache_identity="a" * 64,
        )

    await call("one")
    assert ledger.snapshot()["attempted"] == 2 and ledger.snapshot()["failed"] == 1
    await call("one")
    assert len(calls) == 2 and ledger.snapshot()["cacheHits"] == 1
    for _ in range(38):
        ledger.record("reserved", "scope_value")
    with pytest.raises(RardarLLMError) as error:
        await call("different")
    assert error.value.code == "provider_budget_exhausted"
    assert len(calls) == 2 and ledger.snapshot()["reserved"] == 40


@pytest.mark.asyncio
async def test_strict_rardar_route_never_falls_back_to_default(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="default-only", routing_group="default")
    await control_plane.reload_routes()
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response("default", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)

    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": "facts"}],
        )
    assert error.value.code == "rardar_llm_not_configured"
    assert calls == []

    # TopicEye's pre-existing permissive route behaviour remains unchanged.
    assert await provider.call_llm([{"role": "user", "content": "topic"}], routing_group="missing") == "default"


@pytest.mark.asyncio
async def test_model_configuration_owns_provider_endpoint_model_and_generation_settings(
    control_plane, monkeypatch
) -> None:
    first_id = await control_plane.add_model(
        name="first",
        provider_name="openai",
        model_id="openai/model-a",
        api_base="https://first.invalid/v1",
        priority=10,
        temperature=0.41,
        max_tokens=901,
    )
    second_id = await control_plane.add_model(
        name="second",
        provider_name="anthropic",
        model_id="anthropic/model-b",
        api_base="https://second.invalid/v1",
        priority=20,
        enabled=False,
        temperature=0.22,
        max_tokens=902,
    )
    await control_plane.reload_routes()
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response("ok", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)

    async def unchanged_business_call():
        return await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_PROFILE,
            messages=[{"role": "user", "content": "same business input"}],
        )

    first = await unchanged_business_call()
    assert calls[-1]["model"] == "openai/model-a"
    assert calls[-1]["api_base"] == "https://first.invalid/v1"
    assert calls[-1]["api_key"] == TEST_KEY
    assert calls[-1]["temperature"] == 0.41
    assert calls[-1]["max_tokens"] == 901
    assert first.metadata.model_id == first_id

    await control_plane.set_enabled(first_id, False)
    await control_plane.set_enabled(second_id, True)
    await control_plane.reload_routes()
    second = await unchanged_business_call()
    assert calls[-1]["model"] == "anthropic/model-b"
    assert calls[-1]["api_base"] == "https://second.invalid/v1"
    assert calls[-1]["temperature"] == 0.22
    assert calls[-1]["max_tokens"] == 902
    assert second.metadata.model_id == second_id


@pytest.mark.asyncio
async def test_prompt_json_uses_strict_rardar_route_and_route_identity_tracks_configuration(
    control_plane, monkeypatch, tmp_path
) -> None:
    from app.services.llm.provider_budget import ProviderBudgetLedger

    ledger = ProviderBudgetLedger.initialize(tmp_path / "run" / "provider-budget.json", "mock-control")
    monkeypatch.setenv("RARDAR_LLM_RUN_ID", "mock-control")
    monkeypatch.setenv("RARDAR_LLM_BUDGET_PATH", str(ledger.path))
    monkeypatch.setenv("RARDAR_LLM_BUDGET_LIMIT", "40")
    first_id = await control_plane.add_model(name="selection-json", priority=10)
    await control_plane.reload_routes()
    identity_before = await resolve_rardar_route_identity()
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response('{"scopeStatus":"in_scope"}', kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    result = await call_rardar_prompt_json(
        scene=RardarLLMScene.WORTH_SEEING_GATE,
        messages=[{"role": "user", "content": "bounded evidence"}],
        reasoning_effort=ReasoningEffort.HIGH,
        cache_identity="a" * 64,
    )
    assert result.content == '{"scopeStatus":"in_scope"}'
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["reasoning_effort"] == "high"

    await control_plane.set_enabled(first_id, False)
    await control_plane.add_model(name="selection-json-next", priority=10)
    await control_plane.reload_routes()
    identity_after = await resolve_rardar_route_identity()
    assert len(identity_before) == len(identity_after) == 64
    assert identity_before != identity_after
    assert TEST_KEY not in identity_before + identity_after


@pytest.mark.asyncio
async def test_shared_route_chain_retry_failover_cache_and_call_log(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="first", model_id="openai/first", priority=10)
    await control_plane.add_model(name="second", model_id="openai/second", priority=20)
    await control_plane.reload_routes()
    _patch_no_wait_retry(monkeypatch)
    calls: list[str] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "openai/first":
            raise RuntimeError("temporary upstream 503")
        return _response("from-second", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    messages = [{"role": "user", "content": "shared control"}]
    first = await call_rardar_llm(scene=RardarLLMScene.PROJECT_SUMMARY, messages=messages)
    cached = await call_rardar_llm(scene=RardarLLMScene.PROJECT_SUMMARY, messages=messages)

    assert first.content == cached.content == "from-second"
    assert calls == ["openai/first", "openai/first", "openai/second"]
    assert cached.metadata.cache_hit is True
    logs = await control_plane.logs()
    assert [row.status for row in logs] == ["FAILED", "FAILED", "DONE"]
    assert all(row.scene == RardarLLMScene.PROJECT_SUMMARY.value for row in logs)


@pytest.mark.asyncio
async def test_reasoning_effort_passthrough_audit_and_cache_partition(control_plane, monkeypatch, caplog) -> None:
    await control_plane.add_model(name="reasoner")
    await control_plane.reload_routes()
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response(f"response-{len(calls)}", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    caplog.set_level(logging.INFO, logger="app.services.llm._call_engine")
    messages = [{"role": "user", "content": "effort"}]

    none_result = await call_rardar_llm(scene=RardarLLMScene.PROJECT_SUMMARY, messages=messages)
    medium = await call_rardar_llm(
        scene=RardarLLMScene.PROJECT_SUMMARY,
        messages=messages,
        reasoning_effort=ReasoningEffort.MEDIUM,
    )
    medium_cached = await call_rardar_llm(
        scene=RardarLLMScene.PROJECT_SUMMARY,
        messages=messages,
        reasoning_effort=ReasoningEffort.MEDIUM,
    )
    high = await call_rardar_llm(
        scene=RardarLLMScene.PROJECT_SUMMARY,
        messages=messages,
        reasoning_effort=ReasoningEffort.HIGH,
    )
    xhigh = await call_rardar_llm(
        scene=RardarLLMScene.PROJECT_SUMMARY,
        messages=messages,
        reasoning_effort=ReasoningEffort.XHIGH,
    )

    assert "reasoning_effort" not in calls[0]
    assert [call.get("reasoning_effort") for call in calls[1:]] == ["medium", "high", "xhigh"]
    assert calls[0]["temperature"] == 0.17
    assert all("temperature" not in call for call in calls[1:])
    assert len(calls) == 4
    assert medium_cached.content == medium.content
    assert medium_cached.metadata.cache_hit is True
    assert none_result.metadata.reasoning_effort is None
    assert high.metadata.reasoning_effort == "high"
    assert xhigh.metadata.reasoning_effort == "xhigh"
    assert "reasoning_effort=xhigh" in caplog.text

    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=messages,
            reasoning_effort="low",  # type: ignore[arg-type]
        )
    assert error.value.code == "rardar_llm_request_rejected"
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_reasoning_effort_is_never_silently_downgraded(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="strict-effort")
    await control_plane.reload_routes()
    calls: list[dict] = []

    async def unsupported_effort(**kwargs):
        calls.append(kwargs)
        raise UnsupportedParamsError(
            "reasoning effort unsupported",
            llm_provider="openai",
            model=kwargs["model"],
        )

    monkeypatch.setattr(_call_engine, "acompletion", unsupported_effort)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": "effort"}],
            reasoning_effort=ReasoningEffort.XHIGH,
        )
    assert error.value.code == "rardar_llm_request_rejected"
    assert [call["reasoning_effort"] for call in calls] == ["xhigh"]


@pytest.mark.asyncio
async def test_existing_response_format_fallback_preserves_reasoning_effort(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="json-fallback")
    await control_plane.reload_routes()
    calls: list[dict] = []

    async def provider_without_json_mode(**kwargs):
        calls.append(kwargs)
        if "response_format" in kwargs:
            raise UnsupportedParamsError(
                "response_format unsupported",
                llm_provider="openai",
                model=kwargs["model"],
            )
        return _response('{"title":"fallback","count":3}', kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", provider_without_json_mode)
    result = await call_rardar_structured(
        scene=RardarLLMScene.PROJECT_PROFILE,
        messages=[{"role": "user", "content": "facts"}],
        response_model=StrictPayload,
        prompt_version="p1",
        schema_version="s1",
        reasoning_effort=ReasoningEffort.XHIGH,
    )
    assert result.value.title == "fallback"
    assert len(calls) == 2
    assert [call["reasoning_effort"] for call in calls] == ["xhigh", "xhigh"]
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


@pytest.mark.asyncio
async def test_structured_cache_separates_prompt_schema_effort_and_model_schema(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="structured")
    await control_plane.reload_routes()
    calls: list[dict] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response('{"title":"safe","count":1}', kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    arguments = {
        "scene": RardarLLMScene.PROJECT_PROFILE,
        "messages": [{"role": "user", "content": "structured"}],
        "response_model": StrictPayload,
        "prompt_version": "prompt-v1",
        "schema_version": "schema-v1",
        "reasoning_effort": ReasoningEffort.MEDIUM,
    }
    first = await call_rardar_structured(**arguments)
    repeated = await call_rardar_structured(**arguments)
    await call_rardar_structured(**(arguments | {"prompt_version": "prompt-v2"}))
    await call_rardar_structured(**(arguments | {"schema_version": "schema-v2"}))
    await call_rardar_structured(**(arguments | {"reasoning_effort": ReasoningEffort.XHIGH}))
    await call_rardar_structured(**(arguments | {"response_model": AlternatePayload}))

    assert first.value == StrictPayload(title="safe", count=1)
    assert repeated.metadata.cache_hit is True
    assert len(calls) == 5
    assert all(call["response_format"] == {"type": "json_object"} for call in calls)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-json",
        '{"title":"a","title":"b","count":1}',
        '{"title":"a","count":NaN}',
        '{"title":"a","count":Infinity}',
        '{"title":"a","count":"1"}',
        '{"title":"a"}',
        '{"title":"a","count":1,"extra":true}',
        "[]",
    ],
)
@pytest.mark.asyncio
async def test_structured_output_fails_closed(control_plane, monkeypatch, raw: str) -> None:
    await control_plane.add_model(name="invalid-output")
    await control_plane.reload_routes()

    async def fake_completion(**kwargs):
        return _response(raw, kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_structured(
            scene=RardarLLMScene.EXPLOSION_EXPLANATION,
            messages=[{"role": "user", "content": "facts"}],
            response_model=StrictPayload,
            prompt_version="p1",
            schema_version="s1",
        )
    assert error.value.code == "rardar_llm_invalid_output"
    if raw:
        assert raw not in str(error.value)


@pytest.mark.asyncio
async def test_structured_output_accepts_utf8_and_json_fence(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="valid-output")
    await control_plane.reload_routes()

    async def fake_completion(**kwargs):
        return _response('```json\n{"title":"中文","count":2}\n```', kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    result = await call_rardar_structured(
        scene=RardarLLMScene.PROJECT_PROFILE,
        messages=[{"role": "user", "content": "facts"}],
        response_model=StrictPayload,
        prompt_version="p1",
        schema_version="s1",
    )
    assert result.value.title == "中文"


@pytest.mark.parametrize(
    ("upstream_error", "expected_code"),
    [
        (TimeoutError("provider timeout"), "rardar_llm_unavailable"),
        (RuntimeError("429 rate limit"), "rardar_llm_unavailable"),
        (RuntimeError("upstream 503"), "rardar_llm_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_upstream_failures_have_stable_rardar_errors(
    control_plane, monkeypatch, upstream_error: Exception, expected_code: str
) -> None:
    await control_plane.add_model(name="failing")
    await control_plane.reload_routes()
    _patch_no_wait_retry(monkeypatch)

    async def fake_completion(**_kwargs):
        raise upstream_error

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": "private prompt"}],
        )
    assert error.value.code == expected_code
    assert "private prompt" not in str(error.value)


@pytest.mark.asyncio
async def test_deterministic_provider_rejection_maps_without_failover(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="first", priority=10)
    await control_plane.add_model(name="second", priority=20)
    await control_plane.reload_routes()
    calls: list[str] = []

    async def reject(**kwargs):
        calls.append(kwargs["model"])
        raise BadRequestError("content rejected", model=kwargs["model"], llm_provider="openai")

    monkeypatch.setattr(_call_engine, "acompletion", reject)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": "request"}],
        )
    assert error.value.code == "rardar_llm_request_rejected"
    assert calls == ["openai/first"]


@pytest.mark.asyncio
async def test_circuit_open_maps_to_unavailable_without_calling_provider(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="circuit")
    await control_plane.reload_routes()
    breaker = get_llm_circuit_breaker("rardar")
    for _ in range(breaker.failure_threshold):
        await breaker.record_failure()
    calls = 0

    async def fake_completion(**kwargs):
        nonlocal calls
        calls += 1
        return _response("unexpected", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": "facts"}],
        )
    assert error.value.code == "rardar_llm_unavailable"
    assert calls == 0


@pytest.mark.asyncio
async def test_key_is_encrypted_masked_and_absent_from_errors_and_logs(control_plane, monkeypatch, caplog) -> None:
    model_id = await control_plane.add_model(name="secret-safe")
    await control_plane.reload_routes()
    _patch_no_wait_retry(monkeypatch)
    secret = TEST_KEY
    prompt = "do-not-log-this-prompt"
    raw = "do-not-leak-upstream-body"

    async with control_plane.sessions() as session:
        model = await session.get(LlmModel, model_id)
        assert model is not None
        assert model.api_key != secret
        payload = llm_models_api._model_payload(model)
        assert payload["api_key_set"] is True
        assert "api_key" not in payload

    async def fake_completion(**kwargs):
        assert kwargs["api_key"] == secret
        raise RuntimeError(f"{raw}; Authorization: Bearer {secret}; prompt={prompt}")

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    caplog.set_level(logging.INFO)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": prompt}],
        )
    logs = await control_plane.logs()
    combined = "\n".join(filter(None, [str(error.value), caplog.text, *(row.error_message or "" for row in logs)]))
    assert error.value.code == "rardar_llm_unavailable"
    assert secret not in combined
    assert prompt not in combined
    assert raw not in combined


@pytest.mark.asyncio
async def test_model_test_api_redacts_provider_exception(control_plane, monkeypatch) -> None:
    model_id = await control_plane.add_model(name="model-test-safe")
    secret = TEST_KEY

    def fake_completion(**kwargs):
        assert kwargs["api_key"] == secret
        raise RuntimeError(f"Authorization: Bearer {secret}; private provider response")

    monkeypatch.setattr("litellm.completion", fake_completion)
    async with control_plane.sessions() as session:
        result = await llm_models_api.test_model(model_id, session)
    assert result["status"] == "failed"
    assert secret not in result["error"]
    assert "private provider response" not in result["error"]
    logs = await control_plane.logs()
    assert secret not in "\n".join(row.error_message or "" for row in logs)


@pytest.mark.asyncio
async def test_today_fact_artifact_is_independent_from_llm_failure(control_plane, monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "rardar-data"
    shutil.copytree(FIXTURES / "revision-a", root)
    adapter = RardarIntelligenceAdapter.from_config(str(root))
    before = adapter.load_explosion_board().model_dump(mode="json")

    await control_plane.add_model(name="fact-isolation")
    await control_plane.reload_routes()
    _patch_no_wait_retry(monkeypatch)

    async def fake_completion(**_kwargs):
        raise RuntimeError("upstream 503")

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    with pytest.raises(RardarLLMError):
        await call_rardar_llm(
            scene=RardarLLMScene.EXPLOSION_EXPLANATION,
            messages=[{"role": "user", "content": "facts"}],
        )

    after = adapter.load_explosion_board().model_dump(mode="json")
    assert after == before
    assert [item["repository"] for item in after["exactRanked"]] == [
        item["repository"] for item in before["exactRanked"]
    ]


@pytest.mark.asyncio
async def test_disabled_rardar_models_are_not_configured(control_plane, monkeypatch) -> None:
    await control_plane.add_model(name="disabled", enabled=False)
    await control_plane.reload_routes()
    calls = 0

    async def fake_completion(**kwargs):
        nonlocal calls
        calls += 1
        return _response("unexpected", kwargs["model"])

    monkeypatch.setattr(_call_engine, "acompletion", fake_completion)
    with pytest.raises(RardarLLMError) as error:
        await call_rardar_llm(
            scene=RardarLLMScene.PROJECT_SUMMARY,
            messages=[{"role": "user", "content": "facts"}],
        )
    assert error.value.code == "rardar_llm_not_configured"
    assert calls == 0


@pytest.mark.asyncio
async def test_route_cache_uses_real_model_rows_and_no_business_tables(control_plane) -> None:
    await control_plane.add_model(name="priority-b", priority=20)
    await control_plane.add_model(name="priority-a", priority=10)
    await control_plane.add_model(name="other", routing_group="default", priority=1)
    await control_plane.reload_routes()
    routes = await provider._model_cache.get_route_models("rardar", fallback_to_any=False)
    assert [model.name for model in routes] == ["priority-a", "priority-b"]
    async with control_plane.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(LlmModel)) == 3
        assert await session.scalar(select(func.count()).select_from(LlmCallLog)) == 0
