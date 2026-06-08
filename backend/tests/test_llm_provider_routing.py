from types import SimpleNamespace
import asyncio

import pytest

from app.services.llm import provider


def _model(model_id: int, name: str, priority: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=model_id,
        name=name,
        provider="openai",
        model_id=name,
        api_key="test-key",
        api_base="https://example.test/v1",
        routing_group="default",
        routing_priority=priority,
        cooldown_seconds=300,
        temperature=0.3,
        max_tokens=2000,
        extra_params=None,
    )


@pytest.mark.asyncio
async def test_call_llm_fails_over_across_ordered_model_chain(monkeypatch):
    provider._failover.reset()
    models = [_model(1, "first", 10), _model(2, "second", 20)]
    calls = []

    async def route_models(group="default"):
        return models

    async def fake_call(messages, model, api_key, api_base, temperature, max_tokens, response_format, model_config, scene):
        calls.append(model)
        if model == "openai/first":
            raise RuntimeError("first failed")
        return "ok from second"

    monkeypatch.setattr(provider._model_cache, "get_route_models", route_models)
    monkeypatch.setattr(provider, "_call_with_retry", fake_call)

    result = await provider.call_llm([{"role": "user", "content": "hello"}])

    assert result == "ok from second"
    assert calls == ["openai/first", "openai/second"]


@pytest.mark.asyncio
async def test_call_llm_skips_cooling_down_candidate(monkeypatch):
    provider._failover.reset()
    models = [_model(1, "first", 10), _model(2, "second", 20)]
    calls = []

    async def route_models(group="default"):
        return models

    async def fake_call(messages, model, api_key, api_base, temperature, max_tokens, response_format, model_config, scene):
        calls.append(model)
        return f"ok from {model}"

    provider._failover.on_failure("db:1", cooldown_seconds=300)
    monkeypatch.setattr(provider._model_cache, "get_route_models", route_models)
    monkeypatch.setattr(provider, "_call_with_retry", fake_call)

    result = await provider.call_llm([{"role": "user", "content": "hello"}])

    assert result == "ok from openai/second"
    assert calls == ["openai/second"]


@pytest.mark.asyncio
async def test_call_llm_requires_enabled_db_route_models(monkeypatch):
    provider._failover.reset()

    async def route_models(group="default"):
        return []

    monkeypatch.setattr(provider._model_cache, "get_route_models", route_models)

    with pytest.raises(RuntimeError, match="No enabled LLM route models configured"):
        await provider.call_llm([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_llm_completion_calls_are_globally_bounded(monkeypatch):
    provider.reset_completion_semaphore()
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    class FakeMessage:
        content = "{}"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    async def fake_to_thread(func, **kwargs):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        async with lock:
            active -= 1
        return FakeResponse()

    async def fake_record_llm_call_in_new_session(**kwargs):
        return None

    monkeypatch.setattr(provider.settings, "LLM_WORKER_CONCURRENCY", 2)
    monkeypatch.setattr(provider.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(provider, "record_llm_call_in_new_session", fake_record_llm_call_in_new_session)

    try:
        await asyncio.gather(*[
            provider._call_llm_single(
                [{"role": "user", "content": f"hello {index}"}],
                "openai/test",
                "test-key",
                "https://example.test/v1",
                0.2,
                100,
                None,
                None,
                "test",
            )
            for index in range(5)
        ])

        assert max_active == 2
    finally:
        provider.reset_completion_semaphore()
