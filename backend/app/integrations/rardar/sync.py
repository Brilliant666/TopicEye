"""Read-only Production Artifact sync into an atomic local Rardar mirror."""

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

from app.integrations.rardar.adapter import (
    RardarArtifactError,
    RardarIntelligenceAdapter,
    _SafeRoot,
    _strict_json,
)

_GENERATION_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_HOST_ALIAS = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_REPARSE_POINT = 0x400
_MAX_BUNDLE_BYTES = 64 * 1024 * 1024


class RardarSyncError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RardarSyncResult:
    generation_id: str
    window_state: str
    exact_count: int
    pending_count: int
    manifest_sha256: str
    artifact_sha256: str
    file_count: int
    synced_at: str
    changed: bool


RemoteRunner = Callable[[str, str], bytes]


_REMOTE_PROGRAM = r"""
import base64, hashlib, json, os, re, stat, sys
from pathlib import PurePosixPath

ROOT = __REMOTE_ROOT__
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

pointer_raw = read_stable("current.json", 65536)
pointer = object_value(pointer_raw)
generation_id = pointer.get("generationId")
if not isinstance(generation_id, str) or not GENERATION.fullmatch(generation_id):
    raise RuntimeError("unsafe_generation")

manifest_relative = "generations/%s/manifest.json" % generation_id
manifest_raw = read_stable(manifest_relative, 4 * 1024 * 1024)
manifest = object_value(manifest_raw)
manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
if pointer.get("manifestSha256") != manifest_sha or manifest.get("generationId") != generation_id or manifest.get("state") != "ready":
    raise RuntimeError("manifest_mismatch")
artifacts = manifest.get("artifacts")
hashes = manifest.get("hashes")
if not isinstance(artifacts, list) or not isinstance(hashes, dict) or len(artifacts) != len(set(artifacts)) or set(artifacts) != set(hashes):
    raise RuntimeError("manifest_inventory_invalid")

explosion_relative = "trending/explosion.json"
if explosion_relative not in hashes:
    raise RuntimeError("explosion_not_published")
explosion_raw = read_stable("generations/%s/%s" % (generation_id, explosion_relative))
if hashlib.sha256(explosion_raw).hexdigest() != hashes[explosion_relative]:
    raise RuntimeError("explosion_hash_invalid")
explosion = object_value(explosion_raw)
if explosion.get("generationId") != generation_id:
    raise RuntimeError("explosion_generation_mismatch")

captures = explosion.get("sourceCaptures")
if not isinstance(captures, dict) or not isinstance(captures.get("current"), dict):
    raise RuntimeError("source_inventory_invalid")
references = [captures["current"]]
if captures.get("baseline") is not None:
    references.append(captures["baseline"])
references.extend(captures.get("partial") or [])
if captures.get("coverageWitness") is not None:
    references.append(captures["coverageWitness"])

files = {"manifest.json": manifest_raw, explosion_relative: explosion_raw}
for reference in references:
    if not isinstance(reference, dict):
        raise RuntimeError("source_reference_invalid")
    relative = reference.get("generationRelativePath")
    if not isinstance(relative, str) or relative not in hashes or relative not in artifacts:
        raise RuntimeError("source_manifest_mismatch")
    raw = read_stable("generations/%s/%s" % (generation_id, relative))
    digest = hashlib.sha256(raw).hexdigest()
    if digest != hashes[relative] or digest != reference.get("fileSha256"):
        raise RuntimeError("source_hash_invalid")
    files[relative] = raw

if read_stable("current.json", 65536) != pointer_raw or read_stable(manifest_relative, 4 * 1024 * 1024) != manifest_raw:
    raise RuntimeError("publication_changed_during_inventory")

payload = {
    "schemaVersion": 1,
    "generationId": generation_id,
    "current": base64.b64encode(pointer_raw).decode("ascii"),
    "files": {key: base64.b64encode(value).decode("ascii") for key, value in files.items()},
    "manifestSha256": manifest_sha,
    "artifactSha256": hashes[explosion_relative],
    "windowState": explosion["window"]["state"],
    "exactCount": len(explosion["exactRanked"]),
    "pendingCount": len(explosion["pendingRanked"]),
}
sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
"""


