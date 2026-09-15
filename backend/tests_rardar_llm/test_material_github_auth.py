"""Synthetic HTTP transport only: no source or Provider requests."""

from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.services import rardar_github_client, rardar_trending as service
from tests_rardar_llm.test_material_work_allowance import work  # noqa: F401


@pytest.fixture
def transport(monkeypatch):
    seen = []
    original = httpx.AsyncClient

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={})

    monkeypatch.setattr(
        rardar_github_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("value,expected", [("", None), ("   ", None), (" synthetic-token ", "Bearer synthetic-token")])
async def test_public_api_auth_and_secret_redaction(transport, value, expected):
    async with rardar_github_client.github_material_client(SecretStr(value)) as client:
        assert client.follow_redirects is False
        assert client.trust_env is False
        assert client.timeout.read == 12
        response = await client.get("/repos/owner/project")
        assert response.status_code == 200
    assert transport[0].headers.get("Authorization") == expected
    assert transport[0].headers["User-Agent"] == "TopicEye-Rardar/2.0"
    assert "synthetic-token" not in repr(transport[0].headers)
    config = Settings(_env_file=None, GITHUB_TOKEN=value)
    assert "synthetic-token" not in repr(config)
    assert "synthetic-token" not in config.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/repos/owner/project",
        "https://api.github.com.evil.test/repos/owner/project",
        "http://api.github.com/repos/owner/project",
        "https://api.github.com:444/repos/owner/project",
        "https://user:password@api.github.com/repos/owner/project",
    ],
)
async def test_foreign_or_credentialed_origin_refused_before_network(transport, url):
    async with rardar_github_client.github_material_client(SecretStr("synthetic-token")) as client:
        with pytest.raises(ValueError, match="^rardar_github_origin_not_allowed$"):
            await client.get(url)
    assert transport == []


def test_invalid_credential_error_does_not_include_secret():
    with pytest.raises(ValueError, match="^rardar_github_token_invalid$"):
        rardar_github_client.github_material_client(SecretStr("synthetic\nsecret"))


@pytest.mark.asyncio
async def test_metadata_entry_uses_project_token(transport, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", SecretStr("synthetic-token"))

    async def refresh(_target, _projects, client):
        await client.get("/repos/current/one")
        return {"unchanged": True}

    monkeypatch.setattr(service.trending_metadata, "refresh", refresh)
    assert await service.refresh_metadata(tmp_path, []) == {"unchanged": True}
    assert transport[0].headers["Authorization"] == "Bearer synthetic-token"


@pytest.mark.asyncio
async def test_material_entry_uses_project_token_without_changing_allowance(work, transport, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "GITHUB_TOKEN", SecretStr("synthetic-token"))

    async def collect(_target, project, _generation, client, _route):
        await client.get(f"/repos/{project['repository']}")
        return SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")

    monkeypatch.setattr(service, "_collect_project_material", collect)
    result = await service.historical_work(work.target, {}, lambda: None, only_project_id=work.projects[0]["projectId"])
    assert result["processed"] == 1
    assert result["providerRequests"] == 0
    assert len(transport) == 1
    assert transport[0].headers["Authorization"] == "Bearer synthetic-token"


@pytest.mark.asyncio
async def test_redirect_default_and_override_cannot_leak_credential(monkeypatch):
    seen = []
    original = httpx.AsyncClient

    def redirect(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://foreign.example/private"})

    monkeypatch.setattr(
        rardar_github_client.httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(redirect)),
    )
    async with rardar_github_client.github_material_client(SecretStr("synthetic-token")) as client:
        assert (await client.get("/repos/current/one")).status_code == 302
        with pytest.raises(ValueError, match="^rardar_github_origin_not_allowed$"):
            await client.get("/repos/current/one", follow_redirects=True)
    assert len(seen) == 2
    assert all(request.url.host == "api.github.com" for request in seen)
