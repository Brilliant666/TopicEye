"""Rardar Project ID v1, matching upstream pipeline/project_identity.py.

This is the existing cross-repository contract, not a new numeric-ID migration.
Numeric GitHub IDs remain optional external continuity anchors.
"""

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from app.integrations.rardar.read_cache import cached, signature
from app.services.llm.provider_budget import atomic, digest, file_lock, plain

REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$")


def canonical_repository(value: str) -> str:
    if not isinstance(value, str) or not REPOSITORY.fullmatch(value):
        raise ValueError("invalid_repository")
    return value.lower()


def project_id_for_repository(value: str) -> str:
    canonical = canonical_repository(value)
    prefix = re.sub(r"[^a-z0-9]+", "-", canonical).strip("-")[:64].rstrip("-")
    return f"{prefix}--{hashlib.sha256(canonical.encode()).hexdigest()[:20]}"


def _index_path(target: Path) -> Path:
    return target / "profile-cache" / "repository-metadata" / "identities-v1.json"


def _index(target: Path) -> dict:
    path = _index_path(target)
    plain(path, missing=True)
    return cached(("repository-identities", signature(path)), lambda: _load_index(path))


def _load_index(path: Path) -> dict:
    if not path.exists():
        return {"projects": {}, "aliases": {}}
    if path.stat().st_size > 2_000_000:
        raise ValueError("repository_identity_index_invalid")
    record = json.loads(path.read_bytes())
    if not isinstance(record, dict):
        raise ValueError("repository_identity_index_invalid")
    data = record.get("payload")
    if (
        record.get("schemaVersion") != 1
        or not isinstance(data, dict)
        or set(data) != {"projects", "aliases"}
        or record.get("digest") != digest(data)
        or not isinstance(data["projects"], dict)
        or not isinstance(data["aliases"], dict)
    ):
        raise ValueError("repository_identity_index_invalid")
    aliases = {}
    for key, project in data["projects"].items():
        if (
            not isinstance(project, dict)
            or not key.isdigit()
            or int(key) <= 0
            or key != str(int(key))
            or type(project.get("githubRepositoryId")) is not int
            or project.get("githubRepositoryId") != int(key)
            or not isinstance(project.get("aliases"), list)
            or not project["aliases"]
            or any(not isinstance(name, str) for name in project["aliases"])
            or len(project["aliases"]) != len(set(project["aliases"]))
            or project.get("repository") not in project["aliases"]
            or not isinstance(project.get("projectId"), str)
            or project.get("projectId") not in {project_id_for_repository(name) for name in project["aliases"]}
        ):
            raise ValueError("repository_identity_index_invalid")
        for name in project["aliases"]:
            if canonical_repository(name) != name or name in aliases:
                raise ValueError("repository_identity_index_invalid")
            aliases[name] = int(key)
        witness = project.get("evidence")
        if (
            not isinstance(witness, dict)
            or witness.get("githubRepositoryId") != int(key)
            or witness.get("repository") != project["repository"]
            or witness.get("sourceUrl") != f"https://api.github.com/repos/{project['repository']}"
            or not isinstance(witness.get("fetchedAt"), str)
            or not isinstance(project.get("firstSeenAt"), str)
        ):
            raise ValueError("repository_identity_index_invalid")
        if (
            datetime.fromisoformat(witness["fetchedAt"]).tzinfo is None
            or datetime.fromisoformat(project["firstSeenAt"]).tzinfo is None
        ):
            raise ValueError("repository_identity_index_invalid")
    if aliases != data["aliases"] or any(type(value) is not int for value in data["aliases"].values()):
        raise ValueError("repository_identity_index_invalid")
    return data


def resolve(target: Path, project: dict) -> dict | None:
    """Read existing numeric continuity proof; a similar name is never proof."""
    if project.get("identityState") == "needs_identity_evidence":
        raise ValueError("repository_identity_evidence_required")
    repository = canonical_repository(project["repository"])
    expected = project.get("githubRepositoryId")
    if expected is not None and (type(expected) is not int or expected <= 0):
        raise ValueError("repository_identity_mismatch")
    path = _index_path(target)
    plain(path, missing=True)

    def selected(data):
        identifier = data["aliases"].get(repository)
        if identifier is not None and expected not in (None, identifier):
            raise ValueError("repository_identity_mismatch")
        return data["projects"].get(str(identifier))

    # Select one small record before copying, not the full shared index for
    # every card. Atomic writes invalidate the same existing read cache key.
    return cached(("repository-identities", signature(path)), lambda: _load_index(path), select=selected)


