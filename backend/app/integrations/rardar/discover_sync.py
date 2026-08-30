"""Independent read-only sync for Rardar Discover raw and Serving generations."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from app.integrations.rardar.adapter import _SafeRoot, _strict_json
from app.integrations.rardar.discover import DISCOVER_ROOT, DiscoverArtifactAdapter
from app.integrations.rardar.discover_serving import (
    DISCOVER_SERVING_PROJECTION_VERSION,
    DiscoverServingError,
    DiscoverServingLoader,
    build_discover_serving,
    clear_discover_serving_cache,
    install_discover_serving,
)
from app.integrations.rardar.serving import ProfileProvider

_GENERATION = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_HOST = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_REPARSE_POINT = 0x400
_MAX_BUNDLE = 256 * 1024 * 1024


class DiscoverSyncError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class DiscoverSyncResult:
    discover_generation_id: str
    serving_generation_id: str
    manifest_sha256: str
    artifact_sha256: str
    latest_capture_id: str
    published_count: int
    changed: bool
    github_requests: int
    readme_cache_hits: int
    translation_calls: int
    translation_cache_hits: int


RemoteRunner = Callable[[str, str], bytes]

_REMOTE_PROGRAM = r"""
import base64, hashlib, json, os, re, stat, sys
from pathlib import PurePosixPath

ROOT = __REMOTE_ROOT__
STORE = "artifacts/trending/discover/v1"
GENERATION = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
MAX_FILE = 16 * 1024 * 1024

def safe_parts(relative):
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or not parsed.parts or any(part in ("", ".", "..") for part in parsed.parts):
        raise RuntimeError("unsafe_path")
    return parsed.parts

def read_stable(relative, maximum=MAX_FILE):
    path = os.path.join(ROOT, *safe_parts(relative))
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_size > maximum:
        raise RuntimeError("unsafe_file")
    with open(path, "rb") as handle:
        first = handle.read(maximum + 1)
    middle = os.lstat(path)
    with open(path, "rb") as handle:
        second = handle.read(maximum + 1)
    after = os.lstat(path)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if len(first) > maximum or first != second or identity(before) != identity(middle) or identity(middle) != identity(after):
        raise RuntimeError("unstable_file")
    return first

def object_value(raw):
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("invalid_json")
    return value

pointer_relative = STORE + "/current.json"
pointer_raw = read_stable(pointer_relative, 65536)
pointer = object_value(pointer_raw)
generation_id = pointer.get("generationId")
if not isinstance(generation_id, str) or not GENERATION.fullmatch(generation_id):
    raise RuntimeError("unsafe_generation")
base = STORE + "/generations/" + generation_id
manifest_raw = read_stable(base + "/manifest.json", 4 * 1024 * 1024)
manifest = object_value(manifest_raw)
manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
if pointer.get("manifestSha256") != manifest_sha or manifest.get("generationId") != generation_id or manifest.get("state") != "ready":
    raise RuntimeError("manifest_mismatch")
artifacts = manifest.get("artifacts")
if not isinstance(artifacts, dict) or "discover.json" not in artifacts:
    raise RuntimeError("manifest_inventory_invalid")
files = {"manifest.json": manifest_raw}
for relative, expected in artifacts.items():
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise RuntimeError("manifest_inventory_invalid")
    raw = read_stable(base + "/" + relative)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("artifact_hash_invalid")
    files[relative] = raw
if read_stable(pointer_relative, 65536) != pointer_raw or read_stable(base + "/manifest.json", 4 * 1024 * 1024) != manifest_raw:
    raise RuntimeError("publication_changed")
