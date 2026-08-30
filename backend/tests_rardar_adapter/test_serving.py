from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from app.integrations.rardar import serving as serving_module
from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.content_quality import audit_serving_top20
from app.integrations.rardar.narrative_fidelity import _audit_project, audit_official_narrative
from app.integrations.rardar.positioning_precision import audit_positioning_precision
from app.integrations.rardar.serving import (
    ServingProjectionError,
    ServingProjectionLoader,
    _validate_built_projection,
    build_serving_projection,
    clear_serving_cache,
    install_serving_projection,
    source_hashes,
)
from app.integrations.rardar.serving_completeness import audit_candidate_publication
from app.integrations.rardar.serving_schemas import (
    OfficialHighlight,
    ServingCapability,
    ServingProjectRecord,
    ServingTodaySnapshot,
)

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _rebundle(built, relative: str, payload: dict) -> tuple[bytes, dict[str, bytes]]:
    files = dict(built.files)
    files[relative] = _canonical(payload)
    manifest = json.loads(files["manifest.json"])
    inventory = [manifest["today"], *manifest["projects"].values(), *manifest["evidence"].values()]
    entry = next(item for item in inventory if item["path"] == relative)
    entry["bytes"] = len(files[relative])
    import hashlib

    entry["sha256"] = hashlib.sha256(files[relative]).hexdigest()
    files["manifest.json"] = _canonical(manifest)
    pointer = json.loads(built.pointer_raw)
    pointer["manifestSha256"] = hashlib.sha256(files["manifest.json"]).hexdigest()
    return _canonical(pointer), files


def _root(tmp_path: Path, revision: str = "revision-a") -> Path:
    root = tmp_path / "mirror"
    shutil.copytree(FIXTURES / revision, root)
    return root


def _build(root: Path):
    board = RardarIntelligenceAdapter.from_config(str(root)).load_explosion_board()
    manifest_sha, explosion_sha = source_hashes(root, board.generationId or "")
    return build_serving_projection(
        board=board,
        source_manifest_sha256=manifest_sha,
        source_explosion_sha256=explosion_sha,
        synced_at=None,
        source_host=None,
        cache_root=root / "profile-cache",
    )


def _install_two(root: Path) -> tuple[str, str]:
    first = _build(root)
    install_serving_projection(root, first)
    shutil.copytree(
        FIXTURES / "revision-b" / "generations" / "fixture-explosion-b",
        root / "generations" / "fixture-explosion-b",
    )
    shutil.copyfile(FIXTURES / "revision-b" / "current.json", root / "current.json")
    second = _build(root)
    install_serving_projection(root, second)
    return first.serving_generation_id, second.serving_generation_id


def test_raw_artifact_builds_small_bound_projection_in_original_order(tmp_path: Path) -> None:
    root = _root(tmp_path)
    board = RardarIntelligenceAdapter.from_config(str(root)).load_explosion_board()
    built = _build(root)
    result = install_serving_projection(root, built)
    today, etag = ServingProjectionLoader(root).load_today_with_etag()

    assert result.source_generation_id == board.generationId
    assert today.manifestSha256 == built.source_manifest_sha256
    assert today.artifactSha256 == built.source_explosion_sha256
    assert [item.githubRepositoryId for item in today.exactRanked] == [
        item.githubRepositoryId for item in board.exactRanked[:20]
    ]
    assert len(today.exactRanked) <= 20
    assert set(built.files) == {
        "manifest.json",
        "today.json",
        *(f"projects/{item.githubRepositoryId}.json" for item in board.exactRanked[:20]),
        *(f"evidence/{item.githubRepositoryId}.json" for item in board.exactRanked[:20]),
    }
    assert etag.startswith('"') and etag.endswith('"')
    assert today.schemaVersion == 6
    assert all(project.identitySummaryZh == project.officialSummaryZh for project in today.exactRanked)
    assert all(project.qualityState in {"ready", "partial", "rejected"} for project in today.exactRanked)
    assert all(isinstance(project.capabilities, list) for project in today.exactRanked)
    assert all(
        capability.detail in project.capabilityBulletsZh
        for project in today.exactRanked
        for capability in project.capabilities
    )


