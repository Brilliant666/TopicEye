"""Read the existing public inventory and verified retained Profile identities.

Historical Find requests that only existed in process memory are not recoverable
from these stores. This inventory neither recreates questions nor writes caches.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2, _read_plain, digest
from app.integrations.rardar.selection_serving import SelectionServingError, SelectionServingLoader
from app.services.llm.provider_budget import plain

_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*")


def inventory_managed_materials(target: Path) -> dict:
    """Return public repository material inputs only; failures remain local."""
    projects: dict[str, dict] = {}
    identities: dict[int, set[str]] = {}
    retained: dict[str, tuple[object, dict]] = {}
    failed = 0
    incompatible = 0
    current_invalid = 0

    def children(directory: Path) -> list[Path]:
        plain(directory, missing=True)
        return sorted(directory.iterdir()) if directory.exists() else []

    registry = target / "public-project-evidence"
    try:
        directories = children(registry)
    except (OSError, ValueError, RuntimeError):
        directories = []
        failed += 1
    for directory in directories:
        try:
            raw = _read_plain(directory / "managed.json", root=registry, maximum=300_000)
            if raw is None:
                continue
            saved = json.loads(raw)
            repository = saved["repository"]
            if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
                raise ValueError("invalid repository")
            if directory.name != hashlib.sha256(repository.lower().encode()).hexdigest():
                raise ValueError("registry identity mismatch")
            facts = saved.get("facts", {})
            options = saved.get("options", {})
            if not isinstance(facts, dict) or not isinstance(options, dict):
                raise ValueError("invalid material metadata")
            projects[repository.casefold()] = {
                "repository": repository,
                "facts": {
                    key: value
                    for key in ("description", "pushedAt", "licenseSpdxId")
                    if isinstance(value := facts.get(key), str)
                },
                "options": {key: options.get(key) is True for key in ("include_readme_body", "readme_only")},
            }
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            failed += 1

    for name in ("selection-profile-cache", "profile-cache"):
        cache = target / name
        try:
            directories = children(cache / "profile-store" / "v2")
        except (OSError, ValueError, RuntimeError):
            failed += 1
            continue
        for directory in directories:
            try:
                paths = children(directory)
            except (OSError, ValueError, RuntimeError):
                failed += 1
                continue
            for path in paths:
                if path.suffix != ".json":
                    continue
                try:
                    raw = _read_plain(path, root=target)
                    if raw is None:
                        continue
                    try:
                        stored = ProfileStoreEnvelopeV2.model_validate_json(raw, strict=True)
                    except ValueError:
                        original = json.loads(raw)
                        if original.get("recordDigest") == digest(
                            {key: value for key, value in original.items() if key != "recordDigest"}
                        ):
                            incompatible += 1
                            continue
                        raise
                    identity = stored.cacheIdentity
                    repository = stored.profile.repository
                    if (
                        directory.name != str(identity.repositoryId)
                        or path.stem != identity.identityDigest
                        or not _REPOSITORY.fullmatch(repository)
                    ):
                        raise ValueError("profile path identity mismatch")
                    key = repository.casefold()
                    identities.setdefault(identity.repositoryId, set()).add(key)
                    row = {
                        "repository": repository,
                        "facts": {"description": stored.evidence.evidenceIndex.get("description")},
                        "options": {"include_readme_body": True, "readme_only": False},
                    }
                    if key not in retained or stored.storedAt > retained[key][0]:
                        retained[key] = (stored.storedAt, row)
                except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                    failed += 1
    # Only the current validated artifact, not a scan of historical generations.
    try:
        artifact = SelectionServingLoader(target).validate_generation()
        for assessment in artifact.assessments:
            candidate = assessment.candidate
            repository = candidate.repository
            if not _REPOSITORY.fullmatch(repository):
                raise ValueError("current repository invalid")
            key = repository.casefold()
            identities.setdefault(candidate.githubRepositoryId, set()).add(key)
            projects.setdefault(
                key,
                {
                    "repository": repository,
                    "facts": {"description": candidate.description},
                    "options": {"include_readme_body": True, "readme_only": False},
                },
            )
    except SelectionServingError as exc:
        if exc.code != "rardar_selection_not_configured":
            current_invalid = 1
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        current_invalid = 1
    conflicting = set()
    for repositories in identities.values():
        if len(repositories) > 1:
            conflicting.update(repositories)
    for key, (_stored_at, row) in retained.items():
        projects.setdefault(key, row)
    for key in conflicting:
        projects.pop(key, None)
    return {
        "projects": [projects[key] for key in sorted(projects)],
        "failed": failed,
        "invalidCacheRecords": failed,
        "incompatibleCacheRecords": incompatible,
        "invalidCurrentArtifact": current_invalid,
        "unresolvedProjectCount": len(conflicting),
    }
