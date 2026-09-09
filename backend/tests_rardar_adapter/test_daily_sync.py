"""Daily checks use the normal validated installer, without enrichment prerequisites."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from app.integrations.rardar.serving import ServingProjectionLoader, clear_serving_cache
from app.integrations.rardar.sync import RardarSyncError, sync_rardar_intelligence
from tests_rardar_adapter.test_sync import _bundle, _runner


def _changed_board(state: str) -> bytes:
    payload = json.loads(_bundle("revision-b"))
    artifact = json.loads(base64.b64decode(payload["files"]["trending/explosion.json"]))
    artifact["window"]["state"] = state
    artifact["exactRanked"] = []
    artifact["coverage"]["exactEligibleCount"] = 0
    artifact["coverage"]["exactPublishedCount"] = 0
    artifact_raw = json.dumps(artifact).encode()
    artifact_sha = hashlib.sha256(artifact_raw).hexdigest()
    manifest = json.loads(base64.b64decode(payload["files"]["manifest.json"]))
    manifest["hashes"]["trending/explosion.json"] = artifact_sha
    manifest_raw = json.dumps(manifest).encode()
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    pointer = json.loads(base64.b64decode(payload["current"]))
    pointer["manifestSha256"] = manifest_sha
    payload["current"] = base64.b64encode(json.dumps(pointer).encode()).decode()
    payload["files"]["manifest.json"] = base64.b64encode(manifest_raw).decode()
    payload["files"]["trending/explosion.json"] = base64.b64encode(artifact_raw).decode()
    payload.update(manifestSha256=manifest_sha, artifactSha256=artifact_sha, windowState=state, exactCount=0)
    return json.dumps(payload).encode()


def _inventory(target: Path) -> dict[str, bytes]:
    return {str(path.relative_to(target)): path.read_bytes() for path in target.rglob("*") if path.is_file()}


def _no_profiles(*_args):
    raise AssertionError("A check must not rebuild unchanged or unusable published facts")


def test_daily_check_installs_new_valid_facts_with_partial_v8_materials(tmp_path: Path) -> None:
    target = tmp_path / "mirror"
    first = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")), check_published=True)
    second = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-b")), check_published=True)
    assert first.outcome == second.outcome == "updated"
    assert second.changed
    assert second.upstream_window["endedAt"].startswith("2026-08-25")
    today, _ = ServingProjectionLoader(target).load_today_with_etag()
    assert today.schemaVersion == 8
    assert today.generationId == "fixture-explosion-b"
    assert today.exactRanked
    assert any(project.materialState != "complete" for project in today.exactRanked)
    for project in today.exactRanked:
        detail, _ = ServingProjectionLoader(target).load_project_with_etag(
            project.githubRepositoryId, today.generationId
        )
        assert detail.project.rank == project.rank
        assert detail.project.totalStars == project.totalStars
    assert (target / "generations" / "fixture-explosion-a").is_dir()


def test_daily_identical_check_is_zero_write_zero_profile_and_preserves_sync_time(tmp_path: Path) -> None:
    target = tmp_path / "mirror"
    first = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")), check_published=True)
    before = _inventory(target)
    second = sync_rardar_intelligence(
        target=target, runner=_runner(_bundle("revision-a")), profile_provider=_no_profiles, check_published=True
    )
    assert second.outcome == "unchanged"
    assert not second.changed
    assert second.synced_at == first.synced_at
    assert second.serving_generation_id == first.serving_generation_id
    assert _inventory(target) == before


@pytest.mark.parametrize("state", ["warming_up", "baseline_missing", "exact"])
@pytest.mark.parametrize("with_local", [True, False])
def test_daily_no_complete_board_preserves_old_facts_or_does_not_install(
    tmp_path: Path, state: str, with_local: bool
) -> None:
    target = tmp_path / "mirror"
    if with_local:
        sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    before = _inventory(target)
    result = sync_rardar_intelligence(
        target=target, runner=_runner(_changed_board(state)), profile_provider=_no_profiles, check_published=True
    )
    assert result.outcome == "no_complete_board"
    assert not result.changed
    assert result.upstream_window["state"] == state
    assert _inventory(target) == before
    if not with_local:
        assert not target.exists()


def test_daily_older_window_cannot_regress_current_display(tmp_path: Path) -> None:
    target = tmp_path / "mirror"
    first = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-b")))
    before = _inventory(target)
    result = sync_rardar_intelligence(
        target=target, runner=_runner(_bundle("revision-a")), profile_provider=_no_profiles, check_published=True
    )
    assert result.outcome == "no_complete_board"
    assert result.serving_generation_id == first.serving_generation_id
    assert _inventory(target) == before


@pytest.mark.parametrize("failure", ["remote", "facts", "local_detail"])
def test_daily_failed_check_preserves_current_and_never_rebuilds(tmp_path: Path, failure: str) -> None:
    target = tmp_path / "mirror"
    first = sync_rardar_intelligence(target=target, runner=_runner(_bundle("revision-a")))
    payload = json.loads(_bundle("revision-a"))
    if failure == "facts":
        payload["files"]["trending/explosion.json"] = base64.b64encode(b"{}").decode()
    if failure == "local_detail":
        manifest_path = target / "serving" / "generations" / first.serving_generation_id / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        project_path = next(iter(manifest["projects"].values()))["path"]
        (manifest_path.parent / project_path).write_bytes(b"{}")
    before = _inventory(target)

    def runner(_host: str, _root: str) -> bytes:
        if failure == "remote":
            raise RardarSyncError("rardar_sync_remote_unavailable", "Unavailable")
        return json.dumps(payload).encode()

    with pytest.raises(RardarSyncError):
        sync_rardar_intelligence(target=target, runner=runner, profile_provider=_no_profiles, check_published=True)
    assert _inventory(target) == before
    clear_serving_cache()


def test_check_cli_rejects_generate_profiles_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import sync_rardar_intelligence as cli

    monkeypatch.setattr("sys.argv", ["sync", "--target", "/unused", "--check-published", "--generate-profiles"])
    monkeypatch.setattr(cli, "sync_rardar_intelligence", _no_profiles)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_check_cli_uses_shared_check_with_model_generation_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from scripts import sync_rardar_intelligence as cli

    captured = {}

    def provider(**kwargs):
        captured.update(kwargs)
        return None

    real_sync = cli.sync_rardar_intelligence

    def sync(**kwargs):
        assert kwargs["check_published"] is True
        return real_sync(**kwargs, runner=_runner(_bundle("revision-a")))

    monkeypatch.setattr("sys.argv", ["sync", "--target", str(tmp_path / "mirror"), "--check-published"])
    monkeypatch.setattr(cli, "real_profile_provider", provider)
    monkeypatch.setattr(cli, "sync_rardar_intelligence", sync)
    assert cli.main() == 0
    assert captured["allow_model_generation"] is False