def test_content_quality_audit_reads_validated_serving_and_fails_incomplete_fixture(tmp_path: Path) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))

    report = audit_serving_top20(root)

    assert report["status"] == "FAIL"
    assert 0 < report["summary"]["total"] < 20
    assert report["sourceGenerationId"] == "fixture-explosion-a"
    assert report["projects"][0]["repository"] == "fixture-lab/exact-1"


def test_positioning_precision_audit_reads_only_validated_serving(tmp_path: Path) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))

    report = audit_positioning_precision(root)

    assert report["status"] == "PASS"
    assert report["sourceGenerationId"] == "fixture-explosion-a"
    assert report["servingSchemaVersion"] == 6
    assert report["summary"]["total"] == len(report["projects"])
    assert report["summary"]["remainingIssues"] == 0
    assert all(project["qualityResult"] == "PASS" for project in report["projects"])


@pytest.mark.parametrize("schema_version", [1, 2, 3, 4, 5])
def test_legacy_serving_versions_remain_readable_without_structured_capabilities(
    tmp_path: Path,
    schema_version: int,
) -> None:
    built = _build(_root(tmp_path))
    today = json.loads(built.files["today.json"])
    today["schemaVersion"] = schema_version
    v4_project_fields = {
        "identitySummaryZh",
        "coreValueZh",
        "coreValueEvidenceRefs",
        "keyDifferentiators",
        "productFormsZh",
        "qualityState",
        "qualityIssues",
    }
    v5_project_fields = {
        "officialTaglineZh",
        "officialTaglineEvidenceRefs",
        "officialPositioningZh",
        "officialPositioningEvidenceRefs",
        "officialHighlights",
        "officialNarrativeMode",
        "officialNarrativeIssues",
        "rardarAssessmentZh",
        "rardarAssessmentEvidenceRefs",
        "rardarDifferentiators",
    }
    v6_project_fields = {
        "positioningZh",
        "positioningSourceMode",
        "positioningEvidenceRefs",
        "positioningIncludedRoles",
        "positioningExcludedClauses",
    }
    for project in today["exactRanked"]:
        for field in v6_project_fields:
            project.pop(field, None)
        if schema_version < 5:
            for field in v5_project_fields:
                project.pop(field, None)
        if schema_version < 4:
            for field in v4_project_fields:
                project.pop(field, None)
        if schema_version < 3:
            project.pop("capabilities", None)
    parsed_today = ServingTodaySnapshot.model_validate_json(_canonical(today), strict=True)

    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    record = json.loads(built.files[f"projects/{identifier}.json"])
    record["schemaVersion"] = schema_version
    for field in v6_project_fields:
        record["project"].pop(field, None)
        record["profile"].pop(field, None)
    if schema_version < 5:
        for field in v5_project_fields:
            record["project"].pop(field, None)
            record["profile"].pop(field, None)
        record["profile"].pop("officialNarrativePromptVersion", None)
        record["profile"].pop("rardarAssessmentPromptVersion", None)
    if schema_version < 4:
        for field in v4_project_fields:
            record["project"].pop(field, None)
            record["profile"].pop(field, None)
    if schema_version < 3:
        record["project"].pop("capabilities", None)
        record["profile"].pop("capabilities", None)
    record["profile"]["profileSchemaVersion"] = f"rardar-project-profile-v{schema_version}"
    record["profile"]["promptVersion"] = {
        1: "rardar-project-profile-zh-v2",
        2: "rardar-project-profile-zh-v3",
        3: "rardar-project-profile-zh-v4",
        4: "rardar-project-profile-zh-v6",
        5: "rardar-project-profile-zh-v8",
    }[schema_version]
    parsed_record = ServingProjectRecord.model_validate_json(_canonical(record), strict=True)

    if schema_version < 3:
        assert parsed_today.exactRanked[0].capabilities == []
        assert parsed_record.profile.capabilities == []


