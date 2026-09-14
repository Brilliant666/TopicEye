from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from tenacity import wait_none

from app.services import llm_usage
from app.services.llm import _call_engine as engine, daily_provider_budget as daily, provider
from app.services.llm.find_operation import active_find_operation, find_operation
from app.services.llm.provider_budget import ProviderBudgetError


@pytest.fixture
def dispatch(monkeypatch):
    limiter = SimpleNamespace(acquire=AsyncMock())
    monkeypatch.setattr(engine, "_rate_limiter", limiter)
    monkeypatch.setattr(engine, "_get_token_rate_limiter", lambda: limiter)
    monkeypatch.setattr(engine, "_get_model_rate_limiter", lambda _: None)
    monkeypatch.setattr(engine, "execution_budget", lambda _: None)
    monkeypatch.setattr(engine, "daily_execution_budget", AsyncMock(return_value=None))
    monkeypatch.setattr(engine.settings, "RARDAR_DAILY_OPERATIONS_ENABLED", False)
    monkeypatch.setattr(provider, "_litellm_extra_kwargs", lambda _: {"num_retries": 9})
    monkeypatch.setattr(llm_usage, "record_llm_call_in_new_session", AsyncMock())
    monkeypatch.setattr(llm_usage, "extract_usage", lambda _: SimpleNamespace())

    @asynccontextmanager
    async def slot(*_args):
        yield

    monkeypatch.setattr(engine, "acquire_completion_slot", slot)
    calls = []

    async def completion(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"result":true}'))])

    monkeypatch.setattr(engine, "acompletion", completion)
    return calls


async def call(scene="rardar_find_project_comparison", response_format=None):
    return await engine._call_llm_single([], "mock", None, None, 0.3, 100, response_format, scene=scene)


@pytest.mark.asyncio
async def test_stages_formats_and_concurrent_tasks_share_one_limit(dispatch):
    reserved = []

    async def reserve(metadata):
        await asyncio.sleep(0)
        reserved.append(metadata)

    with find_operation(run_id="run-one", request_limit=3, reserve=reserve) as state:
        # Simulate plan + comparison formats + route attempts, all at the real
        # provider dispatch boundary rather than counting high-level functions.
        results = await asyncio.gather(
            call("rardar_find_query_plan"),
            call(response_format={"type": "json_object"}),
            call(),
            call(),
            call(),
            return_exceptions=True,
        )
    assert len(dispatch) == len(reserved) == state.requests_reserved == 3
    assert state.dispatched == state.completed == 3
    assert state.failed == 0
    assert sum(isinstance(item, ProviderBudgetError) for item in results) == 2
    assert all(item["num_retries"] == 0 for item in dispatch)
    assert reserved[0]["scene"] == "rardar_find_query_plan"
    assert all(item["accounting"] == "reserved_before_http" for item in reserved)
    assert set(reserved[0]) == {"runId", "scene", "model", "dailyRunId", "dailyTaskId", "stage", "accounting"}
    assert not active_find_operation()


@pytest.mark.asyncio
async def test_real_retry_wrapper_cannot_exceed_shared_cap(dispatch, monkeypatch):
    async def failing(**kwargs):
        dispatch.append(kwargs)
        raise RuntimeError("temporary simulated transport failure")

    monkeypatch.setattr(engine, "acompletion", failing)
    retry_call = engine._call_with_retry.retry_with(wait=wait_none())
    reserve = AsyncMock()
    with (
        find_operation(run_id="retry", request_limit=1, reserve=reserve) as state,
        pytest.raises(ProviderBudgetError, match="find_run_request_limit"),
    ):
        await retry_call([], "mock", None, None, 0.3, 100, None, scene="rardar_find_project_comparison")
    assert len(dispatch) == reserve.await_count == state.failed == state.dispatched == 1
    assert state.completed == 0


