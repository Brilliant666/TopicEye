"""One local news writer across web operations and the existing CLIs."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.core.config import settings
from app.services.llm.provider_budget import file_lock, plain

_owned: ContextVar[bool] = ContextVar("news_writer_owned", default=False)


def operation_root() -> Path:
    # Separate databases cannot interfere, and credentials never enter state.
    database_key = hashlib.sha256(settings.DATABASE_URL.encode()).hexdigest()[:20]
    home = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state"))
    root = home / "TopicEye" / "news-operations" / database_key
    plain(root, missing=True)
    return root


@contextmanager
def news_writer():
    if _owned.get():
        yield
        return
    root = operation_root()
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / "writer.lock", blocking=False):
        token = _owned.set(True)
        try:
            yield
        finally:
            _owned.reset(token)
