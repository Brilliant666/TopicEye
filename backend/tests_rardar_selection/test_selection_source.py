from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.integrations.rardar import selection_source as source_module
from app.integrations.rardar.selection_source import (
    SelectionSourceAdapter,
    SelectionSourceError,
    build_selection_source,
    install_selection_source,
    ssh_selection_source_runner,
)
from tests_rardar_selection.source_fixture import source_bundle


def _payload() -> dict[str, object]:
    return json.loads(source_bundle())


def test_source_bundle_installs_complete_observation_window_and_is_idempotent(tmp_path: Path) -> None:
    built = build_selection_source(source_bundle())
    first = install_selection_source(tmp_path.resolve(), built)
    pointer = (tmp_path / "selection-source/current.json").read_bytes()
    second = install_selection_source(tmp_path.resolve(), built)
    loaded = SelectionSourceAdapter(tmp_path.resolve()).load()

    assert first.created is True and first.changed is True
    assert second.created is False and second.changed is False
    assert (tmp_path / "selection-source/current.json").read_bytes() == pointer
    assert len(loaded.captures) == 14
    assert loaded.source_observation_set_id == built.source_observation_set_id
    assert loaded.source_observation_set_id.startswith("observation-v1-")
    assert loaded.today_generation_id
    assert loaded.today["exactRanked"]
    assert (
        source_module._timestamp(loaded.captures[-1]["scheduledAt"])
        - source_module._timestamp(loaded.captures[0]["scheduledAt"])
    ).total_seconds() == 26 * 3600


def test_corrupt_capture_or_today_hash_fails_before_pointer_change(tmp_path: Path) -> None:
    healthy = build_selection_source(source_bundle())
    install_selection_source(tmp_path.resolve(), healthy)
    pointer = (tmp_path / "selection-source/current.json").read_bytes()

    payload = _payload()
    capture = payload["captures"][0]
    decoded = json.loads(base64.b64decode(capture["content"]))
    decoded["observations"][0]["totalStars"] += 1
    capture["content"] = base64.b64encode(json.dumps(decoded).encode()).decode()
    with pytest.raises(SelectionSourceError, match="provenance"):
        build_selection_source(json.dumps(payload).encode())
    assert (tmp_path / "selection-source/current.json").read_bytes() == pointer

    payload = _payload()
    manifest = json.loads(base64.b64decode(payload["today"]["manifest"]))
    manifest["hashes"]["trending/explosion.json"] = "0" * 64
    payload["today"]["manifest"] = base64.b64encode(json.dumps(manifest).encode()).decode()
    with pytest.raises(SelectionSourceError):
        build_selection_source(json.dumps(payload).encode())
    assert (tmp_path / "selection-source/current.json").read_bytes() == pointer


def test_degraded_phase_gap_is_allowed_but_short_window_is_rejected(tmp_path: Path) -> None:
    del tmp_path
    payload = _payload()
    payload["captures"].pop(4)
    built = build_selection_source(json.dumps(payload).encode())
    assert built.source_observation_set_id.startswith("observation-v1-")

    payload = _payload()
    payload["captures"] = payload["captures"][-13:]
    with pytest.raises(SelectionSourceError, match="26 to 72"):
        build_selection_source(json.dumps(payload).encode())


def test_loader_rejects_corruption_and_extra_files(tmp_path: Path) -> None:
    built = build_selection_source(source_bundle())
    install_selection_source(tmp_path.resolve(), built)
    root = tmp_path / "selection-source/generations" / built.source_observation_set_id
    capture = next((root / "captures").glob("*.json"))
    capture.write_bytes(capture.read_bytes() + b" ")
    with pytest.raises(SelectionSourceError, match="read failed"):
        SelectionSourceAdapter(tmp_path.resolve()).load()

    capture.write_bytes(built.files[capture.relative_to(root).as_posix()])
    (root / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SelectionSourceError, match="cross-file"):
        SelectionSourceAdapter(tmp_path.resolve()).load()


def test_failed_atomic_activation_restores_previous_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = build_selection_source(source_bundle())
    install_selection_source(tmp_path.resolve(), first)
    pointer_path = tmp_path / "selection-source/current.json"
    before = pointer_path.read_bytes()
    payload = _payload()
    first_capture = payload["captures"][0]
    decoded = json.loads(base64.b64decode(first_capture["content"]))
    decoded["capturedAt"] = "2026-08-28T22:05:01Z"
    digestless = {key: value for key, value in decoded.items() if key != "digest"}
    decoded["digest"]["value"] = hashlib.sha256(
        json.dumps(digestless, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    first_capture["content"] = base64.b64encode(
        json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    second = build_selection_source(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    original = source_module._atomic

    def fail_once(path: Path, raw: bytes) -> None:
        if path == pointer_path and raw == second.pointer_raw:
            raise OSError("simulated pointer interruption")
        original(path, raw)

    monkeypatch.setattr(source_module, "_atomic", fail_once)
    with pytest.raises(OSError, match="simulated"):
        install_selection_source(tmp_path.resolve(), second)
    assert pointer_path.read_bytes() == before
    assert (
        SelectionSourceAdapter(tmp_path.resolve()).load().source_observation_set_id == first.source_observation_set_id
    )


def test_source_store_rejects_symlink_boundary(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unsupported")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "selection-source"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(SelectionSourceError, match="unsafe"):
        install_selection_source(tmp_path.resolve(), build_selection_source(source_bundle()))


def test_remote_sync_rejects_ssh_option_instead_of_treating_it_as_a_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def unexpected_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not run for an unsafe host")

    monkeypatch.setattr(source_module.subprocess, "run", unexpected_run)
    with pytest.raises(SelectionSourceError) as exc_info:
        ssh_selection_source_runner("-oProxyCommand=unsafe", "/var/lib/rardar/data")
    assert exc_info.value.code == "rardar_selection_source_invalid_configuration"
    assert called is False