@pytest.mark.asyncio
async def test_zero_allowance_read_or_cache_does_not_reserve_and_dispatch_stops(dispatch):
    reserve = AsyncMock()
    with find_operation(run_id="cached", request_limit=0, reserve=reserve) as state:
        assert state.requests_reserved == 0  # GET/cache paths never enter the engine.
        with pytest.raises(ProviderBudgetError, match="find_run_request_limit"):
            await call()
    assert not dispatch
    reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_daily_exhaustion_precedes_run_reservation(dispatch, monkeypatch, tmp_path):
    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")
    ledger = daily.daily_ledger(1)
    with ledger.execution("find_project"):
        pass
    monkeypatch.setattr(engine, "daily_execution_budget", AsyncMock(return_value=(ledger, "find_project")))
    reserve = AsyncMock()
    with (
        find_operation(run_id="limited", request_limit=4, reserve=reserve) as state,
        pytest.raises(ProviderBudgetError, match="exhausted"),
    ):
        await call()
    assert state.requests_reserved == state.dispatched == 0
    assert not dispatch
    reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_db_failure_stops_http_without_refund_and_is_not_retried(dispatch, monkeypatch, tmp_path):
    monkeypatch.setattr(daily, "daily_root", lambda: tmp_path / "daily")
    ledger = daily.daily_ledger(100)
    monkeypatch.setattr(engine, "daily_execution_budget", AsyncMock(return_value=(ledger, "find_project")))
    reserve = AsyncMock(side_effect=RuntimeError("sensitive DB error must not escape"))
    with (
        find_operation(run_id="db-fail", request_limit=4, reserve=reserve) as state,
        pytest.raises(ProviderBudgetError, match="find_run_reservation_failed") as error,
    ):
        await call()
    assert not engine._should_retry(error.value)
    assert state.requests_reserved == 1
    assert state.dispatched == state.completed == state.failed == 0
    assert not dispatch
    assert ledger.snapshot()["reserved"] == 1  # Conservative reservation, not proof of HTTP.
    assert reserve.call_args.args[0]["dailyRunId"] == ledger.run_id


@pytest.mark.asyncio
async def test_context_isolation_non_find_call_unchanged(dispatch):
    reserve = AsyncMock()
    with find_operation(run_id="zero", request_limit=0, reserve=reserve):
        pass
    assert await call("general") == '{"result":true}'
    assert len(dispatch) == 1
    assert dispatch[0]["num_retries"] == 9  # Existing non-budgeted model policy remains untouched.
    reserve.assert_not_awaited()


@pytest.mark.asyncio
async def test_returned_but_unusable_response_is_not_transport_unknown(dispatch, monkeypatch):
    monkeypatch.setattr(engine, "acompletion", AsyncMock(return_value=SimpleNamespace(choices=[])))
    with (
        find_operation(run_id="bad-response", request_limit=1, reserve=AsyncMock()) as state,
        pytest.raises(IndexError),
    ):
        await call()
    assert state.dispatched == state.completed == 1
    assert state.failed == 0  # Response received; later validation is a separate business failure.


@pytest.mark.asyncio
async def test_association_uses_dispatch_day_after_wait_not_initial_day(dispatch, monkeypatch):
    current = (SimpleNamespace(run_id="daily-current", task_id="daily"), "find_project")

    @asynccontextmanager
    async def waited(*args, **kwargs):
        yield current

    monkeypatch.setattr(engine, "managed_budget_execution", waited)
    reserve = AsyncMock()
    with find_operation(run_id="cross-day", request_limit=1, reserve=reserve):
        await call()
    assert reserve.call_args.args[0]["dailyRunId"] == "daily-current"


@pytest.mark.asyncio
async def test_swallowed_plan_reservation_failure_still_stops_comparison(dispatch):
    reserve = AsyncMock(side_effect=RuntimeError("commit unknown"))
    with find_operation(run_id="no-fallback-spend", request_limit=8, reserve=reserve):
        for _phase in ("plan", "comparison"):
            with pytest.raises(ProviderBudgetError, match="find_run_reservation_failed"):
                await call()
    assert reserve.await_count == 1
    assert not dispatch


@pytest.mark.asyncio
@pytest.mark.parametrize("status,known", [(400, 1), (401, 1), (429, 1), (500, 1), (408, 0), (None, 0)])
async def test_explicit_http_failure_is_settled_except_timeout(dispatch, monkeypatch, status, known):
    error = RuntimeError("simulated transport failure")
    error.status_code = status
    monkeypatch.setattr(engine, "acompletion", AsyncMock(side_effect=error))
    with (
        find_operation(run_id="http-failure", request_limit=1, reserve=AsyncMock()) as state,
        pytest.raises(RuntimeError),
    ):
        await call()
    assert state.dispatched == state.failed == 1
    assert state.completed == 0
    assert state.known_failed == known


@pytest.mark.asyncio
async def test_timeout_exception_is_unknown_even_if_sdk_supplies_status(dispatch, monkeypatch):
    error = TimeoutError("simulated deadline")
    error.status_code = 504
    monkeypatch.setattr(engine, "acompletion", AsyncMock(side_effect=error))
    with (
        find_operation(run_id="timeout", request_limit=1, reserve=AsyncMock()) as state,
        pytest.raises(TimeoutError),
    ):
        await call()
    assert state.dispatched == state.failed == 1
    assert state.completed == state.known_failed == 0