def test_project_etag_binds_both_profile_record_and_evidence(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    install_serving_projection(root, built)
    today, _ = ServingProjectionLoader(root).load_today_with_etag()
    identifier = str(today.exactRanked[0].githubRepositoryId)
    detail, etag = ServingProjectionLoader(root).load_project_with_etag(int(identifier), today.generationId)
    manifest = json.loads(built.files["manifest.json"])
    expected = hashlib.sha256(
        (manifest["projects"][identifier]["sha256"] + ":" + manifest["evidence"][identifier]["sha256"]).encode("ascii")
    ).hexdigest()

    assert detail.evidence.digest == detail.profile.evidenceDigest
    assert etag == f'"{expected}"'


def test_warm_today_load_reads_only_pointer_and_never_raw_source_captures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))
    clear_serving_cache()
    loader = ServingProjectionLoader(root)
    calls: Counter[str] = Counter()
    original = loader.safe.read_stable

    def tracked(relative: str, **kwargs):
        calls[relative] += 1
        return original(relative, **kwargs)

    monkeypatch.setattr(loader.safe, "read_stable", tracked)
    loader.load_today_with_etag()
    calls.clear()
    for _ in range(20):
        loader.load_today_with_etag()

    assert set(calls) == {"serving/current.json"}
    assert not any("source-copies" in path or path.startswith("generations/") for path in calls)


def test_pointer_switch_keeps_old_source_addressable_and_never_mixes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first_id, second_id = _install_two(root)
    loader = ServingProjectionLoader(root)
    current, _ = loader.load_today_with_etag()
    assert current.servingGenerationId == second_id
    old_project_id = json.loads(
        (root / "serving" / "generations" / first_id / "today.json").read_text(encoding="utf-8")
    )["exactRanked"][0]["githubRepositoryId"]
    old, _ = loader.load_project_with_etag(old_project_id, "fixture-explosion-a")
    assert old.servingGenerationId == first_id
    assert old.generationId == "fixture-explosion-a"