def resolved_repository(target: Path, project: dict) -> str:
    identity = resolve(target, project)
    return identity["repository"] if identity else canonical_repository(project["repository"])


def identifiers(identity: dict) -> set[str]:
    """Every old deterministic URL remains readable after a proven rename."""
    return {identity["projectId"], *(project_id_for_repository(name) for name in identity["aliases"])}


def unique_projects(target: Path, projects: list[dict]) -> list[dict]:
    """One work/selection slot per proven project, preserving source facts.

    Prefer the currently verified name as representative when present. Stars,
    growth and appearances are never summed or taken from another source row;
    source names/URLs remain traceable through the untouched original records.
    """
    grouped = {}
    for project in projects:
        repository = canonical_repository(project["repository"])
        try:
            identity = resolve(target, project)
        except (ValueError, OSError, RuntimeError):
            identity = None
        key = ("github", identity["githubRepositoryId"]) if identity else ("repository", repository)
        if key not in grouped:
            grouped[key] = {"project": project, "identity": identity, "repositories": [], "projectIds": []}
        group = grouped[key]
        if repository not in group["repositories"]:
            group["repositories"].append(repository)
        identifier = project_id_for_repository(repository)
        if identifier not in group["projectIds"]:
            group["projectIds"].append(identifier)
        if identity and repository == identity["repository"]:
            group["project"] = project
    result = []
    for group in grouped.values():
        project = deepcopy(group["project"])
        project["sourceRepositories"] = group["repositories"]
        project["sourceProjectIds"] = group["projectIds"]
        identity = group["identity"]
        if identity:
            project.update(
                stableProjectId=identity["projectId"],
                identityAliases=list(identity["aliases"]),
                identityProjectIds=sorted(identifiers(identity)),
            )
        result.append(project)
    return result


def bind(target: Path, project: dict, metadata: dict, *, fetched_at: str) -> dict:
    """Extend the metadata identity index after a validated GitHub response.

    The caller supplies the old numeric identity from verified board/metadata
    evidence. A redirect alone cannot authorize a new-name association.
    """
    old = canonical_repository(project["repository"])
    current = canonical_repository(metadata["full_name"])
    identifier = metadata["id"]
    supplied = project.get("githubRepositoryId")
    if (
        type(identifier) is not int
        or identifier <= 0
        or (supplied is not None and (type(supplied) is not int or supplied <= 0))
    ):
        raise ValueError("repository_identity_mismatch")
    path = _index_path(target)
    plain(path.parent, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock")):
        data = _index(target)
        known = data["aliases"].get(old)
        expected = project.get("githubRepositoryId") or known
        if expected not in (None, identifier) or (old != current and expected != identifier):
            raise ValueError("repository_identity_evidence_required")
        if any(data["aliases"].get(name) not in (None, identifier) for name in (old, current)):
            raise ValueError("repository_identity_mismatch")
        previous = data["projects"].get(str(identifier))
        if previous:
            stable = previous["projectId"]
            aliases = list(dict.fromkeys([*previous["aliases"], old, current]))
        else:
            stable = project_id_for_repository(old)
            aliases = list(dict.fromkeys([old, current]))
        value = {
            "githubRepositoryId": identifier,
            "projectId": stable,
            "repository": current,
            "aliases": aliases,
            "firstSeenAt": previous["firstSeenAt"] if previous else fetched_at,
            "evidence": {
                "repository": current,
                "githubRepositoryId": identifier,
                "sourceUrl": f"https://api.github.com/repos/{current}",
                "fetchedAt": fetched_at,
            },
        }
        data["projects"][str(identifier)] = value
        for name in aliases:
            data["aliases"][name] = identifier
        atomic(path, {"schemaVersion": 1, "payload": data, "digest": digest(data)})
    return value
