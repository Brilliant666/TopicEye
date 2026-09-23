"""Private, bounded replay samples for public-repository material generation.

This is not a response cache or a source of publishable content. A sample is
captured before JSON/schema parsing, then retained only when validation fails
or a field is explicitly isolated. Nothing in this module calls a provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.services.llm.provider_budget import ProviderBudgetError, plain

SCHEMA_VERSION = 1
RETENTION_DAYS = 14
MAX_SAMPLES_PER_REPOSITORY = 32
MAX_RAW_BYTES = 256 * 1024
MAX_INPUT_BYTES = 256 * 1024
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
MAX_RECORD_BYTES = 3 * 1024 * 1024
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SAMPLE_ID = re.compile(r"[0-9a-f]{32}\Z")
_SAFE_TAG = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_SAFE_MODEL = re.compile(r"[A-Za-z0-9_./-]{1,160}\Z")
_SAFE_REASON = re.compile(r"[A-Za-z0-9_.:\[\]-]{1,160}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_KNOWN_FIELDS = frozenset(
    {
        "summary",
        "positioning",
        "positioningZh",
        "includedEvidenceRefs",
        "includedRoles",
        "excludedClauses",
        "capabilities",
        "keyDifferentiators",
        "coreValue",
        "productForms",
        "supportedEnvironments",
        "useCases",
        "deliveryForms",
        "title",
        "detail",
        "shortDetail",
        "sourceMode",
        "text",
        "evidenceRefs",
        "role",
    }
)
_SENSITIVE = re.compile(
    r"(?:-----BEGIN (?:OPENSSH|RSA|EC|PRIVATE) KEY-----|"
    r"\b(?:authorization|cookie|set-cookie)\s*[:=]\s*\S+|"
    r"\b(?:api[_-]?key|access[_-]?token|github[_-]?token|password|secret)\s*[:=]\s*['\"]?\S+|"
    r"\b(?:postgres(?:ql)?|mysql)://[^\s]+@|\bsk-[A-Za-z0-9_-]{16,})",
    re.IGNORECASE,
)
_CAPTURE: ContextVar[FailureSampleContext | None] = ContextVar("rardar_material_failure_sample", default=None)
_OPERATION: ContextVar[str | None] = ContextVar("rardar_material_recovery_operation", default=None)


class SampleStoreUnavailable(RuntimeError):
    """Fail closed when a material output cannot be retained safely."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass
class FailureSampleContext:
    cache_root: Path
    repository: str
    repository_id: int
    stage: str
    attempt: int
    operation_id: str | None
    input_payload: dict[str, Any]
    evidence: dict[str, Any]
    rule_version: str
    sample: SampleRef | None = field(default=None, init=False)

    @property
    def sample_ref(self) -> SampleRef | None:
        return self.sample


@dataclass(frozen=True)
class SampleRef:
    path: Path
    sample_id: str
    cache_root: Path


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bounded(value: object, maximum: int, label: str) -> bytes:
    try:
        raw = _canonical(value)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SampleStoreUnavailable(f"failure_sample_{label}_invalid") from exc
    if len(raw) > maximum:
        raise SampleStoreUnavailable(f"failure_sample_{label}_oversized")
    if _SENSITIVE.search(raw.decode("utf-8")):
        raise SampleStoreUnavailable("failure_sample_sensitive_content")
    return raw


