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
    """Keep a concise appearance basis, without deriving historical growth."""
    project["primaryGrowth"] = None
    dated = [a for a in project.get("appearances", []) if a.get("sourceDate")]
    windows = project.get("historicalRardarEvidence", [])
    events = [(a["sourceDate"], "board", a) for a in dated]
    events += [(_local_day(a["windowEndedAt"]), "rardar", a) for a in windows]
    if events:
        date, kind, item = max(events, key=lambda row: (row[0], row[1] == "board"))
        if kind == "board":
            rows = [a for a in dated if a["sourceDate"] == date]
            item = sorted(rows, key=lambda a: (a["source"] != "github", a["rank"]))[0]
            project["historicalContext"] = {
                **_appearance_basis(item),
                "kind": "board",
                "dateKind": "source",
                "date": date,
            }
        else:
            item = max(
                (a for a in windows if _local_day(a["windowEndedAt"]) == date),
                key=lambda a: _instant(a["windowEndedAt"]),
            )
            project["historicalContext"] = {
                **_appearance_basis(item),
                "kind": "rardar",
                "dateKind": "window",
                "date": item["windowEndedAt"],
            }
    elif project.get("appearances"):
        date = max(a.get("captureDate") or _local_day(a["fetchedAt"]) for a in project["appearances"])
        rows = [a for a in project["appearances"] if (a.get("captureDate") or _local_day(a["fetchedAt"])) == date]
        item = sorted(rows, key=lambda a: (a["source"] != "github", a["rank"]))[0]
        project["historicalContext"] = {**_appearance_basis(item), "kind": "board", "dateKind": "capture", "date": date}
    else:
        project["primaryGrowth"] = None
        records = project.get("historicalEvidence", [])
        item = max(records, key=lambda a: _instant(a["fetchedAt"])) if records else None
        project["historicalContext"] = {**_appearance_basis(item), "kind": "reported_count"} if item else None


def _appearance_basis(item: dict) -> dict:
    return {
        key: item[key]
        for key in ("source", "sourceUrl", "sourceDate", "fetchedAt", "rank", "windowEndedAt", "sourceGeneration")
        if key in item
    }


def select_historical_total(project: dict, candidates: list[dict]) -> None:
    """Choose a value together with its real source time, never its maximum.

    A dated archive read today still describes its source day. Unknown source
    times remain unknown; fetch time is only a saved-source fallback.
    Live repository metadata is applied separately by the shared metadata cache.
    """
    available = [row for row in candidates if type(row.get("totalStars")) is int and row["totalStars"] >= 0]
    if not available:
        project.update(totalStars=None, totalStarsSource=None)
        return

    def key(row):
        actual = row.get("windowEndedAt") or row.get("observedAt")
        day = row.get("sourceDate")
        fetched = _instant(row["fetchedAt"]).timestamp() if row.get("fetchedAt") else 0
        if actual:
            when = _instant(actual)
            return (when.date().isoformat(), when.timestamp(), row.get("source", ""))
        if day:
            # Only a day is known. Use day ordering, not an invented measuredAt.
            return (day, fetched, row.get("source", ""))
        return (_instant(row["fetchedAt"]).date().isoformat() if fetched else "", fetched, row.get("source", ""))

    selected = max(available, key=key)
    observed = selected.get("windowEndedAt") or selected.get("observedAt")
    project.update(
        totalStars=selected["totalStars"],
        totalStarsSource={
            "source": "rardar_history" if selected["source"] == "rardar_today" else selected["source"],
            "sourceUrl": selected.get("sourceUrl"),
            "sourceDate": selected.get("sourceDate"),
            "fetchedAt": selected.get("fetchedAt"),
            "observedAt": observed,
            "timeKind": "observed" if observed else "source_date" if selected.get("sourceDate") else "unknown",
            "historicalSaved": True,
            "status": selected.get("sourceStatus", "saved"),
        },
    )
