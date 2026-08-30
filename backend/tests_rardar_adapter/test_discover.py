from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://adapter:adapter@127.0.0.1:5432/adapter")

from app.api.v1 import rardar as rardar_api
from app.integrations.rardar.adapter import RardarArtifactError, _SafeRoot
from app.integrations.rardar.discover import DISCOVER_ROOT, DiscoverArtifactAdapter
from app.integrations.rardar.discover_serving import (
    DiscoverServingError,
    DiscoverServingLoader,
    build_discover_serving,
    clear_discover_serving_cache,
    install_discover_serving,
)
from app.integrations.rardar.discover_sync import sync_discover_intelligence
from app.integrations.rardar.serving_profiles import CollectedProjectProfile, ProfileBuildResult
from app.integrations.rardar.serving_schemas import (
    OfficialProjectProfile,
    ProjectEvidenceProjection,
    ServingCapability,
)
from app.services import rardar_intelligence

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_discover"


def _copy_fixture(tmp_path: Path, name: str = "source") -> Path:
    root = tmp_path / name
    shutil.copytree(FIXTURE / "artifacts", root / "artifacts")
    return root


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _complete_profiles(projects, generation_id: str, _cache_root: Path) -> ProfileBuildResult:
    profiles: dict[int, CollectedProjectProfile] = {}
    for project in projects:
        identity = f"{project.repository} 是一个具有明确仓库身份的开源项目。"
        positioning = "通过可验证的仓库证据提供自动化能力与可复用组件。"
        capability = ServingCapability(
            title="证据驱动能力",
            detail="根据仓库描述与文档整理可验证的核心功能。",
            shortDetail="整理可验证功能",
            evidenceRefs=["readme:section:1"],
            sourceMode="rardar_derived",
        )
        evidence_payload = {
            "schemaVersion": 1,
            "githubRepositoryId": project.githubRepositoryId,
            "repository": project.repository,
            "generationId": generation_id,
            "readmePath": "README.md",
            "readmeBlobSha": "a" * 40,
            "sourceLanguage": "zh",
            "selectedSections": [],
            "originalExcerpts": ["经过验证的项目说明与核心能力。"],
            "topLevelTree": [],
            "evidenceIndex": {
                "repository": "官方 GitHub 仓库身份",
                "description": project.description or "经过验证的项目说明。",
                "readme:section:1": "项目通过可复用组件提供自动化能力。",
            },
            "pathRefs": {},
        }
        evidence_payload["digest"] = hashlib.sha256(_canonical(evidence_payload)).hexdigest()
        evidence = ProjectEvidenceProjection.model_validate(evidence_payload, strict=True)
        profile_payload = {
            "profileSchemaVersion": "rardar-project-profile-v7",
            "promptVersion": "rardar-project-profile-zh-v15",
            "githubRepositoryId": project.githubRepositoryId,
            "repository": project.repository,
            "htmlUrl": str(project.htmlUrl),
            "generationId": generation_id,
            "profileState": "complete",
            "officialSummaryZh": identity,
            "sourceLabel": "Rardar 整理",
            "sourceLanguage": "zh",
            "capabilityBulletsZh": [capability.detail],
            "capabilities": [capability.model_dump(mode="json")],
            "productFormsZh": ["开源项目"],
            "supportedEnvironmentsZh": ["开发环境"],
            "primaryUseCasesZh": ["工程复用"],
            "deliveryFormsZh": ["源代码"],
            "claimEvidenceRefs": {
                identity: ["description"],
                positioning: ["readme:section:1"],
            },
            "readmePath": "README.md",
            "readmeBlobSha": "a" * 40,
            "selectedSections": [],
            "originalExcerpts": ["经过验证的项目说明与核心能力。"],
            "startHere": [],
            "evidenceDigest": evidence.digest,
            "generatedAt": (project.pushedAt or datetime(2026, 8, 30, tzinfo=UTC)).isoformat(),
            "translationState": "not_needed",
            "identitySummaryZh": identity,
            "coreValueZh": None,
            "coreValueEvidenceRefs": [],
            "keyDifferentiators": [],
            "qualityState": "partial",
            "qualityIssues": ["assessment_missing"],
            "officialTaglineZh": identity,
            "officialTaglineEvidenceRefs": ["description"],
            "officialPositioningZh": positioning,
            "officialPositioningEvidenceRefs": ["readme:section:1"],
            "positioningZh": positioning,
            "positioningSourceMode": "rardar_derived",
            "positioningEvidenceRefs": ["readme:section:1"],
            "positioningIncludedRoles": ["identity", "core_mechanism"],
            "positioningExcludedClauses": [],
            "officialHighlights": [],
            "officialNarrativeMode": "rardar_derived",
            "officialNarrativeIssues": ["source_structure_weak"],
            "officialNarrativePromptVersion": "rardar-official-narrative-zh-v2",
            "rardarAssessmentZh": None,
            "rardarAssessmentEvidenceRefs": [],
            "rardarDifferentiators": [],
            "rardarAssessmentPromptVersion": "rardar-assessment-zh-v12",
        }
        profile = OfficialProjectProfile.model_validate_json(_canonical(profile_payload), strict=True)
        profiles[project.githubRepositoryId] = CollectedProjectProfile(
            profile=profile,
            evidence=evidence,
            github_requests=0,
            readme_cache_hit=True,
            translation_calls=0,
            translation_cache_hit=True,
        )
    return ProfileBuildResult(
        profiles=profiles,
        github_requests=0,
        readme_cache_hits=len(profiles),
        translation_calls=0,
        translation_cache_hits=len(profiles),
    )


