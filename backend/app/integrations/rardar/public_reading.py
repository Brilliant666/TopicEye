"""Durable public reading products, built by writers and never by HTTP reads.

The existing atomic-file publication model is reused. Each view commits its
own immutable product so a failed historical build cannot block Today. Only
validated public output lives here; account state, Find runs and budgets do not.
"""

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.integrations.rardar.project_identity import canonical_repository, project_id_for_repository
from app.services.llm.provider_budget import ProviderBudgetError, atomic, digest, file_lock, plain

VIEWS = ("trending-today", "historical-hot")
_REVISION = re.compile(r"^[a-f0-9]{64}$")
_MAX_BYTES = 32 * 1024 * 1024


def _safe(path: Path, *, missing: bool = False) -> None:
    try:
        plain(path, missing=missing)
    except ProviderBudgetError:
        raise ValueError("public_reading_path_invalid") from None


def _root(target: Path) -> Path:
    root = target / "trending-boards" / "public-reading"
    _safe(root, missing=True)
    return root


def _view(value: str) -> str:
    if value not in VIEWS:
        raise ValueError("public_reading_view_invalid")
    return value


def _read(path: Path, maximum: int) -> dict:
    _safe(path)
    if path.stat().st_size > maximum:
        raise ValueError("public_reading_size_invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("public_reading_shape_invalid")
    return value


def current(target: Path) -> dict:
    """A small live pointer; no source/Profile reads, locks or writes."""
    path = _root(target) / "current.json"
    _safe(path, missing=True)
    if not path.exists():
        return {"schemaVersion": 1, "views": {}}
    value = _read(path, 16_000)
    if (
        set(value) != {"schemaVersion", "views"}
        or type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
    ):
        raise ValueError("public_reading_pointer_invalid")
    if not isinstance(value["views"], dict) or set(value["views"]) - set(VIEWS):
        raise ValueError("public_reading_pointer_invalid")
    for entry in value["views"].values():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"revision", "publishedAt", "generationId"}
            or not isinstance(entry["revision"], str)
            or not _REVISION.fullmatch(entry["revision"])
            or not isinstance(entry["publishedAt"], str)
            or datetime.fromisoformat(entry["publishedAt"]).tzinfo is None
            or (entry["generationId"] is not None and not isinstance(entry["generationId"], str))
        ):
            raise ValueError("public_reading_pointer_invalid")
    return value


def _validate(view: str, value: dict, *, candidate: bool = False) -> None:
    if set(value) != {"view", "board", "details", "identifiers"} or value["view"] != view:
        raise ValueError("public_reading_product_invalid")
    board, details, identifiers = value["board"], value["details"], value["identifiers"]
    if not isinstance(board, dict) or not isinstance(board.get("projects"), list):
        raise ValueError("public_reading_board_invalid")
    if not isinstance(details, dict) or not isinstance(identifiers, dict):
        raise ValueError("public_reading_details_invalid")
    seen = set()
    for project in board["projects"]:
        if not isinstance(project, dict):
            raise ValueError("public_reading_project_invalid")
        if not isinstance(project.get("repository"), str):
            raise ValueError("public_reading_project_invalid")
        repository = canonical_repository(project["repository"])
        identifier = project_id_for_repository(repository)
        numeric = project.get("githubRepositoryId")
        detail = details.get(identifier)
        if (
            project.get("projectId") != identifier
            or identifier in seen
            or project.get("repositoryUrl") != f"https://github.com/{repository}"
            or (numeric is not None and (type(numeric) is not int or numeric <= 0))
        ):
            raise ValueError("public_reading_identity_mismatch")
        if candidate:
            if (
                not isinstance(detail, dict)
                or detail.get("projectId") != identifier
                or detail.get("repository") != repository
                or detail.get("githubRepositoryId") != numeric
                or detail.get("generationId") != board.get("generationId")
            ):
                raise ValueError("public_reading_identity_mismatch")
        elif not isinstance(detail, str) or not _REVISION.fullmatch(detail):
            raise ValueError("public_reading_detail_reference_invalid")
        seen.add(identifier)
    if set(details) != seen:
        raise ValueError("public_reading_members_mismatch")
    for alias, identifier in identifiers.items():
        if not isinstance(alias, str) or not alias or len(alias) > 250 or identifier not in details:
            raise ValueError("public_reading_identifier_invalid")
        project = next(p for p in board["projects"] if p["projectId"] == identifier)
        allowed = {identifier, *project.get("identityProjectIds", []), *project.get("sourceProjectIds", [])}
        if project.get("stableProjectId"):
            allowed.add(project["stableProjectId"])
        if alias not in allowed:
            raise ValueError("public_reading_identifier_invalid")


@lru_cache(maxsize=6)
def _load(path: str, signature: tuple, view: str, revision: str) -> dict:
    # A changed/replaced file has another signature, including within one old
    # read-cache epoch. Verification happens once per immutable file identity.
    envelope = _read(Path(path), _MAX_BYTES)
    if (
        set(envelope) != {"schemaVersion", "revision", "payload"}
        or type(envelope["schemaVersion"]) is not int
        or envelope["schemaVersion"] != 1
    ):
        raise ValueError("public_reading_envelope_invalid")
    payload = envelope["payload"]
    if not isinstance(payload, dict) or envelope["revision"] != revision or digest(payload) != revision:
        raise ValueError("public_reading_digest_mismatch")
    _validate(view, payload)
    return payload


