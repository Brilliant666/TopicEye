"""Inventory only public, validated identities; no network or model requests."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.rardar.serving_profiles import collect_official_project_profile
from app.services import rardar_managed_materials as inventory
from tests_rardar_selection.test_profile_cache_v2 import _handler, _project


async def seed(target):
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        await collect_official_project_profile(
            _project(),
            "fixture",
            target / "selection-profile-cache",
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )
    return next((target / "selection-profile-cache/profile-store/v2").glob("*/*.json"))


@pytest.mark.asyncio
async def test_retained_profile_is_read_without_current_observation(tmp_path):
    path = await seed(tmp_path)
    original = path.read_bytes()
    result = inventory.inventory_managed_materials(tmp_path)
    assert [item["repository"] for item in result["projects"]] == [_project().repository]
    assert result["invalidCacheRecords"] == 0
    assert "totalStars" not in str(result)
    assert path.read_bytes() == original


@pytest.mark.asyncio
async def test_tampered_record_is_local_failure(tmp_path):
    path = await seed(tmp_path)
    saved = json.loads(path.read_bytes())
    saved["profile"]["repository"] = "forged/repository"
    path.write_text(json.dumps(saved), encoding="utf-8")
    result = inventory.inventory_managed_materials(tmp_path)
    assert result["projects"] == []
    assert result["invalidCacheRecords"] == 1
    assert result["unresolvedProjectCount"] == 0


@pytest.mark.asyncio
async def test_filename_identity_mismatch_is_rejected(tmp_path):
    path = await seed(tmp_path)
    path.rename(path.with_name("0" * 64 + ".json"))
    result = inventory.inventory_managed_materials(tmp_path)
    assert result["projects"] == []
    assert result["invalidCacheRecords"] == 1


def test_validated_current_members_remain_managed_and_conflicts_are_local(tmp_path, monkeypatch):
    def candidate(identifier, repository):
        return SimpleNamespace(
            candidate=SimpleNamespace(githubRepositoryId=identifier, repository=repository, description="public")
        )

    artifact = SimpleNamespace(
        assessments=[candidate(1, "old/name"), candidate(1, "new/name"), candidate(2, "safe/project")]
    )
    monkeypatch.setattr(
        inventory, "SelectionServingLoader", lambda _: SimpleNamespace(validate_generation=lambda: artifact)
    )
    result = inventory.inventory_managed_materials(tmp_path)
    assert [item["repository"] for item in result["projects"]] == ["safe/project"]
    assert result["unresolvedProjectCount"] == 2
    assert result["invalidCacheRecords"] == 0
