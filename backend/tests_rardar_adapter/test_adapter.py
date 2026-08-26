from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://adapter:adapter@127.0.0.1:5432/adapter")

from app.api.v1 import rardar as rardar_api
from app.integrations.rardar.adapter import RardarArtifactError, RardarIntelligenceAdapter, _SafeRoot

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence"
BACKEND = Path(__file__).parents[1]


def _copy_revision(tmp_path: Path, revision: str = "revision-a") -> Path:
    root = tmp_path / "data"
    shutil.copytree(FIXTURES / revision, root)
    return root


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _resign(root: Path, generation_id: str, *, artifact_changed: bool = False) -> None:
    manifest_path = root / "generations" / generation_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if artifact_changed:
        artifact_path = root / "generations" / generation_id / "trending" / "explosion.json"
        manifest["hashes"]["trending/explosion.json"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    _write_json(manifest_path, manifest)
    pointer_path = root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifestSha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write_json(pointer_path, pointer)


def _load(root: Path):
    return RardarIntelligenceAdapter.from_config(str(root)).load_explosion_board()


def test_ready_fixture_projects_only_verified_facts(tmp_path: Path) -> None:
    board = _load(_copy_revision(tmp_path))

    assert board.state == "ready"
    assert board.generationId == "fixture-explosion-a"
    assert len(board.exactRanked) == 5
    assert len(board.pendingRanked) == 3
    assert board.conflictCount == 2
    assert [item.rank for item in board.exactRanked] == [1, 2, 3, 4, 5]
    assert not hasattr(board.exactRanked[0], "summaryZh")


def test_unconfigured_missing_and_relative_roots_have_stable_errors(tmp_path: Path) -> None:
    with pytest.raises(RardarArtifactError) as unconfigured:
        RardarIntelligenceAdapter.from_config("")
    assert unconfigured.value.code == "rardar_intelligence_not_configured"

    with pytest.raises(RardarArtifactError) as missing:
        _load(tmp_path / "missing")
    assert missing.value.code == "rardar_intelligence_unavailable"

    with pytest.raises(RardarArtifactError) as relative:
        RardarIntelligenceAdapter.from_config("relative/data")
    assert relative.value.code == "rardar_intelligence_invalid_configuration"


def test_valid_generation_without_explosion_is_not_ready(tmp_path: Path) -> None:
    root = _copy_revision(tmp_path)
    manifest_path = root / "generations" / "fixture-explosion-a" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].remove("trending/explosion.json")
    del manifest["hashes"]["trending/explosion.json"]
    _write_json(manifest_path, manifest)
    _resign(root, "fixture-explosion-a")

    board = _load(root)

    assert board.state == "not_ready"
    assert board.reason == "explosion_artifact_not_published"
    assert board.exactRanked == []


@pytest.mark.parametrize("window_state", ["warming_up", "baseline_missing"])
def test_published_non_exact_states_keep_pending_facts(tmp_path: Path, window_state: str) -> None:
    root = _copy_revision(tmp_path)
    artifact_path = root / "generations" / "fixture-explosion-a" / "trending" / "explosion.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["window"]["state"] = window_state
    artifact["exactRanked"] = []
    artifact["coverage"]["exactEligibleCount"] = 0
    artifact["coverage"]["exactPublishedCount"] = 0
    _write_json(artifact_path, artifact)
    _resign(root, "fixture-explosion-a", artifact_changed=True)

    board = _load(root)

    assert board.state == window_state
    assert board.exactRanked == []
    assert len(board.pendingRanked) == 3


@pytest.mark.parametrize("case", ["manifest_missing", "manifest_digest", "manifest_state", "artifact_hash"])
def test_generation_integrity_failures_are_closed(tmp_path: Path, case: str) -> None:
    root = _copy_revision(tmp_path)
    generation = root / "generations" / "fixture-explosion-a"
    manifest_path = generation / "manifest.json"
    if case == "manifest_missing":
        manifest_path.unlink()
    elif case == "manifest_digest":
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    elif case == "manifest_state":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["state"] = "building"
        _write_json(manifest_path, manifest)
        _resign(root, "fixture-explosion-a")
    else:
        artifact_path = generation / "trending" / "explosion.json"
        artifact_path.write_bytes(artifact_path.read_bytes().replace(b"fixture-lab/exact-1", b"fixture-lab/exact-z", 1))

    with pytest.raises(RardarArtifactError) as error:
        _load(root)
    assert error.value.code == "rardar_generation_invalid"