def _directory(path: Path) -> None:
    plain(path, missing=True)
    if not path.exists():
        path.mkdir(mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (os.name != "nt" and info.st_mode & 0o077):
        raise SampleStoreUnavailable("failure_sample_directory_permissions")


def _root(cache_root: Path) -> Path:
    if not cache_root.is_absolute():
        raise SampleStoreUnavailable("failure_sample_root_invalid")
    plain(cache_root, missing=True)
    if not cache_root.exists():
        plain(cache_root.parent)
        cache_root.mkdir(mode=0o700)
    plain(cache_root)
    if not cache_root.is_dir():
        raise SampleStoreUnavailable("failure_sample_root_invalid")
    parent = cache_root / "failure-samples"
    _directory(parent)
    version = parent / "v1"
    _directory(version)
    return version


def preflight(cache_root: Path) -> Path:
    """Verify private, durable local storage before the first outbound request."""
    try:
        root = _root(cache_root)
        descriptor, name = tempfile.mkstemp(prefix=".probe-", dir=root)
        try:
            if os.name != "nt":
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(b"probe\n")
                handle.flush()
                os.fsync(handle.fileno())
            if Path(name).read_bytes() != b"probe\n":
                raise SampleStoreUnavailable("failure_sample_probe_mismatch")
        finally:
            with suppress(FileNotFoundError):
                os.unlink(name)
        return root
    except SampleStoreUnavailable:
        raise
    except (OSError, ValueError, ProviderBudgetError) as exc:
        raise SampleStoreUnavailable("failure_sample_store_unavailable") from exc


@contextmanager
def failure_sample_scope(context: FailureSampleContext) -> Iterator[FailureSampleContext]:
    if (
        not _REPOSITORY.fullmatch(context.repository)
        or type(context.repository_id) is not int
        or context.repository_id < 1
    ):
        raise SampleStoreUnavailable("failure_sample_identity_invalid")
    if context.stage not in {"translation", "positioning"} or type(context.attempt) is not int or context.attempt < 1:
        raise SampleStoreUnavailable("failure_sample_stage_invalid")
    if context.operation_id is not None and not _SAFE_TAG.fullmatch(context.operation_id):
        raise SampleStoreUnavailable("failure_sample_operation_invalid")
    if not _SAFE_TAG.fullmatch(context.rule_version):
        raise SampleStoreUnavailable("failure_sample_rule_version_invalid")
    if not isinstance(context.input_payload, dict) or not isinstance(context.evidence, dict):
        raise SampleStoreUnavailable("failure_sample_source_identity_mismatch")
    if (
        context.input_payload.get("repository") != context.repository
        or context.evidence.get("repository") != context.repository
        or context.evidence.get("githubRepositoryId") != context.repository_id
    ):
        raise SampleStoreUnavailable("failure_sample_source_identity_mismatch")
    selected = context.input_payload.get("evidenceIndex")
    complete = context.evidence.get("evidenceIndex")
    if selected is not None and (
        not isinstance(selected, dict)
        or not isinstance(complete, dict)
        or any(
            not isinstance(value, str) or not isinstance(complete.get(key), str) or not complete[key].startswith(value)
            for key, value in selected.items()
        )
    ):
        raise SampleStoreUnavailable("failure_sample_source_evidence_mismatch")
    # These checks are deterministic from already-saved public input. Run them
    # before dispatch, not after spending a Provider request.
    _bounded(context.input_payload, MAX_INPUT_BYTES, "input")
    _bounded(context.evidence, MAX_EVIDENCE_BYTES, "evidence")
    if _CAPTURE.get() is not None:
        raise SampleStoreUnavailable("failure_sample_nested_scope")
    # Preflight is intentionally before the caller's model/source dispatch.
    preflight(context.cache_root)
    token = _CAPTURE.set(context)
    try:
        yield context
    finally:
        _CAPTURE.reset(token)


def current_failure_sample() -> FailureSampleContext | None:
    return _CAPTURE.get()


@contextmanager
def operation_scope(authorization_id: str) -> Iterator[None]:
    """Bind an existing recovery grant to all of its nested material attempts."""
    if not _SAFE_TAG.fullmatch(authorization_id) or _OPERATION.get() is not None:
        raise SampleStoreUnavailable("failure_sample_operation_invalid")
    token = _OPERATION.set(authorization_id)
    try:
        yield
    finally:
        _OPERATION.reset(token)


def current_operation_id() -> str | None:
    return _OPERATION.get()


def _atomic(path: Path, raw: bytes) -> None:
    if len(raw) > MAX_RECORD_BYTES:
        raise SampleStoreUnavailable("failure_sample_record_oversized")
    plain(path, missing=True)
    descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(name)
        raise


def _read(ref: SampleRef) -> dict[str, Any]:
    plain(ref.path)
    info = ref.path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or (os.name != "nt" and info.st_mode & 0o077)
        or info.st_size > MAX_RECORD_BYTES
    ):
        raise SampleStoreUnavailable("failure_sample_file_unsafe")
    raw = ref.path.read_bytes()
    if len(raw) != info.st_size:
        raise SampleStoreUnavailable("failure_sample_file_changed")
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise SampleStoreUnavailable("failure_sample_file_invalid") from exc
    if not isinstance(value, dict) or value.get("sampleId") != ref.sample_id:
        raise SampleStoreUnavailable("failure_sample_file_invalid")
    expected = value.pop("recordDigest", None)
    if not isinstance(expected, str) or not _SHA.fullmatch(expected) or _digest(_canonical(value)) != expected:
        raise SampleStoreUnavailable("failure_sample_digest_mismatch")
    value["recordDigest"] = expected
    return value


