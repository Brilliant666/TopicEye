from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import llm_usage
from app.services.llm import _call_engine as engine
from app.services.rardar_llm_control import _map_control_error

FIND = "rardar_find_project_comparison"


def test_find_deadline_is_bounded_and_other_scenes_unchanged(monkeypatch):
    monkeypatch.setattr(engine.settings, "LLM_COMPLETION_TIMEOUT_SECONDS", 45)
    monkeypatch.setattr(engine.settings, "RARDAR_FIND_COMPLETION_TIMEOUT_SECONDS", 120)
    assert engine._completion_timeout_seconds(scene=FIND) == 45
    with engine.find_comparison_deadline():
        assert engine._completion_timeout_seconds(scene=FIND) == 120
        assert engine._completion_timeout_seconds(300, scene=FIND) == 120
        assert engine._completion_timeout_seconds(30, scene=FIND) == 30
        assert engine._completion_timeout_seconds(scene="rardar_news_quickread") == 45
    assert engine._completion_timeout_seconds(scene=FIND) == 45
    assert engine._completion_timeout_seconds(scene="rardar_news_quickread") == 45
    assert engine._completion_timeout_seconds(300) == 45


@pytest.mark.parametrize("value", [0, -1, 121, float("inf"), float("nan")])
def test_find_invalid_deadline_rejected(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RARDAR_FIND_COMPLETION_TIMEOUT_SECONDS=value)


@pytest.fixture
def isolated_engine(monkeypatch):
    limiter = SimpleNamespace(acquire=AsyncMock())
    monkeypatch.setattr(engine, "_rate_limiter", limiter)
    monkeypatch.setattr(engine, "_get_token_rate_limiter", lambda: limiter)
    monkeypatch.setattr(engine, "_get_model_rate_limiter", lambda _: None)
    monkeypatch.setattr(engine, "execution_budget", lambda _: None)
    monkeypatch.setattr(llm_usage, "record_llm_call_in_new_session", AsyncMock())

    @asynccontextmanager
    async def slot(*_args):
        yield

    monkeypatch.setattr(engine, "acquire_completion_slot", slot)
    monkeypatch.setattr(engine.settings, "RARDAR_FIND_COMPLETION_TIMEOUT_SECONDS", 0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["local", "sdk"])
async def test_find_timeout_cancels_or_classifies_and_never_retries(isolated_engine, monkeypatch, kind):
    calls = []
    cancelled = []

    async def completion(**kwargs):
        calls.append(kwargs)
        if kind == "sdk":
            raise httpx.ReadTimeout("sensitive text must not escape")
        try:
            await asyncio.sleep(20)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(engine, "acompletion", completion)
    with engine.find_comparison_deadline(), pytest.raises(engine.FindCompletionTimeout) as captured:
        await engine._call_with_retry([], "mock", None, None, 1, 100, None, scene=FIND)
    classification = "local_completion_deadline" if kind == "local" else "sdk_timeout"
    assert captured.value.classification == classification
    assert _map_control_error(captured.value).classification == classification
    assert len(calls) == 1
    assert calls[0]["timeout"] == 0.1
    assert calls[0]["num_retries"] == 0
    assert bool(cancelled) is (kind == "local")
    # Shared provider uses this same terminal predicate to stop failover.
    assert engine._is_deterministic_request_error(captured.value)
    assert not engine._should_retry(captured.value)


@pytest.mark.asyncio
async def test_external_cancellation_propagates(isolated_engine, monkeypatch):
    started = asyncio.Event()
    cancelled = []

    async def completion(**kwargs):
        started.set()
        try:
            await asyncio.sleep(20)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(engine, "acompletion", completion)
    task = asyncio.create_task(engine._call_with_retry([], "mock", None, None, 1, 100, None, scene=FIND))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled == [True]


def test_news_timeout_keeps_existing_retry_policy():
    assert engine._should_retry(TimeoutError("mock"))
