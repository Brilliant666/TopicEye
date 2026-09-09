"""Exact Profile identity reuse across the two known local cache roots."""

import json

import httpx
import pytest

from app.integrations.rardar.profile_cache_v2 import (
    ProfileCacheIdentityV2,
    ProfileCacheIntegrityError,
    load_profile_store,
)
from app.integrations.rardar.serving_profiles import collect_official_project_profile
from tests_rardar_selection.test_profile_cache_v2 import _handler, _project


async def seeded(root):
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        await collect_official_project_profile(
            _project(),
            "fixture",
            root,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )
    path = next((root / "profile-store/v2").glob("*/*.json"))
    identity = ProfileCacheIdentityV2.model_validate_json(
        json.dumps(json.loads(path.read_bytes())["cacheIdentity"]), strict=True
    )
    return path, identity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,destination", [("profile-cache", "selection-profile-cache"), ("selection-profile-cache", "profile-cache")]
)
async def test_exact_identity_cross_module_read_is_zero_model_and_read_only(tmp_path, source, destination):
    path, identity = await seeded(tmp_path / source)
    original = path.read_bytes()
    value = load_profile_store(tmp_path / destination, identity)
    assert value is not None and value.cacheIdentity == identity
    assert path.read_bytes() == original
    assert not (tmp_path / destination).exists()

    async def forbidden(*_args, **_kwargs):
        pytest.fail("cross-module compatible Profile must not call a model")

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        reused = await collect_official_project_profile(
            _project(),
            "fixture",
            tmp_path / destination,
            client=client,
            translate=True,
            translator=forbidden,
            narrative_translator=forbidden,
            positioning_translator=forbidden,
            model_route_identity="a" * 64,
        )
    assert reused.profile_cache_state in {"hit", "rebound"}
    assert reused.translation_calls == 0
    assert path.read_bytes() == original


@pytest.mark.asyncio
async def test_changed_identity_and_arbitrary_root_do_not_reuse(tmp_path):
    _path, identity = await seeded(tmp_path / "profile-cache")
    assert (
        load_profile_store(
            tmp_path / "selection-profile-cache", identity.model_copy(update={"identityDigest": "b" * 64})
        )
        is None
    )
    assert load_profile_store(tmp_path / "unrelated", identity) is None


@pytest.mark.asyncio
async def test_corrupt_sibling_is_rejected_not_returned_as_cache_miss(tmp_path):
    path, identity = await seeded(tmp_path / "profile-cache")
    saved = json.loads(path.read_bytes())
    saved["profile"]["repository"] = "forged/project"
    path.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(ProfileCacheIntegrityError):
        load_profile_store(tmp_path / "selection-profile-cache", identity)


@pytest.mark.asyncio
async def test_selection_input_fingerprint_observes_only_allowed_sibling_store(tmp_path):
    from app.integrations.rardar.selection import selection_input_digest
    from tests_rardar_selection.test_selection import _source

    target, source = _source(tmp_path / "source")
    cache_root = target / "selection-profile-cache"

    def fingerprint():
        return selection_input_digest(source, cache_root=cache_root, model_route_identity="a" * 64, recall_limit=48)

    before = fingerprint()
    path, _identity = await seeded(target / "profile-cache")
    added_profile = fingerprint()
    assert added_profile != before
    unrelated = target / "profile-cache" / "other-model-results.json"
    unrelated.write_text('{"unrelated":true}', encoding="utf-8")
    assert fingerprint() == added_profile
    path.unlink()
    assert fingerprint() == before