def _write(ref: SampleRef, value: dict[str, Any]) -> None:
    body = {key: item for key, item in value.items() if key != "recordDigest"}
    body["recordDigest"] = _digest(_canonical(body))
    _atomic(ref.path, _canonical(body))


def _metadata(value: dict[str, Any]) -> dict[str, Any]:
    # No endpoint, headers, route secrets, prompt, or provider body.
    result: dict[str, Any] = {}
    for key in ("actual_model", "request_model", "provider", "model_id", "cache_hit"):
        item = value.get(key)
        if (key == "cache_hit" and type(item) is bool) or (
            key != "cache_hit" and isinstance(item, str) and _SAFE_MODEL.fullmatch(item)
        ):
            result[key] = item
    return result


def capture_raw(
    raw: str,
    provider_metadata: dict[str, Any],
    *,
    model_name: str,
    prompt_version: str,
    schema_version: str,
) -> SampleRef | None:
    """Persist the exact business response before strict JSON/Pydantic parsing."""
    context = current_failure_sample()
    if context is None:
        return None
    if context.sample is not None:
        raise SampleStoreUnavailable("failure_sample_duplicate_capture")
    if not all(_SAFE_TAG.fullmatch(value) for value in (model_name, prompt_version, schema_version)):
        raise SampleStoreUnavailable("failure_sample_model_identity_invalid")
    if not isinstance(raw, str):
        raise SampleStoreUnavailable("failure_sample_raw_invalid")
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_RAW_BYTES:
        raise SampleStoreUnavailable("failure_sample_raw_oversized")
    if _SENSITIVE.search(raw):
        raise SampleStoreUnavailable("failure_sample_sensitive_content")
    input_raw = _bounded(context.input_payload, MAX_INPUT_BYTES, "input")
    evidence_raw = _bounded(context.evidence, MAX_EVIDENCE_BYTES, "evidence")
    root = preflight(context.cache_root)
    directory = root / str(context.repository_id)
    _directory(directory)
    _prune(directory)
    sample_id = uuid4().hex
    ref = SampleRef(path=directory / f"{sample_id}.json", sample_id=sample_id, cache_root=context.cache_root)
    value = {
        "schemaVersion": SCHEMA_VERSION,
        "sampleId": sample_id,
        "state": "pending",
        "capturedAt": datetime.now(UTC).isoformat(),
        "repository": context.repository,
        "repositoryId": context.repository_id,
        "operationId": context.operation_id,
        "stage": context.stage,
        "attempt": context.attempt,
        "modelClass": model_name,
        "promptVersion": prompt_version,
        "schemaVersionName": schema_version,
        "ruleVersion": context.rule_version,
        "provider": _metadata(provider_metadata),
        "inputPayload": context.input_payload,
        "inputDigest": _digest(input_raw),
        "evidence": context.evidence,
        "evidenceDigest": _digest(evidence_raw),
        "raw": raw,
        "rawSha256": _digest(encoded),
        "result": None,
    }
    try:
        _write(ref, value)
        context.sample = ref
        return ref
    except SampleStoreUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise SampleStoreUnavailable("failure_sample_store_unavailable") from exc


def _safe_error(error: Exception) -> dict[str, Any]:
    from app.services.llm.strict_json import StrictJSONError
    from app.services.rardar_llm_control import RardarLLMError

    if isinstance(error, StrictJSONError):
        code = "empty" if "empty" in str(error).casefold() else "invalid_json"
        return {
            "errorClass": "StrictJSONError",
            "code": code,
            "validationStage": "json_parse",
            "fieldPath": "$",
        }

    if isinstance(error, RardarLLMError):
        return {
            "errorClass": "RardarLLMError",
            "code": error.code if _SAFE_TAG.fullmatch(error.code) else "unknown",
            "classification": error.classification
            if isinstance(error.classification, str) and _SAFE_TAG.fullmatch(error.classification)
            else None,
            "validationStage": error.validation_stage
            if isinstance(error.validation_stage, str) and _SAFE_TAG.fullmatch(error.validation_stage)
            else None,
            "fieldPath": error.field_path
            if isinstance(error.field_path, str) and re.fullmatch(r"\$[A-Za-z0-9_.\[\]<>-]{0,150}", error.field_path)
            else None,
            "validationType": error.validation_type
            if isinstance(error.validation_type, str) and _SAFE_TAG.fullmatch(error.validation_type)
            else None,
        }
    if isinstance(error, ValidationError):
        first = error.errors(include_input=False, include_context=False, include_url=False)[0]
        path = [x if type(x) is int else x if x in _KNOWN_FIELDS else "<extra-field>" for x in first["loc"][:12]]
        return {
            "errorClass": "ValidationError",
            "code": "schema_invalid",
            "validationType": first["type"],
            "fieldPath": path,
        }
    name = type(error).__name__
    message = str(error)
    return {
        "errorClass": name if _SAFE_TAG.fullmatch(name) else "unknown",
        "code": message if _SAFE_TAG.fullmatch(message) else "unknown",
    }