payload = {
    "schemaVersion": 1,
    "generationId": generation_id,
    "current": base64.b64encode(pointer_raw).decode("ascii"),
    "files": {key: base64.b64encode(value).decode("ascii") for key, value in files.items()},
    "manifestSha256": manifest_sha,
    "artifactSha256": artifacts["discover.json"],
}
sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
"""


def _remote_program(remote_root: str) -> str:
    if not remote_root.startswith("/") or "\x00" in remote_root:
        raise DiscoverSyncError("rardar_discover_sync_invalid_configuration", "Remote root is invalid")
    return _REMOTE_PROGRAM.replace("__REMOTE_ROOT__", repr(remote_root))


def ssh_discover_runner(host: str, remote_root: str) -> bytes:
    if not _HOST.fullmatch(host):
        raise DiscoverSyncError("rardar_discover_sync_invalid_configuration", "SSH host alias is invalid")
    try:
        completed = subprocess.run(
            ["ssh", host, "sudo", "-n", "python3", "-"],
            input=_remote_program(remote_root).encode(),
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiscoverSyncError("rardar_discover_sync_remote_unavailable", "Discover inventory failed") from exc
    if completed.returncode != 0:
        raise DiscoverSyncError("rardar_discover_sync_remote_rejected", "Discover inventory was rejected")
    if len(completed.stdout) > _MAX_BUNDLE:
        raise DiscoverSyncError("rardar_discover_sync_bundle_too_large", "Discover bundle exceeded the limit")
    return completed.stdout


def local_discover_runner(source: Path) -> bytes:
    """Produce the same bundle from an isolated local data copy."""

    loaded = DiscoverArtifactAdapter.from_config(str(source)).load()
    generation_id = loaded.board.discoverGenerationId
    safe = _SafeRoot(str(source))
    pointer = safe.read_stable(f"{DISCOVER_ROOT}/current.json", maximum_bytes=64 * 1024)
    manifest_raw = safe.read_stable(
        f"{DISCOVER_ROOT}/generations/{generation_id}/manifest.json",
        maximum_bytes=4 * 1024 * 1024,
    )
    manifest = _strict_json(manifest_raw)
    files = {"manifest.json": manifest_raw}
    for relative in manifest["artifacts"]:
        files[relative] = safe.read_stable(
            f"{DISCOVER_ROOT}/generations/{generation_id}/{relative}", maximum_bytes=16 * 1024 * 1024
        )
    return json.dumps(
        {
            "schemaVersion": 1,
            "generationId": generation_id,
            "current": base64.b64encode(pointer).decode(),
            "files": {key: base64.b64encode(raw).decode() for key, raw in files.items()},
            "manifestSha256": loaded.manifest_sha256,
            "artifactSha256": loaded.artifact_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _decode(raw: bytes) -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
    try:
        value = _strict_json(raw)
        if set(value) != {"schemaVersion", "generationId", "current", "files", "manifestSha256", "artifactSha256"}:
            raise ValueError("unexpected fields")
        if value["schemaVersion"] != 1 or not _GENERATION.fullmatch(value["generationId"]):
            raise ValueError("invalid bundle identity")
        if not _SHA.fullmatch(value["manifestSha256"]) or not _SHA.fullmatch(value["artifactSha256"]):
            raise ValueError("invalid bundle digest")
        pointer = base64.b64decode(value["current"], validate=True)
        if not isinstance(value["files"], dict):
            raise ValueError("invalid bundle files")
        files: dict[str, bytes] = {}
        for relative, encoded in value["files"].items():
            path = PurePosixPath(relative)
            if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
                raise ValueError("unsafe file")
            files[relative] = base64.b64decode(encoded, validate=True)
        if "manifest.json" not in files or "discover.json" not in files or sum(map(len, files.values())) > _MAX_BUNDLE:
            raise ValueError("incomplete bundle")
    except Exception as exc:
        raise DiscoverSyncError("rardar_discover_sync_bundle_invalid", "Discover bundle is invalid") from exc
    return value, pointer, files


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _plain_directory(path: Path) -> None:
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise DiscoverSyncError("rardar_discover_sync_unsafe_path", "Local mirror path is unsafe")


def _ensure_chain(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:] if path.anchor else path.parts:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            with suppress(FileExistsError):
                current.mkdir()
            info = os.lstat(current)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise DiscoverSyncError("rardar_discover_sync_unsafe_path", "Local mirror path is unsafe")


def _atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _optional(path: Path) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise DiscoverSyncError("rardar_discover_sync_unsafe_path", "Local pointer is unsafe")
    return path.read_bytes()


def _identical(root: Path, files: dict[str, bytes]) -> bool:
    if not root.exists():
        return False
    _plain_directory(root)
    actual: set[str] = set()
    for path in root.rglob("*"):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise DiscoverSyncError("rardar_discover_sync_unsafe_path", "Immutable Discover generation is unsafe")
        if stat.S_ISREG(info.st_mode):
            actual.add(path.relative_to(root).as_posix())
        elif not stat.S_ISDIR(info.st_mode):
            raise DiscoverSyncError("rardar_discover_sync_unsafe_path", "Immutable Discover generation is unsafe")
    if actual != set(files):
        return False
    safe = _SafeRoot(str(root))
    return all(safe.read_stable(relative, maximum_bytes=max(len(raw), 1)) == raw for relative, raw in files.items())


def sync_discover_intelligence(
    *,
    target: Path,
    profile_provider: ProfileProvider,
    host: str = "rardar-prod",
    remote_root: str = "/var/lib/rardar/data",
    runner: RemoteRunner = ssh_discover_runner,
    source_dir: Path | None = None,
) -> DiscoverSyncResult:
    if not target.is_absolute() or os.path.normcase(str(target)) != os.path.normcase(os.path.normpath(target)):
        raise DiscoverSyncError("rardar_discover_sync_invalid_configuration", "Local mirror path is invalid")
    _ensure_chain(target.parent)
    lock = target.parent / f".{target.name}.discover-sync.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise DiscoverSyncError("rardar_discover_sync_already_running", "Another Discover sync is running") from exc
    stage: Path | None = None
    created_generation: Path | None = None
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        raw_bundle = local_discover_runner(source_dir) if source_dir is not None else runner(host, remote_root)
        bundle, pointer_raw, files = _decode(raw_bundle)
        generation_id = bundle["generationId"]
        if hashlib.sha256(files["manifest.json"]).hexdigest() != bundle["manifestSha256"]:
            raise DiscoverSyncError("rardar_discover_sync_bundle_invalid", "Discover manifest changed in transit")
        if hashlib.sha256(files["discover.json"]).hexdigest() != bundle["artifactSha256"]:
            raise DiscoverSyncError("rardar_discover_sync_bundle_invalid", "Discover artifact changed in transit")
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.discover-stage-", dir=target.parent))
        stage_store = stage.joinpath(*DISCOVER_ROOT.split("/"))
        generation_stage = stage_store / "generations" / generation_id
        for relative, content in files.items():
            path = generation_stage.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        stage_store.mkdir(parents=True, exist_ok=True)
        (stage_store / "current.json").write_bytes(pointer_raw)
        loaded = DiscoverArtifactAdapter.from_config(str(stage)).load()
        if loaded.board.discoverGenerationId != generation_id:
            raise DiscoverSyncError("rardar_discover_sync_bundle_invalid", "Discover generation identity changed")
        _ensure_chain(target)
        raw_store = target.joinpath(*DISCOVER_ROOT.split("/"))
        _ensure_chain(raw_store / "generations")
        final_generation = raw_store / "generations" / generation_id
        raw_pointer_path = raw_store / "current.json"
        serving_pointer_path = target / "discover-serving" / "current.json"
        serving_source_path = target / "discover-serving" / "sources" / f"{generation_id}.json"
        metadata_path = target / "discover-sync" / "generations" / f"{generation_id}.json"
        old_raw_pointer = _optional(raw_pointer_path)
        old_serving_pointer = _optional(serving_pointer_path)
        old_serving_source = _optional(serving_source_path)
        old_metadata = _optional(metadata_path)
        synced_at = datetime.now(UTC)
        source_host = "local-isolated-copy" if source_dir is not None else host
        metadata_matches = False
        if old_metadata:
            with suppress(Exception):
                existing = _strict_json(old_metadata)
                if (
                    existing.get("sourceHost") == source_host
                    and existing.get("generationId") == generation_id
                    and existing.get("manifestSha256") == bundle["manifestSha256"]
                    and existing.get("artifactSha256") == bundle["artifactSha256"]
                    and existing.get("latestCaptureId") == loaded.board.latestCaptureId
                    and existing.get("publishedCount") == loaded.board.coverage.publishedCount
                    and existing.get("fileCount") == len(files)
                ):
                    synced_at = datetime.fromisoformat(str(existing["syncedAt"]).replace("Z", "+00:00"))
                    if synced_at.tzinfo is None:
                        raise ValueError("stored sync time lacks a timezone")
                    metadata_matches = existing.get("projectionVersion") == DISCOVER_SERVING_PROJECTION_VERSION
        if (
            metadata_matches
            and old_raw_pointer == pointer_raw
            and old_serving_pointer is not None
            and old_serving_source == old_serving_pointer
            and _identical(final_generation, files)
        ):
            activated = DiscoverArtifactAdapter.from_config(str(target)).load()
            serving, _ = DiscoverServingLoader(target).load_with_etag()
            if (
                activated.board.discoverGenerationId == generation_id
                and activated.manifest_sha256 == bundle["manifestSha256"]
                and activated.artifact_sha256 == bundle["artifactSha256"]
                and serving.discoverGenerationId == generation_id
            ):
                return DiscoverSyncResult(
                    discover_generation_id=generation_id,
                    serving_generation_id=serving.servingGenerationId,
                    manifest_sha256=bundle["manifestSha256"],
                    artifact_sha256=bundle["artifactSha256"],
                    latest_capture_id=loaded.board.latestCaptureId,
                    published_count=loaded.board.coverage.publishedCount,
                    changed=False,
                    github_requests=0,
                    readme_cache_hits=0,
                    translation_calls=0,
                    translation_cache_hits=0,
                )
        built = build_discover_serving(
            loaded,
            cache_root=target / "discover-profile-cache",
            profile_provider=profile_provider,
            synced_at=synced_at,
            source_host=source_host,
        )
        raw_files = files
        if final_generation.exists():
            if not _identical(final_generation, raw_files):
                raise DiscoverSyncError(
                    "rardar_discover_sync_generation_conflict", "Immutable Discover generation differs"
                )
        else:
            candidate = raw_store / "generations" / f".{generation_id}.candidate-{os.getpid()}"
            for relative, content in raw_files.items():
                path = candidate.joinpath(*relative.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            os.replace(candidate, final_generation)
            created_generation = final_generation

        metadata = {
            "schemaVersion": 1,
            "projectionVersion": DISCOVER_SERVING_PROJECTION_VERSION,
            "syncedAt": synced_at.isoformat(),
            "sourceHost": source_host,
            "generationId": generation_id,
            "manifestSha256": bundle["manifestSha256"],
            "artifactSha256": bundle["artifactSha256"],
            "latestCaptureId": loaded.board.latestCaptureId,
            "publishedCount": loaded.board.coverage.publishedCount,
            "fileCount": len(files),
        }
        metadata_raw = (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        installed = None
        created_serving_generation: Path | None = None
        try:
            installed = install_discover_serving(target, built)
            if installed.created:
                created_serving_generation = (
                    target / "discover-serving" / "generations" / installed.serving_generation_id
                )
            _atomic(metadata_path, metadata_raw)
            _atomic(raw_pointer_path, pointer_raw)
            activated = DiscoverArtifactAdapter.from_config(str(target)).load()
            serving, _ = DiscoverServingLoader(target).load_with_etag()
            if activated.board.discoverGenerationId != generation_id or serving.discoverGenerationId != generation_id:
                raise DiscoverSyncError("rardar_discover_sync_activation_failed", "Discover pointers did not activate")
        except Exception:
            for path, old in (
                (raw_pointer_path, old_raw_pointer),
                (metadata_path, old_metadata),
                (serving_pointer_path, old_serving_pointer),
                (serving_source_path, old_serving_source),
            ):
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic(path, old)
            clear_discover_serving_cache()
            if created_generation is not None:
                shutil.rmtree(created_generation, ignore_errors=True)
                created_generation = None
            if created_serving_generation is not None:
                shutil.rmtree(created_serving_generation, ignore_errors=True)
            raise
        profile = built.profile_result
        changed = old_raw_pointer != pointer_raw or old_metadata != metadata_raw or installed.changed
        return DiscoverSyncResult(
            discover_generation_id=generation_id,
            serving_generation_id=built.serving_generation_id,
            manifest_sha256=bundle["manifestSha256"],
            artifact_sha256=bundle["artifactSha256"],
            latest_capture_id=loaded.board.latestCaptureId,
            published_count=loaded.board.coverage.publishedCount,
            changed=changed,
            github_requests=profile.github_requests,
            readme_cache_hits=profile.readme_cache_hits,
            translation_calls=profile.translation_calls,
            translation_cache_hits=profile.translation_cache_hits,
        )
    except DiscoverSyncError:
        raise
    except DiscoverServingError as exc:
        raise DiscoverSyncError(exc.code, "Discover Serving activation failed") from exc
    except Exception as exc:
        raise DiscoverSyncError("rardar_discover_sync_failed", "Discover mirror was not changed") from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        if created_generation is not None and not (target.joinpath(*DISCOVER_ROOT.split("/"), "current.json").exists()):
            shutil.rmtree(created_generation, ignore_errors=True)
        lock.unlink(missing_ok=True)


__all__ = [
    "DiscoverSyncError",
    "DiscoverSyncResult",
    "local_discover_runner",
    "ssh_discover_runner",
    "sync_discover_intelligence",
]
