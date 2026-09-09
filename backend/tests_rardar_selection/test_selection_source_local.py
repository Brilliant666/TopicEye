from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from app.integrations.rardar.adapter import RardarArtifactError, _SafeRoot
from app.integrations.rardar.selection_source import SelectionSourceError
from app.integrations.rardar.selection_source_local import build_selection_source_from_today_mirror
from tests_rardar_selection.source_fixture import source_bundle


def _mirror(target: Path) -> tuple[str, dict[str, bytes]]:
    today = json.loads(source_bundle())["today"]
    pointer = base64.b64decode(today["current"])
    generation = json.loads(pointer)["generationId"]
    prefix = f"generations/{generation}"
    files = {
        "current.json": pointer,
        f"{prefix}/manifest.json": base64.b64decode(today["manifest"]),
        f"{prefix}/trending/explosion.json": base64.b64decode(today["explosion"]),
        **{f"{prefix}/{key}": base64.b64decode(value) for key, value in today["generationFiles"].items()},
    }
    for relative, raw in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return generation, files


def test_local_mirror_reuses_verified_observations_without_writing(tmp_path: Path) -> None:
    generation, before = _mirror(tmp_path)
    built = build_selection_source_from_today_mirror(tmp_path, expected_today_generation=generation)
    second = build_selection_source_from_today_mirror(tmp_path, expected_today_generation=generation)
    assert second == built
    manifest = json.loads(built.files["manifest.json"])
    assert manifest["todayGenerationId"] == generation
    assert len(manifest["captureIds"]) >= 2
    assert {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert not (tmp_path / "selection-source").exists()


def test_local_mirror_refuses_different_today_version(tmp_path: Path) -> None:
    _mirror(tmp_path)
    with pytest.raises(SelectionSourceError) as error:
        build_selection_source_from_today_mirror(tmp_path, expected_today_generation="different-generation")
    assert error.value.code == "rardar_selection_today_changed"
    assert not (tmp_path / "selection-source").exists()


def test_local_mirror_rejects_corrupt_source_without_fallback(tmp_path: Path) -> None:
    generation, files = _mirror(tmp_path)
    capture = next(relative for relative in files if "/sources/" in relative)
    (tmp_path / capture).write_bytes(files[capture] + b" ")
    with pytest.raises(RardarArtifactError):
        build_selection_source_from_today_mirror(tmp_path, expected_today_generation=generation)
    assert not (tmp_path / "selection-source").exists()


def test_local_mirror_detects_pointer_change_during_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generation, _files = _mirror(tmp_path)
    original = _SafeRoot.read_stable
    reads = 0

    def changing(self: _SafeRoot, relative: str, *, maximum_bytes: int) -> bytes:
        nonlocal reads
        raw = original(self, relative, maximum_bytes=maximum_bytes)
        if relative == "current.json":
            reads += 1
            if reads == 3:
                return raw + b" "
        return raw

    monkeypatch.setattr(_SafeRoot, "read_stable", changing)
    with pytest.raises(SelectionSourceError) as error:
        build_selection_source_from_today_mirror(tmp_path, expected_today_generation=generation)
    assert error.value.code == "rardar_selection_today_changed"


def test_local_mirror_rejects_symlink(tmp_path: Path) -> None:
    generation, _files = _mirror(tmp_path / "actual")
    link = tmp_path / "linked"
    try:
        link.symlink_to(tmp_path / "actual", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(RardarArtifactError):
        build_selection_source_from_today_mirror(link, expected_today_generation=generation)


@pytest.mark.asyncio
async def test_preparing_new_source_keeps_existing_serving_readable(tmp_path: Path) -> None:
    from app.integrations.rardar.selection import build_selection
    from app.integrations.rardar.selection_serving import (
        SelectionServingLoader,
        build_selection_serving,
        install_selection_serving,
    )
    from app.integrations.rardar.selection_source import build_selection_source, install_selection_source
    from tests_rardar_selection.source_fixture import copy_and_load
    from tests_rardar_selection.test_selection import ModelDouble, _client

    target, old_source = copy_and_load(tmp_path)
    async with _client() as client:
        old = await build_selection(
            source=old_source, cache_root=target / "selection-profile-cache", caller=ModelDouble(), github_client=client
        )
    install_selection_serving(target, build_selection_serving(old))
    before = SelectionServingLoader(target).load_with_etag()
    pointer = (target / "discover-worth-seeing/current.json").read_bytes()
    install_selection_source(target, build_selection_source(source_bundle()))
    after = SelectionServingLoader(target).load_with_etag()
    assert after == before
    assert (target / "discover-worth-seeing/current.json").read_bytes() == pointer