def finish_sample(
    ref: SampleRef | None,
    *,
    error: Exception | None,
    normalized: object | None = None,
    isolation_reasons: list[str] | None = None,
) -> None:
    """Retain failure/isolated samples; remove clean successes."""
    if ref is None:
        return
    try:
        value = _read(ref)
        if value["state"] != "pending":
            return  # an inner JSON/schema failure was already finalized
        if error is None and not isolation_reasons:
            ref.path.unlink()
            return
        reasons = isolation_reasons or []
        if len(reasons) > 12 or any(not isinstance(item, str) or not _SAFE_REASON.fullmatch(item) for item in reasons):
            raise SampleStoreUnavailable("failure_sample_reason_invalid")
        if normalized is not None:
            _bounded(normalized, MAX_INPUT_BYTES, "normalized")
        value["state"] = "failed" if error is not None else "isolated"
        value["result"] = {
            "error": _safe_error(error) if error is not None else None,
            "isolatedFields": reasons,
            "normalized": normalized,
            "finishedAt": datetime.now(UTC).isoformat(),
        }
        _write(ref, value)
    except SampleStoreUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise SampleStoreUnavailable("failure_sample_store_unavailable") from exc


def _prune(directory: Path) -> None:
    """Bound only this store; never touch source/cache/receipt files."""
    threshold = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    items: list[tuple[datetime, Path]] = []
    for count, path in enumerate(directory.iterdir(), 1):
        if count > 128:
            raise SampleStoreUnavailable("failure_sample_repository_inventory_unbounded")
        if not _SAMPLE_ID.fullmatch(path.stem) or path.suffix != ".json":
            continue
        plain(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SampleStoreUnavailable("failure_sample_file_unsafe")
        items.append((datetime.fromtimestamp(info.st_mtime, UTC), path))
    for modified, path in sorted(items):
        if modified < threshold:
            path.unlink()
    remaining = sorted(((when, path) for when, path in items if path.exists()))
    if len(remaining) >= MAX_SAMPLES_PER_REPOSITORY:
        # Do not silently discard recent failed evidence to make room.
        raise SampleStoreUnavailable("failure_sample_repository_limit")


def load_sample(cache_root: Path, repository_id: int, sample_id: str) -> dict[str, Any]:
    """Operator-only read of a fixed repository/sample ID under the private root."""
    if type(repository_id) is not int or repository_id < 1 or not _SAMPLE_ID.fullmatch(sample_id):
        raise SampleStoreUnavailable("failure_sample_identity_invalid")
    root = _root(cache_root)
    directory = root / str(repository_id)
    plain(directory)
    if not directory.is_dir():
        raise SampleStoreUnavailable("failure_sample_missing")
    ref = SampleRef(directory / f"{sample_id}.json", sample_id, cache_root)
    value = _read(ref)
    if value.get("repositoryId") != repository_id or value.get("schemaVersion") != SCHEMA_VERSION:
        raise SampleStoreUnavailable("failure_sample_identity_invalid")
    if _digest(_bounded(value.get("inputPayload"), MAX_INPUT_BYTES, "input")) != value.get("inputDigest"):
        raise SampleStoreUnavailable("failure_sample_input_digest_mismatch")
    if _digest(_bounded(value.get("evidence"), MAX_EVIDENCE_BYTES, "evidence")) != value.get("evidenceDigest"):
        raise SampleStoreUnavailable("failure_sample_evidence_digest_mismatch")
    if not isinstance(value.get("raw"), str) or _digest(value["raw"].encode("utf-8")) != value.get("rawSha256"):
        raise SampleStoreUnavailable("failure_sample_raw_digest_mismatch")
    return value