def product(target: Path, view: str, revision: str | None = None) -> tuple[dict, str]:
    view = _view(view)
    if revision is None:
        entry = current(target)["views"].get(view)
        if entry is None:
            raise LookupError("public_reading_not_published")
        revision = entry["revision"]
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        raise ValueError("public_reading_revision_invalid")
    path = _root(target) / view / f"{revision}.json"
    _safe(path, missing=True)
    if not path.exists():
        raise LookupError("public_reading_revision_not_found")
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    return _load(str(path), stamp, view, revision), revision


def board(target: Path, view: str, revision: str | None = None) -> dict:
    payload, revision = product(target, view, revision)
    return {**deepcopy(payload["board"]), "readingRevision": revision}


@lru_cache(maxsize=8)
def _load_project(path: str, signature: tuple, revision: str) -> dict:
    envelope = _read(Path(path), _MAX_BYTES)
    if (
        set(envelope) != {"schemaVersion", "payload"}
        or type(envelope["schemaVersion"]) is not int
        or envelope["schemaVersion"] != 1
        or not isinstance(envelope["payload"], dict)
        or digest(envelope["payload"]) != revision
    ):
        raise ValueError("public_reading_project_digest_mismatch")
    return envelope["payload"]


def _project(target: Path, revision: str) -> dict:
    path = _root(target) / "projects" / f"{revision}.json"
    _safe(path)
    stat = path.stat()
    return _load_project(str(path), (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino), revision)


def detail(
    target: Path, view: str, identifier: str, generation: str | None = None, *, revision: str | None = None
) -> dict:
    payload, revision = product(target, view, revision)
    if generation is not None and payload["board"].get("generationId") != generation:
        raise LookupError("public_reading_other_generation")
    key = payload["identifiers"].get(identifier, identifier)
    if key not in payload["details"]:
        raise LookupError("public_reading_other_project")
    value = _project(target, payload["details"][key])
    project = next(p for p in payload["board"]["projects"] if p["projectId"] == key)
    if any(value.get(field) != project.get(field) for field in ("projectId", "repository", "githubRepositoryId")):
        raise ValueError("public_reading_identity_mismatch")
    return {
        **deepcopy(value),
        "generationId": payload["board"].get("generationId"),
        "publishedAt": payload["board"].get("publishedAt"),
        "sources": deepcopy(payload["board"].get("sources", [])),
        "historical": view == "historical-hot",
        "readingRevision": revision,
    }


def publish(target: Path, view: str, build) -> dict:
    """Write-side only. Invalid candidates never replace the last good view."""
    view = _view(view)
    root = _root(target)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / view
    _safe(folder, missing=True)
    folder.mkdir(exist_ok=True)
    with file_lock(root / f"{view}.writer.lock"):
        payload = build()
        _validate(view, payload, candidate=True)
        if not payload["board"]["projects"] and payload["board"].get("state") in {
            "not_synced",
            "pending_daily_review",
        }:
            # A restart can still serve its durable products while source
            # files are unavailable. Absence is not a newly verified empty
            # board and must not replace a previously published real view.
            try:
                previous, _ = product(target, view)
            except LookupError:
                previous = None
            if previous is not None and (
                previous["board"].get("state") not in {"not_synced", "pending_daily_review"}
                or previous["board"].get("dailyReview") is not None
                or previous["board"].get("generationId") is not None
            ):
                raise ValueError("public_reading_source_unavailable")
        # Project bodies are content-addressed separately. A changed source
        # status or one changed card must not duplicate every other project's
        # full evidence on disk, nor make list GETs load those bodies.
        projects = root / "projects"
        _safe(projects, missing=True)
        projects.mkdir(exist_ok=True)
        references = {}
        for identifier, detail in payload["details"].items():
            value = {
                key: value
                for key, value in detail.items()
                if key not in {"generationId", "publishedAt", "sources", "historical", "readingRevision"}
            }
            revision = digest(value)
            path = projects / f"{revision}.json"
            _safe(path, missing=True)
            if not path.exists():
                atomic(path, {"schemaVersion": 1, "payload": value})
            _project(target, revision)
            references[identifier] = revision
        payload = {**payload, "details": references}
        _validate(view, payload)
        revision = digest(payload)
        path = folder / f"{revision}.json"
        _safe(path, missing=True)
        if not path.exists():
            atomic(path, {"schemaVersion": 1, "revision": revision, "payload": payload})
        # Verify the saved candidate before the atomic pointer update, also on
        # reuse. Never overwrite an existing corrupt immutable product.
        product(target, view, revision)
        with file_lock(root / "current.writer.lock"):
            pointer = current(target)
            old = pointer["views"].get(view)
            if old and old["revision"] == revision:
                return {"status": "reused", "revision": revision}
            pointer["views"][view] = {
                "revision": revision,
                "publishedAt": datetime.now(UTC).isoformat(),
                "generationId": payload["board"].get("generationId"),
            }
            atomic(root / "current.json", pointer)
        return {"status": "published", "revision": revision}