def test_corrupt_today_fails_closed_without_raw_fallback(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    install_serving_projection(root, built)
    (root / "serving" / "generations" / built.serving_generation_id / "today.json").write_bytes(b"{}\n")
    clear_serving_cache()

    with pytest.raises(ServingProjectionError) as caught:
        ServingProjectionLoader(root).load_today_with_etag()

    assert caught.value.code == "rardar_serving_artifact_digest_invalid"
    assert (root / "current.json").exists()


def test_missing_project_evidence_is_a_partial_package_failure(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    install_serving_projection(root, built)
    today, _ = ServingProjectionLoader(root).load_today_with_etag()
    identifier = today.exactRanked[0].githubRepositoryId
    (root / "serving" / "generations" / built.serving_generation_id / f"evidence/{identifier}.json").unlink()
    clear_serving_cache()

    with pytest.raises(ServingProjectionError) as caught:
        ServingProjectionLoader(root).load_project_with_etag(identifier, today.generationId)

    assert caught.value.code == "rardar_serving_project_unavailable"


def test_schema_damage_is_rejected_before_install(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    today.pop("profileSummary")
    pointer, files = _rebundle(built, "today.json", today)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_today_invalid"


def test_v5_quality_summary_or_assessment_evidence_corruption_fails_closed(tmp_path: Path) -> None:
    built = _build(_root(tmp_path))
    today = json.loads(built.files["today.json"])
    today["profileSummary"]["qualityPartial"] += 1
    pointer, files = _rebundle(built, "today.json", today)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)
    assert caught.value.code == "rardar_serving_today_invalid"

    identifier = next(iter(json.loads(built.files["manifest.json"])["projects"]))
    record = json.loads(built.files[f"projects/{identifier}.json"])
    if record["profile"]["coreValueZh"] is None:
        record["profile"]["coreValueZh"] = "这个受控测试值必须绑定到真实的官方证据。"
        record["project"]["coreValueZh"] = record["profile"]["coreValueZh"]
        record["profile"]["claimEvidenceRefs"][record["profile"]["coreValueZh"]] = ["repository"]
    record["profile"]["coreValueEvidenceRefs"] = []
    record["project"]["coreValueEvidenceRefs"] = []
    record["profile"]["rardarAssessmentEvidenceRefs"] = []
    record["project"]["rardarAssessmentEvidenceRefs"] = []
    pointer, files = _rebundle(built, f"projects/{identifier}.json", record)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)
    assert caught.value.code == "rardar_serving_project_invalid"


def test_v5_missing_narrative_mode_fails_closed(tmp_path: Path) -> None:
    built = _build(_root(tmp_path))
    today = json.loads(built.files["today.json"])
    today["exactRanked"][0].pop("officialNarrativeMode")
    pointer, files = _rebundle(built, "today.json", today)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_today_invalid"


def test_narrative_audit_passes_validated_fixture_and_detects_boundary_damage(tmp_path: Path) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))

    report = audit_official_narrative(root)

    assert report["status"] == "PASS"
    assert report["summary"]["total"] == len(report["projects"])
    today, _ = ServingProjectionLoader(root).load_today_with_etag()
    detail, _ = ServingProjectionLoader(root).load_project_with_etag(
        today.exactRanked[0].githubRepositoryId,
        today.generationId,
    )
    damaged_profile = detail.profile.model_copy(
        update={
            "officialNarrativeMode": "official_zh",
            "sourceLabel": "Rardar 整理",
            "officialPositioningZh": detail.profile.rardarAssessmentZh,
        }
    )
    damaged = detail.model_copy(update={"profile": damaged_profile})

    audited = _audit_project(damaged)

    assert "official_source_falsely_labeled" in audited["boundaryViolations"]
    if detail.profile.rardarAssessmentZh is not None:
        assert "rardar_assessment_as_official_positioning" in audited["boundaryViolations"]


def test_narrative_audit_does_not_treat_rardar_derived_structure_as_official_source_order(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))
    today, _ = ServingProjectionLoader(root).load_today_with_etag()
    detail, _ = ServingProjectionLoader(root).load_project_with_etag(
        today.exactRanked[0].githubRepositoryId,
        today.generationId,
    )
    highlight = OfficialHighlight(
        sourceOrder=3,
        sourceTitle="Rardar 提炼标题",
        sourceDetail="Rardar 从非结构化证据提炼的说明。",
        titleZh="Rardar 提炼标题",
        detailZh="Rardar 从非结构化证据提炼的说明。",
        evidenceRefs=["description"],
    )
    differentiator = ServingCapability(
        title=highlight.titleZh,
        detail=highlight.detailZh,
        shortDetail=None,
        evidenceRefs=["description"],
    )
    derived_profile = detail.profile.model_copy(
        update={
            "officialNarrativeMode": "rardar_derived",
            "sourceLabel": "Rardar 整理",
            "officialHighlights": [highlight],
            "rardarDifferentiators": [differentiator],
            "officialTaglineZh": None,
            "officialPositioningZh": None,
            "rardarAssessmentZh": None,
        }
    )

    audited = _audit_project(detail.model_copy(update={"profile": derived_profile}))

    assert "official_highlight_order_changed" not in audited["boundaryViolations"]
    assert "rardar_differentiator_as_official_highlight" not in audited["boundaryViolations"]


