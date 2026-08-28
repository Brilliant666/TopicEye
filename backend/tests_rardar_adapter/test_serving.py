from __future__ import annotations

import json
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.integrations.rardar import serving as serving_module
from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.serving import (
    ServingProjectionError,
    ServingProjectionLoader,
    _validate_built_projection,
    build_serving_projection,
    clear_serving_cache,
    install_serving_projection,
    source_hashes,
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
