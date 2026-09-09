"""Opt-in, single-run stop signal; it never allocates or replenishes a budget."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from app.services.llm.provider_budget import ProviderBudgetError


@dataclass
class RunFailureGuard:
    failures: int = 0
    consecutive: int = 0
    failure_code: str | None = None
    stopped: bool = False
    response_cache_hit: bool = False


_active: ContextVar[RunFailureGuard | None] = ContextVar("selection_run_failure_guard", default=None)


@contextmanager
def run_failure_guard():
    guard = RunFailureGuard()
    token = _active.set(guard)
    try:
        yield guard
    finally:
        _active.reset(token)


def before_attempt() -> int:
    guard = _active.get()
    if guard is not None and guard.stopped:
        raise ProviderBudgetError("provider_operation_consecutive_failures")
    if guard is not None:
        guard.response_cache_hit = False
    return guard.failures if guard is not None else 0


def response_received(*, cache_hit: bool) -> None:
    guard = _active.get()
    if guard is not None:
        guard.response_cache_hit = cache_hit


def failed(kind: str, *, since: int | None = None) -> None:
    guard = _active.get()
    if guard is None or guard.stopped or (since is not None and (guard.failures != since or guard.response_cache_hit)):
        return
    # Callers pass stable codes, never exception strings or response bodies.
    category = (
        "timeout"
        if "timeout" in kind
        else "structure"
        if any(part in kind for part in ("json", "schema", "empty", "format", "structure"))
        or kind in {"unknown_field", "missing_required_field", "invalid_enum", "wrong_field_type", "missing_content"}
        else "evidence"
        if any(part in kind for part in ("evidence", "alias", "unsupported"))
        else "transport"
        if kind == "transport"
        else "validation"
    )
    guard.failures += 1
    guard.consecutive = guard.consecutive + 1 if category == guard.failure_code else 1
    guard.failure_code = category
    guard.stopped = guard.consecutive >= 2


def succeeded(*, cache_hit: bool = False) -> None:
    guard = _active.get()
    if guard is not None and not guard.stopped and not cache_hit and not guard.response_cache_hit:
        guard.consecutive = 0
        guard.failure_code = None
