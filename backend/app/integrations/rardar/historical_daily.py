"""One immutable historical reading selection per Shanghai publication date.

The caller supplies eligible, evidence-validated projects. This module never
loads Profile bodies or requests external data. Star counts are not inputs to
selection. A single atomic date file is both the publication and its history;
there is no second pointer whose partial update could change today's members.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from random import SystemRandom

from app.integrations.rardar.project_identity import canonical_repository, project_id_for_repository
from app.integrations.rardar.trending_periods import ZONE
from app.integrations.rardar.trending_store import read_json
from app.services.llm.provider_budget import atomic, digest, file_lock, plain

POLICY_VERSION = "historical-daily-random-v1"
_DATE_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def _root(target: Path) -> Path:
    root = target / "historical-daily"
    plain(root, missing=True)
    return root


def _local(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("historical_daily_timezone_required")
    return now.astimezone(ZONE)


def _identity(project: dict) -> dict:
    repository = canonical_repository(project["repository"])
    identifier = project_id_for_repository(repository)
    if project.get("id", project.get("projectId")) != identifier:
        raise ValueError("historical_daily_identity_mismatch")
    numeric = project.get("githubRepositoryId")
    if numeric is not None and (isinstance(numeric, bool) or not isinstance(numeric, int) or numeric <= 0):
        raise ValueError("historical_daily_numeric_identity_invalid")
    return {"projectId": identifier, "repository": repository, "githubRepositoryId": numeric}


def _read(path: Path) -> dict:
    envelope = read_json(path, maximum=100_000)
    if not envelope or envelope.get("schemaVersion") != 1:
        raise ValueError("historical_daily_invalid")
    batch = envelope.get("batch")
    if not isinstance(batch, dict) or envelope.get("digest") != digest(batch):
        raise ValueError("historical_daily_digest_mismatch")
    if batch.get("date") != path.stem or batch.get("policyVersion") != POLICY_VERSION:
        raise ValueError("historical_daily_identity_mismatch")
    identities = [_identity(value) for value in batch["identities"]]
    identifiers = [value["projectId"] for value in identities]
    if batch.get("projectIds") != identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError("historical_daily_members_invalid")
    published = datetime.fromisoformat(batch["publishedAt"])
    if _local(published).date().isoformat() != batch["date"]:
        raise ValueError("historical_daily_date_invalid")
    if len(identifiers) > batch["limit"] or batch["eligibleCount"] < len(identifiers):
        raise ValueError("historical_daily_count_invalid")
    return batch


def _paths(root: Path, date: str | None = None) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        (path for path in root.iterdir() if _DATE_FILE.fullmatch(path.name) and (date is None or path.stem <= date)),
        reverse=True,
    )


def read_latest(target: Path, *, now: datetime | None = None) -> dict | None:
    """Read without creating directories, files, locks, or a new day's batch."""
    paths = _paths(_root(target), _local(now).date().isoformat() if now else None)
    return _read(paths[0]) if paths else None


def read_for_date(target: Path, day: str) -> dict | None:
    """Read a specific successful date, rejecting arbitrary paths."""
    if not _DATE_FILE.fullmatch(f"{day}.json"):
        raise ValueError("historical_daily_date_invalid")
    datetime.strptime(day, "%Y-%m-%d")
    path = _root(target) / f"{day}.json"
    return _read(path) if path.exists() else None


def publish(
    target: Path,
    projects: list[dict],
    *,
    now: datetime | None = None,
    trigger: str,
    limit: int = 8,
    avoidance_days: int = 7,
) -> dict | None:
    """Publish once; pre-09:00 waits, except explicit first initialization.

    Empty eligible sets are valid publications and remain empty for that date.
    Exceptions never replace an existing publication. Concurrent callers use
    the existing inter-process file lock and observe the winning date file.
    """
    local = _local(now or datetime.now(UTC))
    day = local.date().isoformat()
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("historical_daily_limit_invalid")
    if isinstance(avoidance_days, bool) or not isinstance(avoidance_days, int) or not 0 <= avoidance_days <= 365:
        raise ValueError("historical_daily_avoidance_invalid")
    if trigger not in {"main", "compensation", "manual_initialization", "manual", "startup", "catchup"}:
        raise ValueError("historical_daily_trigger_invalid")
    root = _root(target)
    root.mkdir(parents=True, exist_ok=True)
    with file_lock(root / "writer.lock"):
        paths = _paths(root)
        latest = _read(paths[0]) if paths else None
        # A delayed worker cannot publish backwards or overwrite a newer date.
        if latest and latest["date"] >= day:
            return latest
        if local.hour < 9 and not (trigger == "manual_initialization" and latest is None):
            return latest
        identities = {}
        for project in projects:
            identity = _identity(project)
            previous = identities.get(identity["projectId"])
            if previous and previous != identity:
                raise ValueError("historical_daily_duplicate_identity")
            identities[identity["projectId"]] = identity
        history = [_read(path) for path in paths]
        recent = history[:avoidance_days]
        seen = {identifier for batch in recent for identifier in batch["projectIds"]}
        last_seen = {}
        for batch in history:
            for identifier in batch["projectIds"]:
                last_seen.setdefault(identifier, batch["date"])
        random = SystemRandom()
        fresh = sorted(set(identities) - seen)
        random.shuffle(fresh)
        selected = fresh[:limit]
        fallback_count = 0
        if len(selected) < limit:
            remaining = sorted(set(identities) - set(selected))
            random.shuffle(remaining)
            remaining.sort(key=lambda identifier: last_seen.get(identifier, ""))
            fallback = remaining[: limit - len(selected)]
            selected.extend(fallback)
            fallback_count = len(fallback)
        random.shuffle(selected)
        batch = {
            "date": day,
            "publishedAt": local.isoformat(),
            "timezone": "Asia/Shanghai",
            "policyVersion": POLICY_VERSION,
            "limit": limit,
            "avoidanceDays": avoidance_days,
            "lookbackDays": avoidance_days,
            "trigger": trigger,
            "eligibleCount": len(identities),
            "candidateCount": len(identities),
            "fallbackCount": fallback_count,
            "relaxedRecentWindow": fallback_count > 0,
            "projectIds": selected,
            "identities": [identities[identifier] for identifier in selected],
        }
        atomic(root / f"{day}.json", {"schemaVersion": 1, "batch": batch, "digest": digest(batch)})
        return batch
