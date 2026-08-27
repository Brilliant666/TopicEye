from __future__ import annotations

import base64

import httpx
import pytest

from app.services.rardar_project_evidence import clear_project_evidence_cache, collect_project_evidence


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_project_evidence_cache()


def _artifact_facts() -> dict:
    return {
        "description": "Artifact description",
        "pushedAt": "2026-08-27T00:00:00Z",
        "licenseSpdxId": "MIT",
        "primaryLanguage": "Python",
        "topics": ["agents"],
    }


@pytest.mark.asyncio
async def test_evidence_is_bounded_prioritizes_chinese_readme_and_caches() -> None:
    requests: list[str] = []
    readme = "# Fixture\n\n这是官方中文项目介绍，提供可组合的开发自动化能力。\n\n## Features\n\n- SDK\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/contents/README_ZH.md"):
            return httpx.Response(
                200,
                json={
                    "path": "README_ZH.md",
                    "encoding": "base64",
                    "content": base64.b64encode(readme.encode()).decode(),
                },
            )
        if request.url.path.endswith("/contents"):
            return httpx.Response(
                200,
                json=[
                    {"path": "src", "type": "dir"},
                    {"path": "pyproject.toml", "type": "file"},
                    {"path": "README_ZH.md", "type": "file"},
                    *({"path": f"extra-{index}", "type": "dir"} for index in range(120)),
                ],
            )
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(
                200,
                json={"name": "v1.2.0", "published_at": "2026-08-27T00:00:00Z", "body": "Stable release"},
            )
        return httpx.Response(
            200,
            json={
                "description": "Official English description",
                "language": "Python",
                "topics": ["agents"],
                "license": {"spdx_id": "MIT"},
                "pushed_at": "2026-08-27T00:00:00Z",
                "archived": False,
                "disabled": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        first = await collect_project_evidence("fixture/repository", _artifact_facts(), client=client)
        second = await collect_project_evidence("fixture/repository", _artifact_facts(), client=client)

    assert len(requests) == 4
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.digest == second.digest
    assert first.official_intro["sourceLabel"] == "官方介绍"
    assert first.official_intro["evidenceRefs"] == ["readme:introduction"]
    assert first.payload["readme"]["path"] == "README_ZH.md"
    assert first.path_refs["readme:introduction"] == "README_ZH.md"
    assert first.path_refs["readme:heading:1"] == "README_ZH.md#fixture"
    assert "/repos/fixture/repository/readme" not in requests
    assert len(first.payload["topLevelTree"]) == 100
    assert first.payload["collectionLimits"] == {
        "githubRequests": 4,
        "readmeChars": 12000,
        "treeItems": 100,
        "releaseCount": 1,
        "timeoutSeconds": 8,
    }
    assert "file:pyproject.toml" in first.allowed_refs
    assert "release:latest" in first.allowed_refs


@pytest.mark.asyncio
async def test_evidence_failures_keep_bounded_artifact_fallback() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        evidence = await collect_project_evidence("fixture/repository", _artifact_facts(), client=client)

    assert evidence.payload["description"] == "Artifact description"
    assert evidence.official_intro["sourceLabel"] == "官方介绍"
    assert evidence.expected_intro_label == "官方介绍（译）"
    assert evidence.official_intro["evidenceRefs"] == ["description"]
    assert evidence.allowed_refs == frozenset({"repository", "description", "license"})