def test_discover_adapter_recomputes_stages_sources_and_today_exclusion(tmp_path: Path) -> None:
    loaded = DiscoverArtifactAdapter.from_config(str(_copy_fixture(tmp_path).resolve())).load()

    assert loaded.board.policyVersion == "trending-discover-v1"
    assert loaded.board.stageCounts.model_dump() == {"justDiscovered": 2, "rising": 2, "nearValidation": 1}
    assert loaded.board.coverage.excludedExactCount == 1
    assert loaded.board.coverage.sourceCaptureCount == 14
    assert [item.githubRepositoryId for item in loaded.board.nearValidation] == [2]
    assert set(loaded.projects) == {2, 3, 4, 8, 11}
    assert all(item.observedWindowHours <= 26 for item in loaded.board.justDiscovered + loaded.board.rising)


@pytest.mark.parametrize("case", ["manifest", "source", "today", "order"])
def test_discover_adapter_fails_closed_on_integrity_or_recomputation_damage(tmp_path: Path, case: str) -> None:
    root = _copy_fixture(tmp_path)
    store = root.joinpath(*DISCOVER_ROOT.split("/"))
    pointer = json.loads((store / "current.json").read_text(encoding="utf-8"))
    generation = store / "generations" / pointer["generationId"]
    if case == "manifest":
        (generation / "manifest.json").write_bytes((generation / "manifest.json").read_bytes() + b" ")
    elif case == "source":
        (generation / "sources" / "capture-01.json").write_bytes(
            (generation / "sources" / "capture-01.json").read_bytes() + b" "
        )
    elif case == "today":
        (generation / "sources" / "today-explosion.json").write_bytes(
            (generation / "sources" / "today-explosion.json").read_bytes() + b" "
        )
    else:
        artifact = generation / "discover.json"
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        payload["stages"]["rising"].reverse()
        payload["payloadDigest"]["value"] = hashlib.sha256(
            _canonical({key: value for key, value in payload.items() if key != "payloadDigest"})
        ).hexdigest()
        artifact.write_bytes(_canonical(payload))
        manifest_path = generation / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["discover.json"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest_path.write_bytes(_canonical(manifest))
        pointer["manifestSha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        (store / "current.json").write_bytes(_canonical(pointer))
    with pytest.raises(RardarArtifactError) as error:
        DiscoverArtifactAdapter.from_config(str(root.resolve())).load()
    assert error.value.code == "rardar_discover_invalid"


def test_discover_adapter_rejects_same_length_mutation_and_symlink(tmp_path: Path, monkeypatch) -> None:
    root = _copy_fixture(tmp_path / "mutation")
    original = _SafeRoot._read_open_file
    calls = 0

    def mutate(path: Path, maximum_bytes: int):
        nonlocal calls
        result = original(path, maximum_bytes)
        calls += 1
        if calls == 1:
            raw = path.read_bytes()
            path.write_bytes(raw.replace(b"20260830T002000000000Z", b"20260830T002000000001Z", 1))
        return result

    monkeypatch.setattr(_SafeRoot, "_read_open_file", staticmethod(mutate))
    with pytest.raises(RardarArtifactError):
        DiscoverArtifactAdapter.from_config(str(root.resolve())).load()

    linked = _copy_fixture(tmp_path / "symlink")
    store = linked.joinpath(*DISCOVER_ROOT.split("/"))
    pointer = store / "current.json"
    target = pointer.with_name("real-current.json")
    target.write_bytes(pointer.read_bytes())
    pointer.unlink()
    try:
        pointer.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(RardarArtifactError):
        DiscoverArtifactAdapter.from_config(str(linked.resolve())).load()


def test_discover_serving_is_complete_static_and_independent_from_raw(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    source = DiscoverArtifactAdapter.from_config(str(root.resolve())).load()
    built = build_discover_serving(source, cache_root=root / "cache", profile_provider=_complete_profiles)
    installed = install_discover_serving(root, built)
    snapshot, etag = DiscoverServingLoader(root).load_with_etag()

    assert installed.changed is True
    assert snapshot.profileSummary.selectedCount == 5
    assert snapshot.profileSummary.identityComplete == 5
    assert snapshot.profileSummary.positioningComplete == 5
    assert snapshot.profileSummary.capabilitiesComplete == 5
    assert etag == f'"{built.manifest_sha256}"'
    item = snapshot.justDiscovered[0]
    detail, _ = DiscoverServingLoader(root).load_project_with_etag(
        item.githubRepositoryId,
        snapshot.discoverGenerationId,
    )
    assert detail.profile.positioningZh
    assert detail.profile.capabilities

    shutil.rmtree(root / "artifacts")
    clear_discover_serving_cache()
    offline, _ = DiscoverServingLoader(root).load_with_etag()
    assert offline == snapshot


def test_profile_failure_and_activation_interruption_preserve_old_serving(tmp_path: Path, monkeypatch) -> None:
    root = _copy_fixture(tmp_path)
    source = DiscoverArtifactAdapter.from_config(str(root.resolve())).load()
    first = build_discover_serving(source, cache_root=root / "cache", profile_provider=_complete_profiles)
    install_discover_serving(root, first)
    pointer = root / "discover-serving" / "current.json"
    before = pointer.read_bytes()

    def incomplete(projects, generation_id: str, cache_root: Path):
        result = _complete_profiles(projects, generation_id, cache_root)
        return ProfileBuildResult(
            profiles={key: value for index, (key, value) in enumerate(result.profiles.items()) if index > 0},
            github_requests=0,
            readme_cache_hits=0,
            translation_calls=0,
            translation_cache_hits=0,
        )

    with pytest.raises(DiscoverServingError) as profile_error:
        build_discover_serving(source, cache_root=root / "cache", profile_provider=incomplete)
    assert profile_error.value.code == "rardar_discover_profile_incomplete"
    assert pointer.read_bytes() == before

    import app.integrations.rardar.discover_serving as serving_module

    original = serving_module._atomic
    source_pointer = root / "discover-serving" / "sources" / f"{first.discover_generation_id}.json"
    source_pointer.unlink()

    def interrupt(path: Path, raw: bytes) -> None:
        if path == source_pointer:
            raise OSError("injected pointer interruption")
        original(path, raw)

    monkeypatch.setattr(serving_module, "_atomic", interrupt)
    with pytest.raises(OSError):
        install_discover_serving(root, first)
    assert pointer.read_bytes() == before


def test_discover_sync_is_idempotent_and_does_not_touch_today_pointer(tmp_path: Path) -> None:
    source = _copy_fixture(tmp_path, "source")
    target = (tmp_path / "mirror").resolve()
    target.mkdir()
    today = target / "serving" / "current.json"
    today.parent.mkdir()
    today.write_bytes(b'{"today":"unchanged"}\n')
    before = today.read_bytes()
    profile_provider_calls = 0

    def profile_provider(projects, generation_id, cache_root):
        nonlocal profile_provider_calls
        profile_provider_calls += 1
        if profile_provider_calls > 1:
            raise AssertionError("an unchanged source generation must reuse its validated Serving projection")
        return _complete_profiles(projects, generation_id, cache_root)

    first = sync_discover_intelligence(
        target=target,
        source_dir=source,
        profile_provider=profile_provider,
    )
    second = sync_discover_intelligence(
        target=target,
        source_dir=source,
        profile_provider=profile_provider,
    )

    assert first.changed is True
    assert second.changed is False
    assert profile_provider_calls == 1
    assert second.github_requests == 0
    assert second.translation_calls == 0
    assert first.discover_generation_id == second.discover_generation_id
    assert today.read_bytes() == before
    assert not list(tmp_path.glob(".*discover-stage-*"))


def test_discover_sync_activation_rollback_removes_candidates_and_is_retryable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _copy_fixture(tmp_path, "source")
    target = (tmp_path / "mirror").resolve()
    target.mkdir()
    today = target / "serving" / "current.json"
    today.parent.mkdir()
    today.write_bytes(b'{"today":"unchanged"}\n')

    import app.integrations.rardar.discover_sync as sync_module

    original = sync_module._atomic

    def interrupt(path: Path, raw: bytes) -> None:
        if "discover-sync" in path.parts:
            raise OSError("injected metadata activation interruption")
        original(path, raw)

    monkeypatch.setattr(sync_module, "_atomic", interrupt)
    with pytest.raises(sync_module.DiscoverSyncError):
        sync_discover_intelligence(
            target=target,
            source_dir=source,
            profile_provider=_complete_profiles,
        )

    assert today.read_bytes() == b'{"today":"unchanged"}\n'
    assert not (target / "artifacts" / "trending" / "discover" / "v1" / "current.json").exists()
    assert not (target / "discover-serving" / "current.json").exists()
    assert not list((target / "artifacts" / "trending" / "discover" / "v1" / "generations").glob("*"))
    assert not list((target / "discover-serving" / "generations").glob("*"))

    monkeypatch.setattr(sync_module, "_atomic", original)
    retried = sync_discover_intelligence(
        target=target,
        source_dir=source,
        profile_provider=_complete_profiles,
    )
    assert retried.changed is True


def test_discover_api_states_detail_and_no_database_dependency(tmp_path: Path, monkeypatch) -> None:
    root = _copy_fixture(tmp_path)
    source = DiscoverArtifactAdapter.from_config(str(root.resolve())).load()
    install_discover_serving(
        root,
        build_discover_serving(source, cache_root=root / "cache", profile_provider=_complete_profiles),
    )
    config = type("Config", (), {"RARDAR_INTELLIGENCE_DATA_DIR": root})()
    serving_snapshot, _ = DiscoverServingLoader(root).load_with_etag()
    snapshot, _ = rardar_intelligence.load_discover_snapshot(config, now=datetime(2026, 8, 30, 1, tzinfo=UTC))
    stale, _ = rardar_intelligence.load_discover_snapshot(config, now=datetime(2026, 8, 31, tzinfo=UTC))
    assert snapshot.status == "ready"
    assert stale.status == "stale"

    class EmptyLoader:
        def __init__(self, _root: Path) -> None:
            pass

        def load_with_etag(self):
            summary = serving_snapshot.profileSummary.model_copy(
                update={
                    "selectedCount": 0,
                    "identityComplete": 0,
                    "positioningComplete": 0,
                    "capabilitiesComplete": 0,
                    "officialZh": 0,
                    "officialTranslated": 0,
                    "rardarDerived": 0,
                }
            )
            return (
                serving_snapshot.model_copy(
                    update={
                        "profileSummary": summary,
                        "stageCounts": {"justDiscovered": 0, "rising": 0, "nearValidation": 0},
                        "justDiscovered": [],
                        "rising": [],
                        "nearValidation": [],
                    }
                ),
                '"empty"',
            )

    monkeypatch.setattr(rardar_intelligence, "DiscoverServingLoader", EmptyLoader)
    empty, _ = rardar_intelligence.load_discover_snapshot(config, now=datetime(2026, 8, 30, 1, tzinfo=UTC))
    assert empty.status == "empty"
    monkeypatch.undo()

    app = FastAPI()
    app.include_router(rardar_api.router, prefix="/api/v1")
    client = TestClient(app)
    monkeypatch.setattr(rardar_api, "is_rardar_product", lambda: True)
    monkeypatch.setattr(
        rardar_api, "load_discover_snapshot", lambda: rardar_intelligence.load_discover_snapshot(config)
    )
    monkeypatch.setattr(
        rardar_api,
        "load_discover_project_detail",
        lambda identifier, generation: rardar_intelligence.load_discover_project_detail(identifier, generation, config),
    )
    response = client.get("/api/v1/rardar/discover")
    assert response.status_code == 200
    body = response.json()
    identifier = body["stages"]["justDiscovered"][0]["githubRepositoryId"]
    detail = client.get(
        f"/api/v1/rardar/discover/projects/{identifier}",
        params={"generationId": body["generation"]},
    )
    assert detail.status_code == 200

    monkeypatch.setattr(
        rardar_api,
        "load_discover_snapshot",
        lambda: (_ for _ in ()).throw(RardarArtifactError("rardar_discover_invalid", "secret detail")),
    )
    invalid = client.get("/api/v1/rardar/discover")
    assert invalid.status_code == 503
    assert invalid.json()["status"] == "invalid"
    assert "secret detail" not in invalid.text

    monkeypatch.setattr(
        rardar_api,
        "load_discover_snapshot",
        lambda: (_ for _ in ()).throw(RardarArtifactError("rardar_discover_not_configured", "configuration detail")),
    )
    not_configured = client.get("/api/v1/rardar/discover")
    assert not_configured.status_code == 503
    assert not_configured.json()["status"] == "not_configured"
    assert "configuration detail" not in not_configured.text


def test_discover_loader_pointer_switch_recovers_in_same_process(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    source = DiscoverArtifactAdapter.from_config(str(root.resolve())).load()
    built = build_discover_serving(source, cache_root=root / "cache", profile_provider=_complete_profiles)
    install_discover_serving(root, built)
    loader = DiscoverServingLoader(root)
    first, _ = loader.load_with_etag()

    pointer = root / "discover-serving" / "current.json"
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    raw["publishedAt"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    staged = pointer.with_name("current.next.json")
    staged.write_bytes(_canonical(raw))
    os.replace(staged, pointer)
    second, _ = loader.load_with_etag()
    assert second == first


def test_discover_serving_detects_tamper_after_warm_read(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    source = DiscoverArtifactAdapter.from_config(str(root.resolve())).load()
    built = build_discover_serving(source, cache_root=root / "cache", profile_provider=_complete_profiles)
    install_discover_serving(root, built)
    loader = DiscoverServingLoader(root)
    loader.load_with_etag()

    artifact = root / "discover-serving" / "generations" / built.serving_generation_id / "discover.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")
    with pytest.raises(DiscoverServingError) as error:
        loader.load_with_etag()
    assert error.value.code == "rardar_discover_serving_invalid"
