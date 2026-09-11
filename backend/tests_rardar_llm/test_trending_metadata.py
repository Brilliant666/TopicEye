import json

import httpx
import pytest

from app.integrations.rardar import trending_metadata as metadata


def project():
    return {"repository": "owner/repo", "githubRepositoryId": 42, "totalStars": 123, "appearances": []}


def response():
    return {
        "id": 42,
        "full_name": "owner/repo",
        "language": "Python",
        "topics": ["tools"],
        "license": {"spdx_id": "MIT"},
    }


@pytest.mark.asyncio
async def test_metadata_without_profile_keeps_board_facts_and_reuses_cache(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        first = await metadata.refresh(tmp_path, [project()], client)
        second = await metadata.refresh(tmp_path, [project()], client)
    assert first["updated"] == second["reused"] == len(calls) == 1
    saved = metadata.apply({"projects": [project()]}, tmp_path)["projects"][0]
    assert saved["language"] == "Python" and saved["license"] == "MIT"
    assert saved["totalStars"] == 123 and saved["appearances"] == []
    assert saved["metadataSource"]["fetchedAt"]


@pytest.mark.parametrize("payload", [{}, [], {"repository": "owner/repo"}])
@pytest.mark.asyncio
async def test_corrupt_optional_cache_is_not_page_failure_and_can_be_repaired(tmp_path, payload):
    path = metadata._path(tmp_path, "owner/repo")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schemaVersion": 1, "payload": payload, "digest": metadata.digest(payload)}))
    assert metadata.apply({"projects": [project()]}, tmp_path)["projects"] == [project()]
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response()))
    ) as client:
        result = await metadata.refresh(tmp_path, [project()], client)
    assert result["updated"] == 1 and not result["failed"]


@pytest.mark.asyncio
async def test_identity_failure_is_local_and_unknown_license_not_invented(tmp_path):
    meta = response()
    meta["id"] = 43
    with pytest.raises(ValueError, match="identity"):
        metadata.save(tmp_path, project(), meta)
    meta["id"] = 42
    meta["license"]["spdx_id"] = "NOASSERTION"
    assert metadata.save(tmp_path, project(), meta)["license"] is None
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        result = await metadata.refresh(tmp_path, [project(), {"repository": "other/repo"}], client)
    assert result["reused"] == 1 and len(result["failed"]) == 1
    assert metadata.read(tmp_path, project())["language"] == "Python"
