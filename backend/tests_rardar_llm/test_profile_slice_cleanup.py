"""Cooperative yields drain profile collection before a work slice returns."""

import asyncio
from types import SimpleNamespace

import pytest

from app.integrations.rardar import serving_profiles
from app.services.llm.daily_provider_budget import ProviderWorkYield


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_owner", [False, True])
async def test_profile_slice_drains_siblings_before_closing_client(monkeypatch, tmp_path, cancel_owner):
    started = asyncio.Event()
    blocked = asyncio.Event()
    cleaned = asyncio.Event()
    calls = []

    class Client:
        closed = False

        async def aclose(self):
            assert cleaned.is_set()
            self.closed = True

    client = Client()
    monkeypatch.setattr(serving_profiles.httpx, "AsyncClient", lambda **kwargs: client)

    async def collect(project, *args, **kwargs):
        calls.append(project.githubRepositoryId)
        if project.githubRepositoryId == 1:
            await started.wait()
            if not cancel_owner:
                raise ProviderWorkYield("work_slice_exhausted")
            await blocked.wait()
        started.set()
        try:
            await blocked.wait()
        finally:
            await asyncio.sleep(0)
            assert not client.closed
            cleaned.set()

    monkeypatch.setattr(serving_profiles, "collect_official_project_profile", collect)
    projects = [SimpleNamespace(githubRepositoryId=i, rank=i) for i in (1, 2, 3)]
    task = asyncio.create_task(serving_profiles.build_official_profiles(projects, "fixed", tmp_path, concurrency=2))
    await started.wait()
    if cancel_owner:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel_owner else ProviderWorkYield):
        await task
    assert cleaned.is_set()
    assert client.closed
    assert not list(tmp_path.iterdir())  # no negative-cache artifact for a yield
    snapshot = list(calls)
    await asyncio.sleep(0)
    assert calls == snapshot  # no detached collector survives the operation
