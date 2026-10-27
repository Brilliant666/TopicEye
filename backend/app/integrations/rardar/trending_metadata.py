"""Small public repository metadata cache, independent of AI profile completion."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from urllib.parse import urljoin, urlparse

from app.integrations.rardar import project_identity
from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.read_scope import once
from app.integrations.rardar.trending_store import read_json
from app.services.llm.provider_budget import ProviderBudgetError, atomic, digest, file_lock, plain


def _path(target: Path, repository: str) -> Path:
    return target / "profile-cache" / "repository-metadata" / f"{digest(canonical_repository(repository))}.json"


def read(target: Path, project: dict) -> dict | None:
    repository = project_identity.resolved_repository(target, project)
    try:
        record = once(
            ("repository-metadata", str(target.absolute()), repository),
            lambda: read_json(_path(target, repository), maximum=30_000),
        )
    except ProviderBudgetError as exc:
        raise ValueError("repository_metadata_path_invalid") from exc
    if not record:
        return None
    if not isinstance(record, dict) or record.get("schemaVersion") not in (1, 2, 3):
        raise ValueError("repository_metadata_invalid")
    payload = record.get("payload")
    fields = {
        "repository",
        "githubRepositoryId",
        "language",
        "topics",
        "license",
        "fetchedAt",
        "sourceUrl",
    }
    if record["schemaVersion"] >= 2:
        fields |= {"description", "totalStars", "totalStarsFetchedAt"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("repository_metadata_invalid")
    if (
        record.get("digest") != digest(payload)
        or payload.get("repository") != repository
        or project.get("githubRepositoryId") not in (None, payload.get("githubRepositoryId"))
    ):
        raise ValueError("repository_metadata_binding_invalid")
    if (
        type(payload["githubRepositoryId"]) is not int
        or payload["githubRepositoryId"] <= 0
        or any(payload[key] is not None and not isinstance(payload[key], str) for key in ("language", "license"))
        or not isinstance(payload["topics"], list)
        or len(payload["topics"]) > 100
        or any(not isinstance(topic, str) for topic in payload["topics"])
        or payload["sourceUrl"] != f"https://api.github.com/repos/{repository}"
        or not isinstance(payload["fetchedAt"], str)
    ):
        raise ValueError("repository_metadata_invalid")
    fetched = datetime.fromisoformat(payload["fetchedAt"])
    if fetched.tzinfo is None or fetched > datetime.now(UTC) + timedelta(minutes=5):
        raise ValueError("repository_metadata_timestamp_invalid")
    if record["schemaVersion"] >= 2:
        if payload["description"] is not None and not isinstance(payload["description"], str):
            raise ValueError("repository_metadata_invalid")
        stars, measured = payload["totalStars"], payload["totalStarsFetchedAt"]
        if stars is not None and (type(stars) is not int or stars < 0):
            raise ValueError("repository_metadata_invalid")
        if (stars is None) != (measured is None):
            raise ValueError("repository_metadata_invalid")
        if measured is not None:
            measured_at = datetime.fromisoformat(measured)
            if measured_at.tzinfo is None or measured_at > fetched:
                raise ValueError("repository_metadata_timestamp_invalid")
    return payload


def content_revision(target: Path, project: dict) -> dict | None:
    """Material-relevant metadata identity, excluding Stars and observation times.

    README blob/content revisions remain evidence-package responsibilities. A
    pushed_at change alone does not assert that project material changed.
    """
    payload = read(target, project)
    if payload is None:
        return None
    record = read_json(_path(target, payload["repository"]), maximum=30_000)
    revision = record.get("contentRevision")
    if revision is None:
        if record.get("schemaVersion") == 3:
            raise ValueError("repository_content_revision_invalid")
        return None
    content = revision.get("content") if isinstance(revision, dict) else None
    if (
        not isinstance(revision, dict)
        or not isinstance(content, dict)
        or set(content) != {"githubRepositoryId", "description", "language", "topics", "license", "defaultBranch"}
        or any(content[key] != payload.get(key) for key in content if key != "defaultBranch")
        or (content["defaultBranch"] is not None and not isinstance(content["defaultBranch"], str))
        or revision.get("schemaVersion") != 1
        or type(revision.get("revision")) is not int
        or revision["revision"] < 1
        or revision.get("metadataDigest") != digest(revision.get("content"))
        or revision.get("recordDigest") != digest({k: v for k, v in revision.items() if k != "recordDigest"})
        or revision.get("sourceUrl") != payload["sourceUrl"]
        or not isinstance(revision.get("changedAt"), str)
        or not isinstance(revision.get("fetchedAt"), str)
    ):
        raise ValueError("repository_content_revision_invalid")
    changed, fetched = datetime.fromisoformat(revision["changedAt"]), datetime.fromisoformat(revision["fetchedAt"])
    if (
        changed.tzinfo is None
        or fetched.tzinfo is None
        or changed > fetched
        or fetched != datetime.fromisoformat(payload["fetchedAt"])
    ):
        raise ValueError("repository_content_revision_invalid")
    return revision


def read_content_version(target: Path, repository_id: int, metadata_digest: str) -> dict | None:
    """Read the small immutable metadata input, never reconstruct an old input."""
    import re

    if type(repository_id) is not int or repository_id <= 0 or not re.fullmatch(r"[a-f0-9]{64}", metadata_digest):
        raise ValueError("repository_content_revision_invalid")
    path = (
        target / "profile-cache" / "repository-metadata" / "revisions" / str(repository_id) / f"{metadata_digest}.json"
    )
    record = read_json(path, maximum=30_000)
    if record is None:
        return None
    payload = record.get("payload")
    if (
        record.get("schemaVersion") != 1
        or not isinstance(payload, dict)
        or record.get("digest") != digest(payload)
        or payload.get("githubRepositoryId") != repository_id
        or payload.get("metadataDigest") != metadata_digest
        or not isinstance(payload.get("content"), dict)
        or payload["content"].get("githubRepositoryId") != repository_id
        or digest(payload["content"]) != metadata_digest
        or not isinstance(payload.get("repository"), str)
        or canonical_repository(payload["repository"]) != payload["repository"]
        or payload.get("sourceUrl") != f"https://api.github.com/repos/{payload['repository']}"
        or not isinstance(payload.get("firstObservedAt"), str)
        or datetime.fromisoformat(payload["firstObservedAt"]).tzinfo is None
    ):
        raise ValueError("repository_content_revision_invalid")
    return payload


def _archive_content(target: Path, payload: dict, revision: dict) -> None:
    repository_id, identifier = payload["githubRepositoryId"], revision["metadataDigest"]
    path = target / "profile-cache" / "repository-metadata" / "revisions" / str(repository_id) / f"{identifier}.json"
    plain(path.parent, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock")):
        if read_content_version(target, repository_id, identifier) is not None:
            return
        content = {
            "githubRepositoryId": repository_id,
            "repository": payload["repository"],
            "metadataDigest": identifier,
            "content": revision["content"],
            "firstObservedAt": payload["fetchedAt"],
            "sourceUrl": payload["sourceUrl"],
        }
        atomic(path, {"schemaVersion": 1, "payload": content, "digest": digest(content)})


async def fetch(target: Path, project: dict, client) -> dict:
    """Read one GitHub metadata resource, following only bounded same-origin hops.

    A 301 supplies a location clue, not continuity evidence. A changed full_name
    is accepted only when a previously verified numeric identity agrees.
    """
    identity = project_identity.resolve(target, project)
    repository = identity["repository"] if identity else canonical_repository(project["repository"])
    expected = project.get("githubRepositoryId") or (identity or {}).get("githubRepositoryId")
    if expected is None:
        saved = read(target, project)
        expected = saved["githubRepositoryId"] if saved else None
    url = f"https://api.github.com/repos/{repository}"
    visited = set()
    for _ in range(3):
        if url in visited:
            raise ValueError("repository_redirect_invalid")
        visited.add(url)
        response = await client.get(url, follow_redirects=False)
        if response.status_code in (301, 302, 307, 308):
            next_url = urljoin(url, response.headers.get("location", ""))
            parsed = urlparse(next_url)
            parts = parsed.path.strip("/").split("/")
            valid_path = (
                len(parts) == 2 and parts[0] == "repositories" and parts[1].isdigit() and int(parts[1]) > 0
            ) or (len(parts) == 3 and parts[0] == "repos" and canonical_repository("/".join(parts[1:])))
            if (
                parsed.scheme != "https"
                or parsed.hostname != "api.github.com"
                or parsed.username
                or parsed.password
                or parsed.port not in (None, 443)
                or parsed.query
                or parsed.fragment
                or not valid_path
            ):
                raise ValueError("repository_redirect_invalid")
            url = next_url
            continue
        response.raise_for_status()
        metadata = response.json()
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("id")) is not int
            or metadata["id"] <= 0
            or not isinstance(metadata.get("full_name"), str)
            or expected not in (None, metadata["id"])
        ):
            raise ValueError("repository_identity_mismatch")
        current = canonical_repository(metadata["full_name"])
        path_parts = urlparse(url).path.strip("/").split("/")
        if path_parts[0] == "repositories" and int(path_parts[1]) != metadata["id"]:
            raise ValueError("repository_identity_mismatch")
        if current != repository and expected != metadata["id"]:
            raise ValueError("repository_identity_evidence_required")
        return metadata
    raise ValueError("repository_redirect_limit")


def save(target: Path, project: dict, meta: dict) -> dict:
    original_repository = canonical_repository(project["repository"])
    identity = project_identity.resolve(target, project)
    try:
        previous = read(target, project)
    except (ValueError, OSError):
        previous = None  # Optional metadata can be repaired; numeric binding below remains strict.
    expected = (
        project.get("githubRepositoryId")
        or (previous or {}).get("githubRepositoryId")
        or (identity or {}).get("githubRepositoryId")
    )
    if (
        not isinstance(meta, dict)
        or not isinstance(meta.get("full_name"), str)
        or type(meta.get("id")) is not int
        or meta["id"] <= 0
        or expected not in (None, meta["id"])
    ):
        raise ValueError("repository_identity_mismatch")
    repository = canonical_repository(meta["full_name"])
    if repository != original_repository and expected != meta["id"]:
        raise ValueError("repository_identity_evidence_required")
    language, topics, license_record = meta.get("language"), meta.get("topics", []), meta.get("license")
    if language is not None and not isinstance(language, str):
        raise ValueError("repository_metadata_invalid")
    if not isinstance(topics, list) or len(topics) > 100 or any(not isinstance(x, str) for x in topics):
        raise ValueError("repository_metadata_invalid")
    if license_record is not None and not isinstance(license_record, dict):
        raise ValueError("repository_metadata_invalid")
    license_id = (license_record or {}).get("spdx_id")
    if license_id in ("NOASSERTION", "OTHER"):
        license_id = None
    if license_id is not None and not isinstance(license_id, str):
        raise ValueError("repository_metadata_invalid")
    stars, description = meta.get("stargazers_count"), meta.get("description")
    if stars is not None and (type(stars) is not int or stars < 0):
        raise ValueError("repository_metadata_invalid")
    if description is not None and not isinstance(description, str):
        raise ValueError("repository_metadata_invalid")
    if meta.get("default_branch") is not None and not isinstance(meta["default_branch"], str):
        raise ValueError("repository_metadata_invalid")
    now = datetime.now(UTC).isoformat()
    payload = {
        "repository": repository,
        "githubRepositoryId": meta["id"],
        "language": language,
        "topics": topics,
        "license": license_id,
        "fetchedAt": now,
        "sourceUrl": f"https://api.github.com/repos/{repository}",
        "description": description,
        "totalStars": stars,
        "totalStarsFetchedAt": now if stars is not None else None,
    }
    path = _path(target, repository)
    plain(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock")):
        try:
            previous = read(target, project)
        except (ValueError, OSError):
            previous = None
        if (
            stars is None
            and previous
            and previous.get("totalStars") is not None
            and previous["githubRepositoryId"] == meta["id"]
        ):
            payload["totalStars"] = previous["totalStars"]
            payload["totalStarsFetchedAt"] = previous["totalStarsFetchedAt"]
        previous_revision = content_revision(target, project) if previous else None
        content = {key: payload[key] for key in ("githubRepositoryId", "description", "language", "topics", "license")}
        content["defaultBranch"] = meta.get(
            "default_branch", (previous_revision or {}).get("content", {}).get("defaultBranch")
        )
        content_hash = digest(content)
        changed = not previous_revision or previous_revision["metadataDigest"] != content_hash
        revision = {
            "schemaVersion": 1,
            "content": content,
            "metadataDigest": content_hash,
            "revision": (previous_revision or {}).get("revision", 0) + int(changed),
            "changedAt": now if changed else previous_revision["changedAt"],
            "fetchedAt": now,
            "sourceUrl": payload["sourceUrl"],
        }
        revision["recordDigest"] = digest(revision)
        identity_project = {**project, "githubRepositoryId": expected}
        project_identity.bind(target, identity_project, meta, fetched_at=now)
        _archive_content(target, payload, revision)
        # Keep the deployed v2 metadata wire readable by the rollback release.
        # The separately versioned revision envelope is additive and does not
        # change the original payload/digest contract. Prior v3 writes remain
        # readable above, without requiring any data rewrite during rollback.
        atomic(path, {"schemaVersion": 2, "payload": payload, "digest": digest(payload), "contentRevision": revision})
    return payload


def apply(snapshot: dict, target: Path) -> dict:
    for project in snapshot["projects"]:
        try:
            metadata = read(target, project)
        except (ValueError, OSError):
            continue  # Optional damaged metadata never invalidates verified board facts.
        if metadata:
            identity = project_identity.resolve(target, project)
            if identity:
                project.update(
                    stableProjectId=identity["projectId"],
                    resolvedRepository=identity["repository"],
                    identityAliases=list(identity["aliases"]),
                    identityProjectIds=sorted(project_identity.identifiers(identity)),
                )
            project.update({key: metadata[key] for key in ("language", "topics", "license")})
            project["githubRepositoryId"] = metadata["githubRepositoryId"]
            project["metadataSource"] = {key: metadata[key] for key in ("fetchedAt", "sourceUrl")}
            if not project.get("description") and metadata.get("description"):
                project["description"] = metadata["description"]
                project["descriptionSource"] = dict(project["metadataSource"])
            if snapshot.get("kind") == "historical" and metadata.get("totalStars") is not None:
                project["totalStars"] = metadata["totalStars"]
                project["totalStarsSource"] = {
                    "source": "github_metadata",
                    "sourceUrl": metadata["sourceUrl"],
                    "sourceDate": None,
                    "fetchedAt": metadata["totalStarsFetchedAt"],
                    "observedAt": metadata["totalStarsFetchedAt"],
                    "timeKind": "observed",
                    "historicalSaved": False,
                    "status": "saved",
                }
    return snapshot


async def refresh(
    target: Path, projects: list[dict], client, *, limit: int = 40, fresh_since: datetime | None = None
) -> dict:
    result = {"updated": 0, "reused": 0, "failed": [], "pending": 0, "providerCalls": 0}
    attempted = 0
    started = monotonic()
    for project in projects:
        try:
            try:
                saved = read(target, project)
            except (ValueError, OSError):
                saved = None  # Repair optional corrupt caches through verified metadata, not AI.
            fresh = False
            if saved:
                if fresh_since is not None:
                    measured = saved.get("totalStarsFetchedAt")
                    fresh = measured is not None and datetime.fromisoformat(measured) >= fresh_since
                else:
                    fresh = datetime.now(UTC) - datetime.fromisoformat(saved["fetchedAt"]) < timedelta(days=1)
            if fresh:
                result["reused"] += 1
                continue
            if attempted >= limit or monotonic() - started >= 45:
                result["pending"] += 1
                continue
            attempted += 1
            payload = await fetch(target, project, client)
            if fresh_since is not None and (
                not isinstance(payload, dict)
                or type(payload.get("stargazers_count")) is not int
                or payload["stargazers_count"] < 0
            ):
                raise ValueError("repository_star_count_missing")
            save(target, project, payload)
            result["updated"] += 1
        except Exception as exc:
            # Only a safe class name; no response bodies or credentials.
            result["failed"].append({"repository": project["repository"], "error": type(exc).__name__})
    return result
