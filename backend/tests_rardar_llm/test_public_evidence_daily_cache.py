"""Public evidence durability uses temporary files and a mocked GitHub only."""

import base64
import json

import httpx
import pytest

from app.services import rardar_project_evidence as evidence

FACTS = {"description": "Public fixture", "pushedAt": "2026-09-09T00:00:00Z", "licenseSpdxId": "MIT"}
BODY = "# Public tool\n\nRun Python tasks manually or on a schedule and inspect their logs."


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    root = tmp_path / "public-project-evidence"
    monkeypatch.setattr(evidence, "_persistent_root", lambda: root)
    evidence.clear_project_evidence_cache()
    yield root
    evidence.clear_project_evidence_cache()


async def collect(*, facts=None, body=BODY, refresh=False):
    def handler(request):
        assert request.url.host == "api.github.com"
        assert request.url.path == "/repos/fixture/public/readme"
        if body is None:
            return httpx.Response(503)
        return httpx.Response(
            200, json={"path": "README.md", "encoding": "base64", "content": base64.b64encode(body.encode()).decode()}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com") as client:
        return await evidence.collect_project_evidence(
            "fixture/public",
            facts or FACTS,
            client=client,
            include_readme_body=True,
            readme_only=True,
            refresh_material=refresh,
        )


@pytest.mark.asyncio
async def test_persisted_public_material_survives_process_cache_and_excludes_requirements(isolated):
    original = await collect(facts={**FACTS, "requirement": "PRIVATE USER REQUIREMENT", "prompt": "PRIVATE PROMPT"})
    managed = next(isolated.glob("*/managed.json"))
    saved = json.loads(managed.read_bytes())
    assert saved["repository"] == "fixture/public"
    assert saved["options"] == {"include_readme_body": True, "readme_only": True}
    assert set(saved["facts"]) == {"description", "pushedAt", "licenseSpdxId"}
    assert all("PRIVATE" not in path.read_text() for path in isolated.rglob("*.json"))
    evidence.clear_project_evidence_cache()
    # Any actual request would fail here, proving the persisted cache is used.
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("unexpected outbound"))
    ) as client:
        cached = await evidence.collect_project_evidence(
            "fixture/public", FACTS, client=client, include_readme_body=True, readme_only=True
        )
    assert cached.cache_hit
    assert cached.digest == original.digest
    assert cached.payload == original.payload


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["payload", "allowed_refs", "official_intro", "path_refs"])
async def test_tampered_material_or_reference_is_not_trusted(isolated, field):
    await collect()
    path = next(path for path in isolated.rglob("*.json") if path.name != "managed.json")
    saved = json.loads(path.read_bytes())
    if field == "payload":
        saved["evidence"][field]["description"] = "FORGED"
    elif field == "allowed_refs":
        saved["evidence"][field].append("forged-ref")
    elif field == "official_intro":
        saved["evidence"][field]["text"] = "FORGED"
    else:
        saved["evidence"][field]["repository"] = "../../FORGED"
    path.write_text(json.dumps(saved), encoding="utf-8")
    evidence.clear_project_evidence_cache()
    assert evidence._persisted_evidence("fixture/public", saved["revision"]) is None


@pytest.mark.asyncio
async def test_failed_refresh_preserves_healthy_persistent_material(isolated):
    original = await collect()
    before = {str(path): path.read_bytes() for path in isolated.rglob("*.json")}
    failed = await collect(body=None, refresh=True)
    assert failed.payload["readme"]["path"] is None
    assert before == {str(path): path.read_bytes() for path in isolated.rglob("*.json")}
    same_process = await collect(body=None)
    assert same_process.cache_hit and same_process.digest == original.digest
    evidence.clear_project_evidence_cache()
    recovered = await collect(body=None)
    assert recovered.cache_hit and recovered.digest == original.digest


@pytest.mark.asyncio
async def test_daily_entry_reads_managed_find_material_and_resumes_without_second_fetch(isolated, monkeypatch):
    from app.services import rardar_daily_operations as daily

    original = await collect()
    calls = []

    async def refresh(repository, facts, **options):
        calls.append((repository, facts, options))
        return original

    monkeypatch.setattr(evidence, "collect_project_evidence", refresh)
    progress = {}
    result = await daily._public_materials(progress, lambda: None)
    assert result["checked"] == 1 and result["updated"] == 1
    assert calls[0][0] == "fixture/public"
    assert calls[0][2]["refresh_material"] is True
    second = await daily._public_materials(progress, lambda: None)
    assert second["reused"] == 1 and len(calls) == 1


@pytest.mark.asyncio
async def test_symlink_cache_fails_closed(isolated, tmp_path):
    from app.services.llm.provider_budget import ProviderBudgetError

    isolated.mkdir()
    target = tmp_path / "elsewhere"
    target.mkdir()
    import hashlib

    link = isolated / hashlib.sha256(b"fixture/public").hexdigest()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(ProviderBudgetError):
        await collect()
    assert list(target.iterdir()) == []


@pytest.mark.asyncio
async def test_hardlinked_evidence_file_fails_closed(isolated, tmp_path):
    from app.services.llm.provider_budget import ProviderBudgetError

    await collect()
    path = next(path for path in isolated.rglob("*.json") if path.name != "managed.json")
    alias = tmp_path / "linked-evidence.json"
    try:
        alias.hardlink_to(path)
    except OSError:
        pytest.skip("hardlinks unavailable")
    saved = json.loads(path.read_bytes())
    original = alias.read_bytes()
    evidence.clear_project_evidence_cache()
    with pytest.raises(ProviderBudgetError, match="unsafe_path"):
        evidence._persisted_evidence("fixture/public", saved["revision"])
    assert alias.read_bytes() == original
