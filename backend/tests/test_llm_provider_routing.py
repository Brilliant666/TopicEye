from types import SimpleNamespace

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