def test_repeated_capability_title_and_detail_is_rejected_before_install(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    relative = f"projects/{identifier}.json"
    record = json.loads(built.files[relative])
    record["profile"]["capabilities"] = [
        {
            "title": "重复能力标题",
            "detail": "重复能力标题",
            "shortDetail": None,
            "evidenceRefs": ["description"],
        }
    ]
    record["profile"]["capabilityBulletsZh"] = ["重复能力标题"]
    pointer, files = _rebundle(built, relative, record)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_project_invalid"


def test_mixed_project_generation_is_rejected_even_with_updated_file_hashes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    relative = f"projects/{identifier}.json"
    record = json.loads(built.files[relative])
    record["generationId"] = "fixture-other"
    record["profile"]["generationId"] = "fixture-other"
    pointer, files = _rebundle(built, relative, record)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_mixed_generation"


def test_today_project_inventory_must_match_the_manifest(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    today["exactRanked"][0]["githubRepositoryId"] = 999999
    pointer, files = _rebundle(built, "today.json", today)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_inventory_invalid"


def test_project_facts_must_match_the_today_projection(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    relative = f"projects/{identifier}.json"
    record = json.loads(built.files[relative])
    record["project"]["rank"] += 1
    pointer, files = _rebundle(built, relative, record)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_mixed_generation"


def test_every_profile_claim_requires_saved_evidence(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    relative = f"projects/{identifier}.json"
    record = json.loads(built.files[relative])
    record["profile"]["claimEvidenceRefs"].pop(record["profile"]["officialSummaryZh"])
    pointer, files = _rebundle(built, relative, record)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_evidence_ref_invalid"


def test_structured_capability_requires_a_saved_evidence_reference(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    relative = f"projects/{identifier}.json"
    record = json.loads(built.files[relative])
    capability = {
        "title": "可验证能力",
        "detail": "保留完整且可复核的能力说明。",
        "shortDetail": None,
        "evidenceRefs": ["readme:missing"],
    }
    record["profile"]["capabilities"] = [capability]
    record["profile"]["capabilityBulletsZh"] = ["保留完整且可复核的能力说明。"]
    record["project"]["capabilities"] = [capability]
    record["project"]["capabilityBulletsZh"] = ["保留完整且可复核的能力说明。"]
    record["profile"]["claimEvidenceRefs"]["保留完整且可复核的能力说明。"] = ["description"]
    pointer, files = _rebundle(built, relative, record)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_evidence_ref_invalid"


def test_evidence_digest_is_recomputed_instead_of_trusting_the_field(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    today = json.loads(built.files["today.json"])
    identifier = str(today["exactRanked"][0]["githubRepositoryId"])
    relative = f"evidence/{identifier}.json"
    evidence = json.loads(built.files[relative])
    evidence["evidenceIndex"]["description"] = "changed after the evidence digest was created"
    pointer, files = _rebundle(built, relative, evidence)

    with pytest.raises(ServingProjectionError) as caught:
        _validate_built_projection(pointer, files)

    assert caught.value.code == "rardar_serving_evidence_digest_invalid"


def test_concurrent_load_parses_manifest_and_today_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))
    clear_serving_cache()
    loader = ServingProjectionLoader(root)
    calls: Counter[str] = Counter()
    original = loader.safe.read_stable

    def tracked(relative: str, **kwargs):
        calls[relative] += 1
        return original(relative, **kwargs)

    monkeypatch.setattr(loader.safe, "read_stable", tracked)
    with ThreadPoolExecutor(max_workers=12) as executor:
        generations = list(executor.map(lambda _index: loader.load_today_with_etag()[0].generationId, range(24)))

    assert len(set(generations)) == 1
    assert sum(count for path, count in calls.items() if path.endswith("manifest.json")) == 1
    assert sum(count for path, count in calls.items() if path.endswith("today.json")) == 1


def test_same_loader_invalidates_after_atomic_pointer_switch(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = _build(root)
    install_serving_projection(root, first)
    loader = ServingProjectionLoader(root)
    assert loader.load_today_with_etag()[0].generationId == "fixture-explosion-a"

    shutil.copytree(
        FIXTURES / "revision-b" / "generations" / "fixture-explosion-b",
        root / "generations" / "fixture-explosion-b",
    )
    shutil.copyfile(FIXTURES / "revision-b" / "current.json", root / "current.json")
    install_serving_projection(root, _build(root))

    assert loader.load_today_with_etag()[0].generationId == "fixture-explosion-b"


def test_serving_pointer_interruption_restores_both_pointers_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    first = _build(root)
    install_serving_projection(root, first)
    current_path = root / "serving" / "current.json"
    current_before = current_path.read_bytes()
    source_before = (root / "serving" / "sources" / "fixture-explosion-a.json").read_bytes()

    shutil.copytree(
        FIXTURES / "revision-b" / "generations" / "fixture-explosion-b",
        root / "generations" / "fixture-explosion-b",
    )
    shutil.copyfile(FIXTURES / "revision-b" / "current.json", root / "current.json")
    second = _build(root)
    original = serving_module._atomic_bytes

    def interrupted(path: Path, raw: bytes) -> None:
        if path == current_path:
            raise OSError("injected current pointer interruption")
        original(path, raw)

    monkeypatch.setattr(serving_module, "_atomic_bytes", interrupted)
    with pytest.raises(OSError, match="injected current pointer interruption"):
        install_serving_projection(root, second)

    assert current_path.read_bytes() == current_before
    assert (root / "serving" / "sources" / "fixture-explosion-a.json").read_bytes() == source_before
    assert not (root / "serving" / "sources" / "fixture-explosion-b.json").exists()
    assert not (root / "serving" / "generations" / second.serving_generation_id).exists()


def test_source_pointer_path_is_validated_before_io(tmp_path: Path) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))

    with pytest.raises(ServingProjectionError) as caught:
        ServingProjectionLoader(root).load_project_with_etag(1, "../escape")

    assert caught.value.code == "rardar_serving_source_invalid"
    assert not (tmp_path / "escape").exists()


def test_unretained_source_is_a_revision_mismatch_not_current_corruption(tmp_path: Path) -> None:
    root = _root(tmp_path)
    install_serving_projection(root, _build(root))

    with pytest.raises(ServingProjectionError) as caught:
        ServingProjectionLoader(root).load_project_with_etag(1, "missing-generation")

    assert caught.value.code == "rardar_serving_source_not_found"


def _completeness_audit(built, *, count: int) -> dict[str, object]:
    today = ServingTodaySnapshot.model_validate_json(built.files["today.json"], strict=True)
    template = today.exactRanked[0]
    projects = [
        template.model_copy(
            update={
                "rank": rank,
                "githubRepositoryId": 90_000 + rank,
                "identitySummaryZh": "一个以证据组织项目研究的开发工具。",
                "officialSummaryZh": "一个以证据组织项目研究的开发工具。",
                "officialTaglineZh": "一个以证据组织项目研究的开发工具。",
                "officialTaglineEvidenceRefs": ["description"],
                "officialPositioningZh": "一个以证据组织项目研究的工具，通过绑定仓库原文保留可追溯性。",
                "officialPositioningEvidenceRefs": ["description"],
                "positioningZh": "一个以证据组织项目研究的工具，通过绑定仓库原文保留可追溯性。",
                "positioningSourceMode": "rardar_derived",
                "positioningEvidenceRefs": ["description"],
                "positioningIncludedRoles": ["identity", "core_mechanism", "primary_outcome"],
                "officialNarrativeMode": "rardar_derived",
                "qualityState": "partial",
            }
        )
        for rank in range(1, count + 1)
    ]
    candidate = today.model_copy(
        update={
            "coverage": today.coverage.model_copy(update={"exactCount": 20}),
            "exactRanked": projects,
        }
    )
    return audit_candidate_publication(
        candidate,
        None,
        candidate_serving_id=built.serving_generation_id,
    )


def test_exact_top20_completeness_requires_twenty_publishable_positions(tmp_path: Path) -> None:
    built = _build(_root(tmp_path))

    incomplete = _completeness_audit(built, count=19)
    complete = _completeness_audit(built, count=20)

    assert incomplete["top20Total"] == 19
    assert incomplete["positioningCompleteCount"] == 19
    assert incomplete["activationAllowed"] is False
    assert complete["top20Total"] == 20
    assert complete["identityCompleteCount"] == 20
    assert complete["positioningCompleteCount"] == 20
    assert complete["activationAllowed"] is True


def test_completeness_audit_keeps_non_top20_not_ready_snapshots_compatible(tmp_path: Path) -> None:
    built = _build(_root(tmp_path))
    today = ServingTodaySnapshot.model_validate_json(built.files["today.json"], strict=True)
    not_ready = today.model_copy(update={"coverage": None, "exactRanked": []})

    audit = audit_candidate_publication(
        not_ready,
        None,
        candidate_serving_id=built.serving_generation_id,
    )

    assert audit["top20GateRequired"] is False
    assert audit["top20Total"] == 0
    assert audit["activationAllowed"] is True


@pytest.mark.parametrize(
    "updates",
    [
        {
            "officialPositioningZh": "一个以证据组织项目研究的开发工具。",
            "positioningZh": "一个以证据组织项目研究的开发工具。",
        },
        {
            "positioningIncludedRoles": ["identity"],
        },
    ],
)
def test_exact_top20_rejects_repeated_or_identity_only_positioning(tmp_path: Path, updates: dict[str, object]) -> None:
    built = _build(_root(tmp_path))
    today = ServingTodaySnapshot.model_validate_json(built.files["today.json"], strict=True)
    audit = _completeness_audit(built, count=20)
    template = today.exactRanked[0]
    projects = [
        template.model_copy(
            update={
                "rank": rank,
                "githubRepositoryId": 91_000 + rank,
                "identitySummaryZh": "一个以证据组织项目研究的开发工具。",
                "officialSummaryZh": "一个以证据组织项目研究的开发工具。",
                "officialTaglineZh": "一个以证据组织项目研究的开发工具。",
                "officialTaglineEvidenceRefs": ["description"],
                "officialPositioningZh": "通过绑定仓库原文保留项目研究结论的可追溯性。",
                "officialPositioningEvidenceRefs": ["description"],
                "positioningZh": "通过绑定仓库原文保留项目研究结论的可追溯性。",
                "positioningSourceMode": "rardar_derived",
                "positioningEvidenceRefs": ["description"],
                "positioningIncludedRoles": ["core_mechanism", "primary_outcome"],
                "officialNarrativeMode": "rardar_derived",
                "qualityState": "partial",
                **(updates if rank == 5 else {}),
            }
        )
        for rank in range(1, 21)
    ]
    candidate = today.model_copy(
        update={
            "coverage": today.coverage.model_copy(update={"exactCount": 20}),
            "exactRanked": projects,
        }
    )
    audit = audit_candidate_publication(candidate, None, candidate_serving_id=built.serving_generation_id)

    assert audit["positioningCompleteCount"] == 19
    assert audit["activationAllowed"] is False


def test_failed_candidate_gate_preserves_current_and_raw_pointer_bytes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    built = _build(root)
    install_serving_projection(root, built)
    serving_pointer = root / "serving" / "current.json"
    before_serving = serving_pointer.read_bytes()
    before_raw = (root / "current.json").read_bytes()
    before_generations = sorted(path.name for path in (root / "serving" / "generations").iterdir())
    blocked = replace(built, publication_audit=_completeness_audit(built, count=19))

    with pytest.raises(ServingProjectionError) as caught:
        install_serving_projection(root, blocked)

    assert caught.value.code == "candidate_completeness_failed"
    assert caught.value.audit is not None
    assert caught.value.audit["activationPerformed"] is False
    assert serving_pointer.read_bytes() == before_serving
    assert (root / "current.json").read_bytes() == before_raw
    assert sorted(path.name for path in (root / "serving" / "generations").iterdir()) == before_generations