def test_duplicate_json_and_non_finite_json_are_rejected(tmp_path: Path) -> None:
    for payload in (
        b'{"schemaVersion":1,"schemaVersion":1}\n',
        b'{"schemaVersion":1,"generationId":NaN}\n',
    ):
        root = _copy_revision(tmp_path / hashlib.sha256(payload).hexdigest())
        (root / "current.json").write_bytes(payload)
        with pytest.raises(RardarArtifactError) as error:
            _load(root)
        assert error.value.code == "rardar_current_pointer_invalid"


def test_rank_and_generation_tamper_fail_even_when_hash_chain_is_resigned(tmp_path: Path) -> None:
    for mutation in ("rank", "generation"):
        root = _copy_revision(tmp_path / mutation)
        artifact_path = root / "generations" / "fixture-explosion-a" / "trending" / "explosion.json"
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if mutation == "rank":
            artifact["exactRanked"][0]["rank"] = 2
        else:
            artifact["generationId"] = "fixture-explosion-z"
        _write_json(artifact_path, artifact)
        _resign(root, "fixture-explosion-a", artifact_changed=True)
        with pytest.raises(RardarArtifactError) as error:
            _load(root)
        assert error.value.code == "rardar_generation_invalid"


def test_source_and_source_path_tamper_fail_closed(tmp_path: Path) -> None:
    root = _copy_revision(tmp_path / "source")
    source = root / "generations" / "fixture-explosion-a" / "trending" / "sources" / "current.json"
    source.write_bytes(source.read_bytes().replace(b'"totalStars": 1100', b'"totalStars": 1101', 1))
    with pytest.raises(RardarArtifactError) as digest_error:
        _load(root)
    assert digest_error.value.code == "rardar_generation_invalid"

    root = _copy_revision(tmp_path / "escape")
    artifact_path = root / "generations" / "fixture-explosion-a" / "trending" / "explosion.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["sourceCaptures"]["current"]["generationRelativePath"] = "../current.json"
    _write_json(artifact_path, artifact)
    _resign(root, "fixture-explosion-a", artifact_changed=True)
    with pytest.raises(RardarArtifactError) as path_error:
        _load(root)
    assert path_error.value.code == "rardar_generation_invalid"


def test_source_payload_digest_tamper_fails_with_resigned_outer_hash_chain(tmp_path: Path) -> None:
    root = _copy_revision(tmp_path)
    generation = root / "generations" / "fixture-explosion-a"
    source_relative = "trending/sources/current.json"
    source_path = generation / source_relative
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["observations"][0]["totalStars"] += 1
    _write_json(source_path, source)

    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    artifact_path = generation / "trending" / "explosion.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["sourceCaptures"]["current"]["fileSha256"] = source_hash
    _write_json(artifact_path, artifact)

    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hashes"][source_relative] = source_hash
    _write_json(manifest_path, manifest)
    _resign(root, "fixture-explosion-a", artifact_changed=True)

    with pytest.raises(RardarArtifactError) as error:
        _load(root)
    assert error.value.code == "rardar_generation_invalid"


def test_same_length_mutation_during_read_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_revision(tmp_path)
    original = _SafeRoot._read_open_file
    calls = 0

    def mutate(path: Path, maximum_bytes: int):
        nonlocal calls
        result = original(path, maximum_bytes)
        calls += 1
        if calls == 1:
            raw = path.read_bytes()
            path.write_bytes(raw.replace(b"fixture-explosion-a", b"fixture-explosion-z", 1))
        return result

    monkeypatch.setattr(_SafeRoot, "_read_open_file", staticmethod(mutate))
    with pytest.raises(RardarArtifactError) as error:
        _load(root)
    assert error.value.code == "rardar_current_pointer_invalid"


def test_delete_and_recreate_during_read_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_revision(tmp_path)
    original = _SafeRoot._read_open_file
    calls = 0

    def recreate(path: Path, maximum_bytes: int):
        nonlocal calls
        result = original(path, maximum_bytes)
        calls += 1
        if calls == 1:
            raw = path.read_bytes()
            path.unlink()
            path.write_bytes(raw)
        return result

    monkeypatch.setattr(_SafeRoot, "_read_open_file", staticmethod(recreate))
    with pytest.raises(RardarArtifactError) as error:
        _load(root)
    assert error.value.code == "rardar_current_pointer_invalid"


