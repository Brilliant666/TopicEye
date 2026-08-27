from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from app.integrations.rardar import sync as sync_module
from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.sync import RardarSyncError, ssh_read_only_runner, sync_rardar_intelligence

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence"


def _bundle(revision: str) -> bytes:
    root = FIXTURES / revision
    pointer_raw = (root / "current.json").read_bytes()
    pointer = json.loads(pointer_raw)
    generation_id = pointer["generationId"]
    generation = root / "generations" / generation_id
    manifest_raw = (generation / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    explosion_raw = (generation / "trending" / "explosion.json").read_bytes()
    explosion = json.loads(explosion_raw)
    captures = explosion["sourceCaptures"]
    references = [captures["current"]]
    if captures["baseline"]:
        references.append(captures["baseline"])
    references.extend(captures["partial"])
    if captures["coverageWitness"]:
        references.append(captures["coverageWitness"])
    files = {"manifest.json": manifest_raw, "trending/explosion.json": explosion_raw}
    for reference in references:
        relative = reference["generationRelativePath"]
        files[relative] = (generation / Path(*relative.split("/"))).read_bytes()
    payload = {
        "schemaVersion": 1,
        "generationId": generation_id,
        "current": base64.b64encode(pointer_raw).decode(),
        "files": {key: base64.b64encode(value).decode() for key, value in files.items()},
        "manifestSha256": hashlib.sha256(manifest_raw).hexdigest(),
        "artifactSha256": manifest["hashes"]["trending/explosion.json"],
        "windowState": explosion["window"]["state"],
        "exactCount": len(explosion["exactRanked"]),
        "pendingCount": len(explosion["pendingRanked"]),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _runner(raw: bytes, calls: list[tuple[str, str]] | None = None):
    def run(host: str, root: str) -> bytes:
        if calls is not None:
            calls.append((host, root))
        return raw

    return run


def test_sync_stages_validates_and_atomically_activates_generation(tmp_path: Path) -> None:
    target = tmp_path / "mirror"
    calls: list[tuple[str, str]] = []
    result = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a"), calls))

    assert calls == [("rardar-prod", "/var/lib/rardar/data")]
    assert result.generation_id == "fixture-explosion-a"
    assert result.file_count >= 4
    assert result.changed is True
    assert (
        RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board().generationId == result.generation_id
    )
    metadata = json.loads((target / "sync" / "generations" / "fixture-explosion-a.json").read_text())
    assert metadata["sourceHost"] == "rardar-prod"
    assert metadata["manifestSha256"] == result.manifest_sha256
    assert not list(tmp_path.glob(".mirror.staging-*"))

    repeated = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    assert repeated.changed is False
    assert (
        RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board().generationId == result.generation_id
    )


@pytest.mark.parametrize("case", ["damaged_artifact", "half_download"])
def test_sync_rejects_damage_and_preserves_old_mirror(tmp_path: Path, case: str) -> None:
    target = tmp_path / "mirror"
    sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    pointer_before = (target / "current.json").read_bytes()
    payload = json.loads(_bundle("revision-b"))
    if case == "damaged_artifact":
        payload["files"]["trending/explosion.json"] = base64.b64encode(b"{}").decode()
    else:
        source = next(key for key in payload["files"] if key.startswith("trending/sources/"))
        del payload["files"][source]

    with pytest.raises(RardarSyncError):
        sync_rardar_intelligence(
            target=target,
            runner=_runner(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()),
        )

    assert (target / "current.json").read_bytes() == pointer_before
    assert (
        RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board().generationId == "fixture-explosion-a"
    )
    assert not list(tmp_path.glob(".mirror.staging-*"))


def test_pointer_write_interruption_keeps_old_pointer_and_removes_partial_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "mirror"
    sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    pointer_before = (target / "current.json").read_bytes()
    original = sync_module._atomic_bytes

    def interrupted(path: Path, raw: bytes) -> None:
        if path == target / "current.json":
            raise OSError("injected pointer interruption")
        original(path, raw)

    monkeypatch.setattr(sync_module, "_atomic_bytes", interrupted)
    with pytest.raises(RardarSyncError) as error:
        sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-b")))

    assert error.value.code == "rardar_sync_failed"
    assert (target / "current.json").read_bytes() == pointer_before
    assert not (target / "generations" / "fixture-explosion-b").exists()
    assert not (target / "sync" / "generations" / "fixture-explosion-b.json").exists()
    assert not list(tmp_path.glob(".mirror.staging-*"))


def test_same_generation_interruption_restores_existing_sync_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "mirror"
    sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    pointer_before = (target / "current.json").read_bytes()
    metadata_path = target / "sync" / "generations" / "fixture-explosion-a.json"
    metadata_before = metadata_path.read_bytes()
    original = sync_module._atomic_bytes

    def interrupted(path: Path, raw: bytes) -> None:
        if path == target / "current.json":
            raise OSError("injected pointer interruption")
        original(path, raw)

    monkeypatch.setattr(sync_module, "_atomic_bytes", interrupted)
    with pytest.raises(RardarSyncError):
        sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))

    assert (target / "current.json").read_bytes() == pointer_before
    assert metadata_path.read_bytes() == metadata_before


def test_local_symlink_target_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    target = tmp_path / "mirror"
    try:
        target.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(RardarSyncError) as error:
        sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    assert error.value.code == "rardar_sync_unsafe_local_path"


def test_local_symlink_ancestor_is_rejected_before_staging(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(RardarSyncError) as error:
        sync_rardar_intelligence(target=alias / "nested" / "mirror", runner=_runner(_bundle("revision-a")))

    assert error.value.code == "rardar_sync_unsafe_local_path"
    assert not (real / "nested").exists()


def test_bundle_rejects_boolean_counts_without_creating_mirror(tmp_path: Path) -> None:
    payload = json.loads(_bundle("revision-a"))
    payload["exactCount"] = False
    target = tmp_path / "mirror"

    with pytest.raises(RardarSyncError) as error:
        sync_rardar_intelligence(
            target=target,
            runner=_runner(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()),
        )

    assert error.value.code == "rardar_sync_bundle_invalid"
    assert not target.exists()


def test_ssh_runner_uses_only_read_only_python_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured["program"] = kwargs["input"].decode()
        return subprocess.CompletedProcess(command, 0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert ssh_read_only_runner("rardar-prod", "/var/lib/rardar/data") == b"{}"
    assert captured["command"] == ["ssh", "rardar-prod", "sudo", "-n", "python3", "-"]
    assert 'open(path, "rb")' in captured["program"]
    assert 'open(path, "wb")' not in captured["program"]
    assert "unlink(" not in captured["program"]
    assert "remove(" not in captured["program"]
