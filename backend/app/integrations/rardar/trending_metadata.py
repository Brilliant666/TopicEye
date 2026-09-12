"""Small public repository metadata cache, independent of AI profile completion."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.trending_store import read_json
from app.services.llm.provider_budget import ProviderBudgetError, atomic, digest, file_lock, plain


def _path(target: Path, repository: str) -> Path:
    return target / "profile-cache" / "repository-metadata" / f"{digest(canonical_repository(repository))}.json"


def read(target: Path, project: dict) -> dict | None:
    try:
        record = read_json(_path(target, project["repository"]), maximum=30_000)
    except ProviderBudgetError as exc:
        raise ValueError("repository_metadata_path_invalid") from exc
    if not record:
        return None
    if not isinstance(record, dict) or record.get("schemaVersion") not in (1, 2):
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
    if record["schemaVersion"] == 2:
        fields |= {"description", "totalStars", "totalStarsFetchedAt"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("repository_metadata_invalid")
    repository = canonical_repository(project["repository"])
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
    if record["schemaVersion"] == 2:
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


def save(target: Path, project: dict, meta: dict) -> dict:
    repository = canonical_repository(project["repository"])
    if (
        not isinstance(meta, dict)
        or not isinstance(meta.get("full_name"), str)
        or canonical_repository(meta["full_name"]) != repository
        or type(meta.get("id")) is not int
        or meta["id"] <= 0
        or project.get("githubRepositoryId") not in (None, meta["id"])
    ):
        raise ValueError("repository_identity_mismatch")
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
        atomic(path, {"schemaVersion": 2, "payload": payload, "digest": digest(payload)})
    return payload


def apply(snapshot: dict, target: Path) -> dict:
    for project in snapshot["projects"]:
        try:
            metadata = read(target, project)
        except (ValueError, OSError):
            continue  # Optional damaged metadata never invalidates verified board facts.
        if metadata:
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


async def refresh(target: Path, projects: list[dict], client, *, limit: int = 40) -> dict:
    result = {"updated": 0, "reused": 0, "failed": [], "pending": 0, "providerCalls": 0}
    attempted = 0
    started = monotonic()
    for project in projects:
        try:
            try:
                saved = read(target, project)
            except (ValueError, OSError):
                saved = None  # Repair optional corrupt caches through verified metadata, not AI.
            if saved and datetime.now(UTC) - datetime.fromisoformat(saved["fetchedAt"]) < timedelta(days=1):
                result["reused"] += 1
                continue
            if attempted >= limit or monotonic() - started >= 45:
                result["pending"] += 1
                continue
            attempted += 1
            repository = canonical_repository(project["repository"])
            response = await client.get(f"/repos/{repository}")
            response.raise_for_status()
            save(target, project, response.json())
            result["updated"] += 1
        except Exception as exc:
            # Only a safe class name; no response bodies or credentials.
            result["failed"].append({"repository": project["repository"], "error": type(exc).__name__})
    return result