def test_symlink_pointer_generation_and_root_are_rejected(tmp_path: Path) -> None:
    external = _copy_revision(tmp_path / "external")
    for kind in ("pointer", "generation", "root"):
        root = _copy_revision(tmp_path / kind)
        try:
            if kind == "pointer":
                (root / "current.json").unlink()
                (root / "current.json").symlink_to(external / "current.json")
                configured = root
            elif kind == "generation":
                generation = root / "generations" / "fixture-explosion-a"
                shutil.rmtree(generation)
                generation.symlink_to(external / "generations" / "fixture-explosion-a", target_is_directory=True)
                configured = root
            else:
                configured = tmp_path / "root-link"
                configured.symlink_to(root, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symbolic links are unavailable in this environment: {exc}")
        with pytest.raises(RardarArtifactError) as error:
            _load(configured)
        expected = (
            "rardar_intelligence_invalid_configuration"
            if kind == "root"
            else ("rardar_current_pointer_invalid" if kind == "pointer" else "rardar_generation_invalid")
        )
        assert error.value.code == expected


def test_junction_or_reparse_root_is_rejected_without_following(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_revision(tmp_path)
    original = os.lstat

    class ReparseInfo:
        def __init__(self, wrapped):
            self._wrapped = wrapped
            self.st_file_attributes = getattr(wrapped, "st_file_attributes", 0) | 0x400

        def __getattr__(self, name: str):
            return getattr(self._wrapped, name)

    def reparse_at_root(path):
        info = original(path)
        return ReparseInfo(info) if Path(path) == root else info

    monkeypatch.setattr(os, "lstat", reparse_at_root)
    with pytest.raises(RardarArtifactError) as error:
        _load(root)
    assert error.value.code == "rardar_intelligence_invalid_configuration"


def _combined_revisions(tmp_path: Path) -> Path:
    root = _copy_revision(tmp_path)
    source = FIXTURES / "revision-b" / "generations" / "fixture-explosion-b"
    shutil.copytree(source, root / "generations" / "fixture-explosion-b")
    return root


def _switch_to_revision_b(root: Path) -> None:
    staged = root / "current.next.json"
    shutil.copyfile(FIXTURES / "revision-b" / "current.json", staged)
    os.replace(staged, root / "current.json")


def test_pointer_switch_is_visible_without_restart(tmp_path: Path) -> None:
    root = _combined_revisions(tmp_path)
    adapter = RardarIntelligenceAdapter.from_config(str(root))
    assert adapter.load_explosion_board().generationId == "fixture-explosion-a"
    _switch_to_revision_b(root)
    assert adapter.load_explosion_board().generationId == "fixture-explosion-b"


def test_pointer_switch_after_logical_read_never_mixes_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _combined_revisions(tmp_path)
    adapter = RardarIntelligenceAdapter.from_config(str(root))
    original = adapter._root.read_stable
    switched = False

    def switch_after_pointer(relative: str, *, maximum_bytes: int) -> bytes:
        nonlocal switched
        raw = original(relative, maximum_bytes=maximum_bytes)
        if relative == "current.json" and not switched:
            switched = True
            _switch_to_revision_b(root)
        return raw

    monkeypatch.setattr(adapter._root, "read_stable", switch_after_pointer)
    assert adapter.load_explosion_board().generationId == "fixture-explosion-a"
    assert adapter.load_explosion_board().generationId == "fixture-explosion-b"


def test_api_is_404_by_default_and_returns_stable_503_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(rardar_api.router, prefix="/api/v1")
    client = TestClient(app)

    monkeypatch.setattr(rardar_api, "is_rardar_product", lambda: False)
    assert client.get("/api/v1/rardar/explosion-board").status_code == 404

    monkeypatch.setattr(rardar_api, "is_rardar_product", lambda: True)

    def unavailable():
        raise RardarArtifactError("rardar_intelligence_unavailable", "unavailable")

    monkeypatch.setattr(rardar_api, "load_explosion_board", unavailable)
    response = client.get("/api/v1/rardar/explosion-board")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "rardar_intelligence_unavailable"


@pytest.mark.parametrize(("rardar_mode", "expected_count"), [("false", 0), ("true", 1)])
def test_application_router_registers_adapter_only_in_rardar_mode(rardar_mode: str, expected_count: int) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": "postgresql+asyncpg://adapter:adapter@127.0.0.1:5432/adapter",
            "RARDAR_PRODUCT_MODE": rardar_mode,
            "PYTHONPATH": str(BACKEND),
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.api.v1.router import router; "
                "print(sum(route.path == '/api/v1/rardar/explosion-board' for route in router.routes))"
            ),
        ],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert int(completed.stdout.strip().splitlines()[-1]) == expected_count


def test_api_returns_ready_board_without_database_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    board = _load(_copy_revision(tmp_path))
    app = FastAPI()
    app.include_router(rardar_api.router, prefix="/api/v1")
    monkeypatch.setattr(rardar_api, "is_rardar_product", lambda: True)
    monkeypatch.setattr(rardar_api, "load_explosion_board", lambda: board)

    response = TestClient(app).get("/api/v1/rardar/explosion-board")

    assert response.status_code == 200
    assert response.json()["generationId"] == "fixture-explosion-a"
    assert len(response.json()["exactRanked"]) == 5
