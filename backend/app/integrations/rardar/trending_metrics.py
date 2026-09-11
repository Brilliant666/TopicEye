"""One source-reported growth per display context; never rewrite source facts."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("trending_timestamp_timezone_required")
    return parsed.astimezone(UTC)


def _local_day(value: str) -> str:
    return _instant(value).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def select_growth(appearances: list[dict]) -> dict | None:
    for source, field in (("github", "reportedDelta"), ("trendshift", "trendshiftStarsGained")):
        rows = sorted(
            (item for item in appearances if item.get("source") == source),
            key=lambda item: _instant(item["fetchedAt"]),
            reverse=True,
        )
        for item in rows:
            value = item.get(field)
            if type(value) is int and value >= 0:
                return {**item, "value": value}
    return None


def order_today(projects: list[dict]) -> None:
    for project in projects:
        project["primaryGrowth"] = select_growth(project["appearances"])
    projects.sort(
        key=lambda p: (
            p["primaryGrowth"] is None,
            -(p["primaryGrowth"]["value"] if p["primaryGrowth"] else 0),
            p.get("totalStars") is None,
            -(p.get("totalStars") or 0),
            p["repository"].casefold(),
        )
    )
    for rank, project in enumerate(projects, 1):
        project["displayRank"] = rank


def apply_history_context(project: dict) -> None:
    """Select one period first, then its growth. Never borrow from another day."""
    dated = [a for a in project.get("appearances", []) if a.get("sourceDate")]
    windows = project.get("historicalRardarEvidence", [])
    events = [(a["sourceDate"], "board", a) for a in dated]
    events += [(_local_day(a["windowEndedAt"]), "rardar", a) for a in windows]
    if events:
        date, kind, item = max(events, key=lambda row: (row[0], row[1] == "board"))
        if kind == "board":
            rows = [a for a in dated if a["sourceDate"] == date]
            growth = select_growth(rows)
            item = growth or sorted(rows, key=lambda a: (a["source"] != "github", a["rank"]))[0]
            project["primaryGrowth"] = growth
            project["historicalContext"] = {**item, "kind": "board", "dateKind": "source", "date": date}
        else:
            item = max(
                (a for a in windows if _local_day(a["windowEndedAt"]) == date),
                key=lambda a: _instant(a["windowEndedAt"]),
            )
            project["primaryGrowth"] = {**item, "source": "rardar_history", "value": item["observedStarDelta"]}
            project["historicalContext"] = {
                **item,
                "kind": "rardar",
                "dateKind": "window",
                "date": item["windowEndedAt"],
            }
    elif project.get("appearances"):
        date = max(a.get("captureDate") or _local_day(a["fetchedAt"]) for a in project["appearances"])
        rows = [a for a in project["appearances"] if (a.get("captureDate") or _local_day(a["fetchedAt"])) == date]
        growth = select_growth(rows)
        item = growth or sorted(rows, key=lambda a: (a["source"] != "github", a["rank"]))[0]
        project["primaryGrowth"] = growth
        project["historicalContext"] = {**item, "kind": "board", "dateKind": "capture", "date": date}
    else:
        project["primaryGrowth"] = None
        records = project.get("historicalEvidence", [])
        item = max(records, key=lambda a: _instant(a["fetchedAt"])) if records else None
        project["historicalContext"] = {**item, "kind": "reported_count"} if item else None
