"""One reentrant OS writer lock for CLI and administrator Selection runs."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.services.llm.provider_budget import file_lock, plain

_held: ContextVar[str | None] = ContextVar("selection_writer", default=None)


@contextmanager
def selection_writer(target: Path):
    plain(target)
    identity = str(target.absolute())
    if _held.get() == identity:
        yield
        return
    with file_lock(target / ".selection-writer.lock", blocking=False):
        token = _held.set(identity)
        try:
            yield
        finally:
            _held.reset(token)
