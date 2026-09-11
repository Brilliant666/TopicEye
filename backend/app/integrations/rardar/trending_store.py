"""Versioned board snapshots and a read-only projection using existing atomic IO.

No Explosion/Selection fields are invented. A source capture is immutable;
the current serving pointer switches only after full validation. History is
derived from retained captures, deduplicated by source and source day (or the
explicitly labelled capture day when the publisher supplies no date).
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.integrations.rardar.project_identity import canonical_repository, project_id_for_repository
from app.services.llm.provider_budget import atomic, digest, file_lock, plain

SOURCES = {"github": "GitHub Trending", "trendshift": "Trendshift Trending"}
MATERIAL_FIELDS = (
    "githubRepositoryId",
    "materialState",
    "profile",
    "displayProfile",
    "displayEvidence",
    "material",
    "productForms",
    "runtimeEnvironments",
    "artifactTypes",
    "language",
    "topics",
    "license",
    "pushedAt",
)


def _apply_material(project: dict, material: dict | None) -> None:
    if not material:
        return
    # Repository name is canonical in both indexes. A known numeric ID must
    # also agree: a reused name must not inherit another repository's reading.
    if material.get("repository") and material["repository"] != project["repository"]:
        return
    if project.get("githubRepositoryId") and project["githubRepositoryId"] != material.get("githubRepositoryId"):
        return
    project.update({key: deepcopy(material[key]) for key in MATERIAL_FIELDS if key in material})


def apply_materials(snapshot: dict, materials: dict) -> dict:
    """Read-time v2 display overlay; the immutable board's facts stay untouched.

    v1 snapshots remain readable. Their small profile is only a legacy fallback;
    complete display fields always come from the current validated shared store.
    """
    result = deepcopy(snapshot)
    result["displaySchemaVersion"] = 2
    for project in result["projects"]:
        project.update(displayProfile=None, displayEvidence=None, material=None)
        for key in ("language", "license", "pushedAt"):
            project.setdefault(key, None)
        for key in ("topics", "productForms", "runtimeEnvironments", "artifactTypes"):
            project.setdefault(key, [])
        _apply_material(project, materials.get(project["repository"]))
    return result


def read_json(path: Path, maximum: int = 12_000_000) -> dict | None:
    plain(path, missing=True)
    if not path.exists():
        return None
    if path.stat().st_size > maximum:
        raise ValueError("trending_file_too_large")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("trending_invalid_json")
    return value


def validate_source(source: dict) -> None:
    if source.get("source") not in SOURCES or source.get("period") != "daily":
        raise ValueError("trending_source_invalid")
    url = urlparse(source.get("sourceUrl", ""))
    if (
        url.scheme != "https"
        or url.username
        or url.password
        or url.port not in (None, 443)
        or url.hostname not in {"github.com", "trendshift.io"}
        or url.path not in {"/", "", "/trending", "/github-trending-repositories"}
    ):
        raise ValueError("trending_source_url_invalid")
    when = datetime.fromisoformat(source["fetchedAt"])
    if when.tzinfo is None:
        raise ValueError("trending_time_invalid")
    if source.get("sourceDate") is not None:
        datetime.strptime(source["sourceDate"], "%Y-%m-%d")
    entries = source.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > 2000:
        raise ValueError("trending_untrusted_empty_or_size")
    repos, ranks = set(), set()
    for item in entries:
        repo = canonical_repository(item["repository"])
        rank = item["rank"]
        if repo in repos or type(rank) is not int or rank < 1 or rank in ranks:
            raise ValueError("trending_duplicate_identity_or_rank")
        for key in ("totalStars", "reportedDelta", "trendshiftStarsGained", "githubRepositoryId"):
            value = item.get(key)
            if value is not None and (type(value) is not int or value < (1 if key == "githubRepositoryId" else 0)):
                raise ValueError("trending_metric_invalid")
        repos.add(repo)
        ranks.add(rank)


def _root(target: Path) -> Path:
    root = target.absolute() / "trending-boards"
    plain(root, missing=True)
    return root


def _generation(root: Path, generation: str) -> dict:
    if not re.fullmatch(r"boards-[a-f0-9]{64}", generation):
        raise ValueError("trending_generation_invalid")
    value = read_json(root / "generations" / f"{generation}.json")
    if not value or digest(value) != generation.removeprefix("boards-"):
        raise ValueError("trending_generation_integrity")
    for source in value["captures"]:
        validate_source(source)
    expected = merge_sources(value["captures"], {s["source"]: s["status"] for s in value["projection"]["sources"]})
    actual = value["projection"]["projects"]
    if len(expected) != len(actual):
        raise ValueError("trending_projection_coverage_invalid")
    for first, second in zip(expected, actual, strict=True):
        if first.get("githubRepositoryId") is not None and first["githubRepositoryId"] != second.get(
            "githubRepositoryId"
        ):
            raise ValueError("trending_projection_facts_invalid")
        for key in (
            "repository",
            "repositoryUrl",
            "projectId",
            "appearances",
            "dualListed",
            "totalStars",
            "description",
        ):
            if first[key] != second[key]:
                raise ValueError("trending_projection_facts_invalid")
    return value


def load_snapshot(target: Path, generation: str | None = None) -> dict:
    root = _root(target)
    pointer = read_json(root / "current.json")
    if generation is None and not pointer:
        return {
            "schemaVersion": 1,
            "metricSchemaVersion": 2,
            "generationId": None,
            "publishedAt": None,
            "checkedAt": None,
            "sources": [],
            "projects": [],
            "state": "not_synced",
        }
    generation = generation or pointer["generationId"]
    value = _generation(root, generation)
    result = deepcopy(value["projection"])
    result["generationId"] = generation
    # The list and a detail pinned to the current generation share source health.
    # A historical generation never inherits a later generation's source check.
    check = read_json(root / "last-check.json") if pointer and pointer["generationId"] == generation else None
    if check:
        result["checkedAt"] = check["checkedAt"]
        # A failed latest check does not rewrite the immutable healthy snapshot.
        errors = {x["source"]: x.get("errorCode") for x in check["sources"] if x["status"] == "failed"}
        for source in result["sources"]:
            if source["source"] in errors:
                source.update(status="stale" if source["count"] else "failed", errorCode=errors[source["source"]])
    for source in result["sources"]:
        source["status"] = _source_status(source, source["status"])
    healthy = {s["source"] for s in result["sources"] if s["status"] == "healthy"}
    for project in result["projects"]:
        project["dualListed"] = project["dualListed"] and len(healthy) == 2
    _apply_display_metrics(result, value["captures"])
    return result


def _project(item: dict, source: dict) -> dict:
    repo = canonical_repository(item["repository"])
    return {
        "repository": repo,
        "repositoryUrl": f"https://github.com/{repo}",
        "projectId": project_id_for_repository(repo),
        "githubRepositoryId": item.get("githubRepositoryId"),
        "description": item.get("description"),
        "totalStars": item.get("totalStars"),
        "appearances": [_appearance(item, source)],
        "dualListed": False,
        "materialState": "unavailable",
        "profile": None,
    }


def _appearance(item: dict, source: dict) -> dict:
    return {
        "source": source["source"],
        "rank": item["rank"],
        "sourceDate": source.get("sourceDate"),
        "captureDate": source.get("captureDate", source["fetchedAt"][:10]),
        "fetchedAt": source["fetchedAt"],
        "period": "daily",
        "sourceUrl": source["sourceUrl"],
        "reportedDelta": item.get("reportedDelta"),
        "reportedDeltaPeriod": item.get("reportedDeltaPeriod"),
        "trendshiftMetric": item.get("trendshiftMetric"),
        "trendshiftStarsGained": item.get("trendshiftStarsGained"),
    }


def _source_status(source: dict, status: str) -> str:
    now = datetime.now(UTC)
    if source.get("fetchedAt") and now - datetime.fromisoformat(source["fetchedAt"]) > timedelta(hours=30):
        return "stale"
    if source.get("sourceDate") and source["sourceDate"] < now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat():
        return "stale"
    return status


def _metric_appearance(item: dict, source: dict, status: str) -> dict:
    """Display v2 only: never change v1 immutable facts or their validation."""
    return {
        **_appearance(item, source),
        "totalStars": item.get("totalStars"),
        "sourceStatus": _source_status(source, status),
        "trendshiftStarsGainedLabel": item.get("trendshiftStarsGainedLabel"),
        "trendshiftMetricPeriod": item.get("trendshiftMetricPeriod"),
    }


def _select_total_stars(project: dict, candidates: list[dict]) -> None:
    available = [item for item in candidates if type(item.get("totalStars")) is int and item["totalStars"] >= 0]
    if not available:
        project.update(totalStars=None, totalStarsSource=None)
        return
    selected = min(
        available,
        key=lambda item: (
            item["sourceStatus"] != "healthy",
            -datetime.fromisoformat(item["fetchedAt"]).timestamp(),
            list(SOURCES).index(item["source"]),
        ),
    )
    project.update(
        totalStars=selected["totalStars"],
        totalStarsSource={
            "source": selected["source"],
            "sourceDate": selected.get("sourceDate"),
            "fetchedAt": selected["fetchedAt"],
            "status": selected["sourceStatus"],
        },
    )


def _apply_display_metrics(snapshot: dict, captures: list[dict]) -> None:
    """Project verified capture metrics without changing union, ordering or disk."""
    statuses = {source["source"]: source["status"] for source in snapshot["sources"]}
    by_source = {
        source["source"]: (source, {canonical_repository(item["repository"]): item for item in source["entries"]})
        for source in captures
    }
    for project in snapshot["projects"]:
        appearances = []
        for old in project["appearances"]:
            source, entries = by_source[old["source"]]
            appearances.append(_metric_appearance(entries[project["repository"]], source, statuses[old["source"]]))
        project["appearances"] = appearances
        _select_total_stars(project, appearances)
    snapshot["metricSchemaVersion"] = 2


def merge_sources(captures: list[dict], statuses: dict[str, str]) -> list[dict]:
    # Persisted v1 contract. New display fields and cumulative-value selection
    # belong to _apply_display_metrics after this version has been verified.
    ordered = sorted(captures, key=lambda x: list(SOURCES).index(x["source"]))
    rows = [sorted(source["entries"], key=lambda x: x["rank"]) for source in ordered]
    projects: dict[str, dict] = {}
    for index in range(max((len(row) for row in rows), default=0)):
        for source, items in zip(ordered, rows, strict=True):
            if index >= len(items):
                continue
            item = items[index]
            key = canonical_repository(item["repository"])
            if key not in projects:
                projects[key] = _project(item, source)
            else:
                projects[key]["appearances"].append(_appearance(item, source))
                if not projects[key]["description"]:
                    projects[key]["description"] = item.get("description")
    for project in projects.values():
        appearances = project["appearances"]
        # No inferred publisher date. Same capture day is labelled as such;
        # explicit source dates, when present, must agree as well.
        days = {a["sourceDate"] or a["captureDate"] for a in appearances}
        project["dualListed"] = (
            len(appearances) == 2
            and len(days) == 1
            and all(statuses.get(a["source"]) == "healthy" for a in appearances)
        )
    ids = [p["projectId"] for p in projects.values()]
    if len(ids) != len(set(ids)):
        raise ValueError("trending_project_identity_collision")
    return list(projects.values())


def publish_sources(target: Path, results: list[dict], *, materials: dict | None = None) -> dict:
    root = _root(target)
    root.mkdir(parents=True, exist_ok=True)
    for name in ("captures", "generations"):
        (root / name).mkdir(exist_ok=True)
    with file_lock(root / "writer.lock", blocking=False):
        pointer = read_json(root / "current.json")
        previous = _generation(root, pointer["generationId"]) if pointer else None
        retained = {s["source"]: s for s in previous["captures"]} if previous else {}
        statuses, errors = {}, {}
        checked = datetime.now(UTC).isoformat()
        for source in results:
            key = source["source"]
            if key not in SOURCES:
                raise ValueError("trending_source_invalid")
            try:
                if source["status"] != "healthy":
                    raise ValueError("trending_source_unavailable")
                validate_source(source)
                capture = {k: v for k, v in source.items() if k not in {"status", "errorCode"}}
                old = retained.get(key)

                def semantic_capture(value):
                    return {k: v for k, v in value.items() if k not in {"fetchedAt", "contentDigest"}}

                if old and semantic_capture(old) == semantic_capture(capture):
                    statuses[key] = "healthy"
                    continue
                path = root / "captures" / f"{digest(capture)}.json"
                existing = read_json(path)
                if existing is None:
                    atomic(path, capture)
                elif existing != capture:
                    raise ValueError("trending_capture_integrity")
                retained[key] = capture
                statuses[key] = "healthy"
            except (ValueError, KeyError, TypeError):
                statuses[key] = "stale" if key in retained else "failed"
                errors[key] = "source_unavailable_or_invalid"
        atomic(
            root / "last-check.json",
            {
                "checkedAt": checked,
                "sources": [
                    {"source": key, "status": "failed" if key in errors else "healthy", "errorCode": errors.get(key)}
                    for key in SOURCES
                ],
            },
        )
        if not retained:
            raise ValueError("trending_no_valid_source")
        if previous and not any(status == "healthy" for status in statuses.values()):
            return {
                "changed": False,
                "generationId": pointer["generationId"],
                "count": len(previous["projection"]["projects"]),
            }
        projects = merge_sources(list(retained.values()), statuses)
        for project in projects:
            material = (materials or {}).get(project["repository"])
            # Persist the existing minimal v1 projection for archive readers;
            # full/current materials are resolved at GET time, never frozen to
            # the last source refresh or mixed into board fact identity.
            if material:
                _apply_material(
                    project,
                    {
                        key: material[key]
                        for key in ("repository", "githubRepositoryId", "materialState", "profile")
                        if key in material
                    },
                )
        source_states = [
            {
                "source": key,
                "label": SOURCES[key],
                "status": statuses.get(key, "failed"),
                "sourceDate": retained.get(key, {}).get("sourceDate"),
                "fetchedAt": retained.get(key, {}).get("fetchedAt"),
                "sourceUrl": retained.get(key, {}).get("sourceUrl"),
                "count": len(retained.get(key, {}).get("entries", [])),
                "errorCode": errors.get(key),
            }
            for key in SOURCES
        ]
        # The complete source content participates in identity; fetchedAt alone
        # is a check, not a reason to create another serving generation.
        semantic = {
            "projects": [
                {**p, "appearances": [{k: v for k, v in a.items() if k != "fetchedAt"} for a in p["appearances"]]}
                for p in projects
            ],
            "sources": [{k: v for k, v in s.items() if k != "fetchedAt"} for s in source_states],
        }
        if previous and previous.get("semanticDigest") == digest(semantic):
            return {"changed": False, "generationId": pointer["generationId"], "count": len(projects)}
        projection = {
            "schemaVersion": 1,
            "publishedAt": checked,
            "checkedAt": checked,
            "sources": source_states,
            "projects": projects,
            "state": "ready",
        }
        value = {
            "schemaVersion": 1,
            "captures": list(retained.values()),
            "semanticDigest": digest(semantic),
            "projection": projection,
        }
        identifier = f"boards-{digest(value)}"
        atomic(root / "generations" / f"{identifier}.json", value)
        _generation(root, identifier)
        atomic(root / "current.json", {"schemaVersion": 1, "generationId": identifier})
        return {"changed": True, "generationId": identifier, "count": len(projects)}


def historical_snapshot(target: Path, *, materials: dict | None = None) -> dict:
    current = load_snapshot(target)
    root = _root(target) / "captures"
    plain(root, missing=True)
    projects: dict[str, dict] = {}
    seen: dict[str, dict[tuple, dict]] = {}
    total_candidates: dict[str, list[dict]] = {}
    current_statuses = {source["source"]: source["status"] for source in current["sources"]}
    archive = _root(target) / "historical-evidence"
    plain(archive, missing=True)
    for path in sorted(archive.glob("*.json")) if archive.exists() else []:
        record = read_json(path)
        if not record or digest(record) != path.stem:
            raise ValueError("historical_evidence_integrity")
        validate_historical_evidence(record)
        for item in record["entries"]:
            key = canonical_repository(item["repository"])
            previous = projects.get(key)
            if previous and previous["historicalEvidence"][0]["fetchedAt"] >= record["fetchedAt"]:
                continue
            projects[key] = {
                "repository": key,
                "repositoryUrl": f"https://github.com/{key}",
                "projectId": project_id_for_repository(key),
                "githubRepositoryId": None,
                "description": item.get("description"),
                "totalStars": item.get("totalStars"),
                "appearances": [],
                "dualListed": False,
                "materialState": "unavailable",
                "profile": None,
                "historicalEvidence": [
                    {
                        "source": "github",
                        "sourceUrl": record["sourceUrl"],
                        "reportedAppearanceCount": item["reportedAppearanceCount"],
                        "sourceDate": None,
                        "fetchedAt": record["fetchedAt"],
                    }
                ],
            }
            seen[key] = {}
            total_candidates[key] = [
                {
                    "source": record["source"],
                    "sourceDate": None,
                    "fetchedAt": record["fetchedAt"],
                    "sourceStatus": _source_status(record, "healthy"),
                    "totalStars": item.get("totalStars"),
                }
            ]
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        capture = read_json(path)
        if not capture or path.stem != digest(capture):
            raise ValueError("trending_history_integrity")
        validate_source(capture)
        for item in capture["entries"]:
            key = canonical_repository(item["repository"])
            if key not in projects:
                projects[key] = _project(item, capture)
                projects[key]["appearances"] = []
                seen[key] = {}
                total_candidates[key] = []
            occurrence = (
                capture["source"],
                capture.get("sourceDate") or capture.get("captureDate", capture["fetchedAt"][:10]),
            )
            appearance = _metric_appearance(item, capture, current_statuses.get(capture["source"], "healthy"))
            total_candidates[key].append(appearance)
            previous = seen[key].get(occurrence)
            if previous is None or datetime.fromisoformat(appearance["fetchedAt"]) > datetime.fromisoformat(
                previous["fetchedAt"]
            ):
                seen[key][occurrence] = appearance
    for key, project in projects.items():
        project["appearances"] = sorted(
            seen[key].values(),
            key=lambda item: (
                -datetime.fromisoformat(item["fetchedAt"]).timestamp(),
                list(SOURCES).index(item["source"]),
            ),
        )
        _select_total_stars(project, total_candidates[key])
        material = (materials or {}).get(key, {})
        _apply_material(project, material)
        # Latest-per-day display must not move the actual first saved observation.
        times = [x["fetchedAt"] for x in total_candidates[key]]
        project.update(historyAppearances=len(seen[key]), firstSeenAt=min(times), lastSeenAt=max(times))
    return apply_materials(
        {
            **current,
            "metricSchemaVersion": 2,
            "projects": sorted(
                projects.values(), key=lambda p: (p["profile"] is None, -(p["totalStars"] or 0), p["repository"])
            ),
            "kind": "historical",
        },
        materials or {},
    )


def validate_historical_evidence(record: dict) -> None:
    if (
        record.get("period") != "historical-all-days"
        or record.get("source") != "github"
        or record.get("sourceUrl") != "https://trendshift.io/github-trending-repositories"
    ):
        raise ValueError("historical_source_invalid")
    if datetime.fromisoformat(record["fetchedAt"]).tzinfo is None:
        raise ValueError("historical_time_invalid")
    entries = record.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > 2000:
        raise ValueError("historical_empty_invalid")
    names = set()
    for item in entries:
        name = canonical_repository(item["repository"])
        count = item.get("reportedAppearanceCount")
        if name in names or type(count) is not int or count < 1:
            raise ValueError("historical_appearance_invalid")
        names.add(name)


def import_historical_evidence(target: Path, record: dict) -> dict:
    validate_historical_evidence(record)
    directory = _root(target) / "historical-evidence"
    plain(directory, missing=True)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest(record)}.json"
    existing = read_json(path)
    if existing is None:
        atomic(path, record)
    elif existing != record:
        raise ValueError("historical_evidence_integrity")
    return {"count": len(record["entries"]), "changed": existing is None}