def _remote_program(remote_root: str) -> str:
    if not remote_root.startswith("/") or "\x00" in remote_root:
        raise RardarSyncError("rardar_sync_invalid_configuration", "Remote data root must be an absolute POSIX path")
    return _REMOTE_PROGRAM.replace("__REMOTE_ROOT__", repr(remote_root))


def ssh_read_only_runner(host: str, remote_root: str) -> bytes:
    if not _HOST_ALIAS.fullmatch(host):
        raise RardarSyncError("rardar_sync_invalid_configuration", "Rardar SSH host alias is invalid")
    try:
        completed = subprocess.run(
            ["ssh", host, "sudo", "-n", "python3", "-"],
            input=_remote_program(remote_root).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RardarSyncError("rardar_sync_remote_unavailable", "Read-only Rardar inventory failed") from exc
    if completed.returncode != 0:
        raise RardarSyncError("rardar_sync_remote_rejected", "Read-only Rardar inventory was rejected")
    if len(completed.stdout) > _MAX_BUNDLE_BYTES:
        raise RardarSyncError("rardar_sync_bundle_too_large", "Rardar sync bundle exceeded the local limit")
    return completed.stdout


def _decode_bundle(raw: bytes) -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
    try:
        bundle = _strict_json(raw)
        expected = {
            "schemaVersion",
            "generationId",
            "current",
            "files",
            "manifestSha256",
            "artifactSha256",
            "windowState",
            "exactCount",
            "pendingCount",
        }
        if set(bundle) != expected or bundle["schemaVersion"] != 1:
            raise ValueError("unexpected bundle fields")
        generation_id = bundle["generationId"]
        if not isinstance(generation_id, str) or not _GENERATION_ID.fullmatch(generation_id):
            raise ValueError("unsafe generation")
        if not _SHA256.fullmatch(str(bundle["manifestSha256"])) or not _SHA256.fullmatch(str(bundle["artifactSha256"])):
            raise ValueError("invalid digest")
        if bundle["windowState"] not in {"exact", "warming_up", "baseline_missing"}:
            raise ValueError("invalid window state")
        if (
            not isinstance(bundle["exactCount"], int)
            or isinstance(bundle["exactCount"], bool)
            or not isinstance(bundle["pendingCount"], int)
            or isinstance(bundle["pendingCount"], bool)
        ):
            raise ValueError("invalid counts")
        pointer_raw = base64.b64decode(bundle["current"], validate=True)
        encoded_files = bundle["files"]
        if (
            not isinstance(encoded_files, dict)
            or "manifest.json" not in encoded_files
            or "trending/explosion.json" not in encoded_files
        ):
            raise ValueError("incomplete bundle")
        files: dict[str, bytes] = {}
        for relative, encoded in encoded_files.items():
            if not isinstance(relative, str) or not isinstance(encoded, str):
                raise ValueError("invalid file entry")
            parsed = PurePosixPath(relative)
            if parsed.is_absolute() or not parsed.parts or any(part in {"", ".", ".."} for part in parsed.parts):
                raise ValueError("unsafe bundle path")
            files[relative] = base64.b64decode(encoded, validate=True)
        if sum(map(len, files.values())) + len(pointer_raw) > _MAX_BUNDLE_BYTES:
            raise ValueError("bundle too large")
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RardarSyncError("rardar_sync_bundle_invalid", "Rardar sync bundle failed local validation") from exc
    return bundle, pointer_raw, files


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _assert_plain_directory(path: Path) -> None:
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise RardarSyncError("rardar_sync_unsafe_local_path", "Local mirror path is not a plain directory")


def _ensure_plain_directory_chain(path: Path) -> None:
    """Create missing directories while rejecting links/reparse points in every component."""

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
            raise RardarSyncError("rardar_sync_unsafe_local_path", "Local mirror path contains an unsafe component")


def _read_optional_plain_file(path: Path) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise RardarSyncError("rardar_sync_unsafe_local_path", "Local mirror metadata is not a plain file")
    return path.read_bytes()


def _write_file(root: Path, relative: str, raw: bytes) -> None:
    parsed = PurePosixPath(relative)
    path = root.joinpath(*parsed.parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _atomic_bytes(path: Path, raw: bytes) -> None:
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


def _plain_file_inventory(root: Path) -> set[str]:
    safe = _SafeRoot(str(root))
    safe.ensure_available()
    paths: set[str] = set()
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        _assert_plain_directory(directory_path)
        for name in directories:
            _assert_plain_directory(directory_path / name)
        for name in filenames:
            path = directory_path / name
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise RardarSyncError(
                    "rardar_sync_unsafe_local_path", "Existing local generation contains an unsafe file"
                )
            paths.add((path.relative_to(root)).as_posix())
    return paths


def _identical_generation(target: Path, files: dict[str, bytes]) -> bool:
    safe = _SafeRoot(str(target))
    safe.ensure_available()
    for relative, expected in files.items():
        try:
            actual = safe.read_stable(relative, maximum_bytes=max(len(expected), 1))
        except (FileNotFoundError, OSError, ValueError, RardarArtifactError):
            return False
        if actual != expected:
            return False
    expected_paths = set(files)
    actual_paths = _plain_file_inventory(target)
    return actual_paths == expected_paths


def sync_rardar_intelligence(
    *,
    target: Path,
    host: str = "rardar-prod",
    remote_root: str = "/var/lib/rardar/data",
    runner: RemoteRunner = ssh_read_only_runner,
) -> RardarSyncResult:
    """Download, validate, and atomically activate one immutable generation."""

    if not target.is_absolute() or os.path.normcase(str(target)) != os.path.normcase(os.path.normpath(target)):
        raise RardarSyncError("rardar_sync_invalid_configuration", "Local mirror must be an absolute normalized path")
    if not _HOST_ALIAS.fullmatch(host):
        raise RardarSyncError("rardar_sync_invalid_configuration", "Rardar source host alias is invalid")
    _ensure_plain_directory_chain(target.parent)
    lock_path = target.parent / f".{target.name}.sync.lock"
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RardarSyncError("rardar_sync_already_running", "Another Rardar sync is already running") from exc

    stage: Path | None = None
    created_generation: Path | None = None
    activated_successfully = False
    try:
        with os.fdopen(lock_descriptor, "w", encoding="ascii") as lock:
            lock.write(str(os.getpid()))
            lock.flush()
        bundle, pointer_raw, files = _decode_bundle(runner(host, remote_root))
        generation_id = bundle["generationId"]
        if hashlib.sha256(files["manifest.json"]).hexdigest() != bundle["manifestSha256"]:
            raise RardarSyncError("rardar_sync_bundle_invalid", "Manifest digest changed in transit")
        if hashlib.sha256(files["trending/explosion.json"]).hexdigest() != bundle["artifactSha256"]:
            raise RardarSyncError("rardar_sync_bundle_invalid", "Explosion digest changed in transit")

        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
        _write_file(stage, "current.json", pointer_raw)
        for relative, content in files.items():
            _write_file(stage / "generations" / generation_id, relative, content)
        board = RardarIntelligenceAdapter.from_config(str(stage)).load_explosion_board()
        if (
            board.generationId != generation_id
            or (board.window and board.window.state != bundle["windowState"])
            or board.coverage is None
            or board.coverage.exactCount != bundle["exactCount"]
            or board.coverage.pendingCount != bundle["pendingCount"]
        ):
            raise RardarSyncError("rardar_sync_bundle_invalid", "Validated Rardar facts do not match inventory")

        synced_at = datetime.now(UTC).isoformat()
        metadata = {
            "schemaVersion": 1,
            "syncedAt": synced_at,
            "sourceHost": host,
            "generationId": generation_id,
            "manifestSha256": bundle["manifestSha256"],
            "artifactSha256": bundle["artifactSha256"],
            "windowState": bundle["windowState"],
            "exactCount": bundle["exactCount"],
            "pendingCount": bundle["pendingCount"],
            "fileCount": len(files),
        }
        metadata_raw = (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

        _ensure_plain_directory_chain(target)
        _ensure_plain_directory_chain(target / "generations")
        _ensure_plain_directory_chain(target / "sync" / "generations")
        target_generation = target / "generations" / generation_id
        try:
            os.lstat(target_generation)
            target_generation_exists = True
        except FileNotFoundError:
            target_generation_exists = False
        if target_generation_exists:
            _assert_plain_directory(target_generation)
            if not _identical_generation(target_generation, files):
                raise RardarSyncError(
                    "rardar_sync_generation_conflict", "Existing local generation differs from Production inventory"
                )

        metadata_path = target / "sync" / "generations" / f"{generation_id}.json"
        pointer_path = target / "current.json"
        old_metadata = _read_optional_plain_file(metadata_path)
        old_pointer = _read_optional_plain_file(pointer_path)
        changed = not target_generation_exists or old_pointer != pointer_raw
        if not target_generation_exists:
            os.replace(stage / "generations" / generation_id, target_generation)
            created_generation = target_generation

        metadata_replaced = False
        pointer_replaced = False
        try:
            _atomic_bytes(metadata_path, metadata_raw)
            metadata_replaced = True
            _atomic_bytes(pointer_path, pointer_raw)
            pointer_replaced = True
            activated = RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board()
            if activated.generationId != generation_id:
                raise RardarSyncError(
                    "rardar_sync_activation_failed", "Local pointer did not activate the validated generation"
                )
        except Exception:
            if pointer_replaced:
                if old_pointer is None:
                    pointer_path.unlink(missing_ok=True)
                else:
                    _atomic_bytes(pointer_path, old_pointer)
            if metadata_replaced:
                if old_metadata is None:
                    metadata_path.unlink(missing_ok=True)
                else:
                    _atomic_bytes(metadata_path, old_metadata)
            if created_generation is not None:
                shutil.rmtree(created_generation, ignore_errors=True)
                created_generation = None
            raise
        activated_successfully = True
        return RardarSyncResult(
            generation_id=generation_id,
            window_state=bundle["windowState"],
            exact_count=bundle["exactCount"],
            pending_count=bundle["pendingCount"],
            manifest_sha256=bundle["manifestSha256"],
            artifact_sha256=bundle["artifactSha256"],
            file_count=len(files),
            synced_at=synced_at,
            changed=changed,
        )
    except RardarSyncError:
        raise
    except RardarArtifactError as exc:
        raise RardarSyncError("rardar_sync_validation_failed", "Downloaded Rardar generation was rejected") from exc
    except Exception as exc:
        raise RardarSyncError("rardar_sync_failed", "Rardar local mirror was not changed") from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        if not activated_successfully and created_generation is not None:
            shutil.rmtree(created_generation, ignore_errors=True)
        lock_path.unlink(missing_ok=True)


def load_sync_metadata(configured: str, generation_id: str) -> dict[str, Any] | None:
    """Read non-secret mirror provenance that is versioned by generation."""

    if not _GENERATION_ID.fullmatch(generation_id):
        return None
    try:
        root = _SafeRoot(configured)
        root.ensure_available()
        raw = root.read_stable(f"sync/generations/{generation_id}.json", maximum_bytes=64 * 1024)
        value = _strict_json(raw)
        expected = {
            "schemaVersion",
            "syncedAt",
            "sourceHost",
            "generationId",
            "manifestSha256",
            "artifactSha256",
            "windowState",
            "exactCount",
            "pendingCount",
            "fileCount",
        }
        if set(value) != expected or value["schemaVersion"] != 1 or value["generationId"] != generation_id:
            return None
        parsed_time = datetime.fromisoformat(value["syncedAt"])
        if parsed_time.tzinfo is None or not _HOST_ALIAS.fullmatch(value["sourceHost"]):
            return None
        if not _SHA256.fullmatch(value["manifestSha256"]) or not _SHA256.fullmatch(value["artifactSha256"]):
            return None
        pointer_raw = root.read_stable("current.json", maximum_bytes=64 * 1024)
        pointer = _strict_json(pointer_raw)
        if pointer.get("generationId") != generation_id or pointer.get("manifestSha256") != value["manifestSha256"]:
            return None
        manifest_raw = root.read_stable(
            f"generations/{generation_id}/manifest.json",
            maximum_bytes=4 * 1024 * 1024,
        )
        manifest = _strict_json(manifest_raw)
        if hashlib.sha256(manifest_raw).hexdigest() != value["manifestSha256"]:
            return None
        if manifest.get("hashes", {}).get("trending/explosion.json") != value["artifactSha256"]:
            return None
        artifact_raw = root.read_stable(
            f"generations/{generation_id}/trending/explosion.json",
            maximum_bytes=16 * 1024 * 1024,
        )
        if hashlib.sha256(artifact_raw).hexdigest() != value["artifactSha256"]:
            return None
        return value
    except (FileNotFoundError, OSError, TypeError, ValueError, RardarArtifactError):
        return None
