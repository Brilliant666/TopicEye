"""A durable Find run's dispatch hook, not another provider budget ledger.

The service owns identity, transaction boundaries and atomic persistent limits.
This context survives phase/route retries and is inherited by child asyncio tasks.
Reservations are never refunded: cancellation between commit and HTTP is uncertain.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from app.services.llm.provider_budget import ProviderBudgetError


@dataclass
class FindOperation:
    run_id: str
    request_limit: int
    reserve: Callable[[dict], Awaitable[None]]
    requests_reserved: int = 0
    dispatched: int = 0
    completed: int = 0
    failed: int = 0
    known_failed: int = 0
    stopped_code: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_active: ContextVar[FindOperation | None] = ContextVar("find_durable_operation", default=None)


@contextmanager
def find_operation(*, run_id: str, request_limit: int, reserve, requests_reserved: int = 0):
    """Bind server-saved bounds; never accept these values directly from a client."""
    if request_limit < 0 or requests_reserved < 0 or requests_reserved > request_limit:
        raise ValueError("invalid Find operation request bounds")
    if _active.get() is not None:
        raise ProviderBudgetError("find_operation_context_already_bound")
    state = FindOperation(run_id, request_limit, reserve, requests_reserved)
    token = _active.set(state)
    try:
        yield state
    finally:
        _active.reset(token)


def active_find_operation() -> bool:
    return _active.get() is not None


def find_request_event(event: str) -> None:
    """Transport-level counters only; completed does not imply valid business output."""
    state = _active.get()
    if state is not None:
        if event not in {"dispatched", "completed", "failed", "known_failed"}:
            raise ValueError("invalid Find request event")
        setattr(state, event, getattr(state, event) + 1)


@asynccontextmanager
async def find_request_admission():
    """Serialize this run only, before daily accounting, including concurrent phases."""
    state = _active.get()
    if state is None:
        yield
        return
    async with state.lock:
        if state.stopped_code is not None:
            raise ProviderBudgetError(state.stopped_code)
        if state.requests_reserved >= state.request_limit:
            raise ProviderBudgetError("find_run_request_limit")
        yield


async def reserve_find_request(*, scene: str, model: str, daily) -> None:
    """Called after daily admission and immediately before HTTP; failures fail closed.

    Daily reservations can conservatively exceed HTTP dispatches if DB commit fails.
    Neither a daily 'dispatched' event nor this reservation proves an HTTP response.
    The callback must commit its atomic counter before returning.
    """
    state = _active.get()
    if state is None:
        return
    metadata = {
        "runId": state.run_id,
        "scene": scene,
        "model": model,
        "dailyRunId": daily[0].run_id if daily else None,
        "dailyTaskId": daily[0].task_id if daily else None,
        "stage": daily[1] if daily else scene,
        "accounting": "reserved_before_http",
    }
    # Retain the local cap even when a DB acknowledgement is lost. The service
    # marks this run uncertain/failed and must not auto-resume paid execution.
    state.requests_reserved += 1
    try:
        await state.reserve(metadata)
    except ProviderBudgetError as exc:
        state.stopped_code = exc.code
        raise
    except Exception:
        state.stopped_code = "find_run_reservation_failed"
        raise ProviderBudgetError("find_run_reservation_failed") from None
