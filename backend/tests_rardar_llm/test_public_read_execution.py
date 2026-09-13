"""Disk-backed public reads must not monopolize the async request loop."""

import threading

import pytest
from fastapi import HTTPException, Response

from app.api.v1 import rardar
from app.services import rardar_trending


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["trending_today", "historical_hot", "trending_project", "historical_project"])
async def test_public_read_runs_off_event_loop(monkeypatch, name):
    monkeypatch.setattr(rardar, "is_rardar_product", lambda: True)
    loop_thread = threading.get_ident()
    seen = []

    def read(*args, **kwargs):
        seen.append((threading.get_ident(), args, kwargs))
        return {"ok": True}

    service = "today" if name == "trending_today" else "history" if name == "historical_hot" else "detail"
    monkeypatch.setattr(rardar_trending, service, read)
    args = (Response(),) if service != "detail" else ("project", "generation") if name == "trending_project" else ("project",)
    assert await getattr(rardar, name)(*args) == {"ok": True}
    assert seen[0][0] != loop_thread
    if name == "historical_project":
        assert seen[0][1:] == (("project", None), {"historical": True})


@pytest.mark.asyncio
async def test_invalid_public_read_remains_unavailable(monkeypatch):
    monkeypatch.setattr(rardar, "is_rardar_product", lambda: True)

    def invalid():
        raise ValueError("invalid saved facts")

    monkeypatch.setattr(rardar_trending, "today", invalid)
    with pytest.raises(HTTPException) as error:
        await rardar.trending_today(Response())
    assert error.value.status_code == 503
