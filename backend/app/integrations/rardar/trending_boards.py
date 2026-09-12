"""Read two distinct public daily boards; never infer exact 24-hour facts.

Trendshift's homepage/calendar is its own ranking, NOT /github-trending.
Only public page data and its observed date-picker action are consumed; no
Signal API key is required. GitHub's absolute daily window remains unknown.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from app.services.scraper_http import build_scraper_client_kwargs

SOURCES = {
    "github": ("GitHub Trending", "https://github.com/trending?since=daily"),
    "trendshift": ("Trendshift Trending", "https://trendshift.io/"),
}
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+")
_MAX_BYTES = 4_000_000


class BoardParseError(ValueError):
    """An empty/changed source must not erase a healthy saved listing."""


def _repository(value: str) -> str:
    value = value.strip()
    if not _REPOSITORY.fullmatch(value) or value.split("/")[1] in {".", ".."}:
        raise BoardParseError("invalid_repository")
    return value


def _integer(value: str) -> int | None:
    value = value.strip().replace(",", "")
    # A rounded 2.2k is deliberately not an exact 2200.
    return int(value) if value.isascii() and value.isdigit() else None


def _validate_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        raise BoardParseError("empty_or_unrecognized_board")
    names = [entry["repository"].lower() for entry in entries]
    if len(names) != len(set(names)):
        raise BoardParseError("duplicate_repository")
    if [entry["rank"] for entry in entries] != list(range(1, len(entries) + 1)):
        raise BoardParseError("invalid_rank_sequence")
    return entries


def parse_github(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for card in soup.select("article.Box-row"):
        link = card.select_one("h2 a[href]")
        if link is None:
            raise BoardParseError("repository_card_missing_link")
        repository = _repository(link["href"].strip("/"))
        stars = card.select_one(f'a[href="/{repository}/stargazers"]')
        delta = re.search(r"([\d,]+)\s+stars? today", card.get_text(" ", strip=True))
        description = card.find("p")
        entries.append(
            {
                "repository": repository,
                "rank": len(entries) + 1,
                "description": description.get_text(" ", strip=True) if description else None,
                "totalStars": _integer(stars.get_text(strip=True)) if stars else None,
                "reportedDelta": _integer(delta[1]) if delta else None,
                "reportedDeltaPeriod": "GitHub reported stars today" if delta else None,
            }
        )
    return _validate_entries(entries)


def parse_trendshift(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    lists = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.get_text())
        except (ValueError, TypeError) as exc:
            raise BoardParseError("invalid_source_json") from exc
        if isinstance(value, dict) and value.get("@type") == "ItemList":
            lists.append(value)
    if len(lists) != 1 or lists[0].get("url", "").rstrip("/") != "https://trendshift.io":
        raise BoardParseError("own_daily_board_not_identified")
    listing = lists[0]
    if "daily" not in str(listing.get("name", "")).lower():
        raise BoardParseError("daily_period_not_identified")
    entries = []
    source_rows = _trendshift_rows(soup)
    for row in listing.get("itemListElement", []):
        item = row.get("item", {})
        if item.get("@type") != "SoftwareSourceCode":
            raise BoardParseError("unexpected_ranked_item_type")
        repository = _repository(item.get("name", ""))
        if item.get("codeRepository") != f"https://github.com/{repository}":
            raise BoardParseError("repository_identity_mismatch")
        path = urlparse(row.get("url", "")).path
        links = soup.find_all("a", href=path)
        link = next((a for a in links if a.get_text(strip=True) == repository), None)
        if not re.fullmatch(r"/repositories/\d+", path) or link is None:
            raise BoardParseError("structured_entry_not_in_visible_board")
        # Rank cards have a direct three-level container; ads and live mentions
        # are not ItemList members. Keep rounded display numbers as labels only.
        card = link.parent.parent.parent
        star = card.select_one("svg.lucide-star")
        star_text = star.parent.get_text(strip=True) if star else None
        raw = source_rows.get(repository, {})
        if raw and raw.get("rank") != row.get("position"):
            raise BoardParseError("source_rank_disagreement")
        entries.append(
            {
                "repository": repository,
                "rank": row.get("position"),
                "description": item.get("description") or None,
                "totalStars": raw.get("repository_stars"),
                "trendshiftStarsGained": raw.get("repository_stars_gained"),
                "trendshiftStarsGainedLabel": star_text,
                "trendshiftMetricPeriod": "Trendshift daily (source-defined window)",
                "sourceDate": str(raw["date"])[:10] if raw.get("date") else None,
                "reportedDelta": None,
                "reportedDeltaPeriod": None,
                "sourceRepositoryUrl": row["url"],
            }
        )
    if listing.get("numberOfItems") != len(entries):
        raise BoardParseError("source_count_mismatch")
    return _validate_entries(entries)


def _trendshift_rows(soup: BeautifulSoup) -> dict[str, dict[str, Any]]:
    """Decode public hydration JSON as data only; never evaluate JavaScript.

    Optional metadata supplements the separately validated visible ItemList.
    Trendshift repository_id is NOT claimed to be GitHub's numeric ID.
    """
    for script in soup.find_all("script"):
        text = script.get_text()
        if not text.startswith("self.__next_f.push("):
            continue
        try:
            payload = json.loads(text[len("self.__next_f.push(") :].rstrip().removesuffix(")"))
            wire = payload[1]
            marker = '"initialData":'
            if not isinstance(wire, str) or marker not in wire:
                continue
            rows, _ = json.JSONDecoder().raw_decode(wire.split(marker, 1)[1])
            if not isinstance(rows, list):
                continue
            result = {}
            for row in rows:
                if not isinstance(row, dict) or "full_name" not in row or "repository_stars_gained" not in row:
                    continue
                if not all(
                    type(row.get(k)) is int and row[k] >= 0 for k in ("repository_stars", "repository_stars_gained")
                ):
                    continue
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", str(row.get("date", ""))):
                    continue
                result[row["full_name"]] = row
            if result:
                return result
        except (ValueError, TypeError, IndexError):
            continue
    return {}


def parse_board(
    source: str, html: str, *, fetched_at: datetime | None = None, target_date: str | None = None
) -> dict[str, Any]:
    now = fetched_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("fetched_at_requires_timezone")
    if target_date is not None:
        _target_date(target_date)
    label, url = SOURCES[source]
    entries = (parse_github if source == "github" else parse_trendshift)(html)
    dates = {entry.get("sourceDate") for entry in entries}
    if source == "trendshift" and len(dates) != 1:
        raise BoardParseError("mixed_source_dates")
    source_date = next(iter(dates)) if source == "trendshift" and len(dates) == 1 else None
    result = {
        "source": source,
        "label": label,
        "sourceUrl": url,
        "status": "healthy",
        "sourceDate": source_date,
        "period": "daily",
        "periodLabel": "Today (source-relative; absolute window not published)",
        "targetPeriodDate": target_date,
        "acquisitionMode": "daily_snapshot",
        "historicalDateFetchSupported": False,
        "historicalDateFetchNote": (
            "Public calendar uses deployment-bound server actions; no stable date-specific interface is configured."
            if source == "trendshift"
            else "GitHub daily/stars today does not publish a verified absolute UTC period here."
        ),
        "captureDate": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "fetchedAt": now.astimezone(UTC).isoformat(),
        "checkedAt": now.astimezone(UTC).isoformat(),
        "entries": entries,
        "errorCode": None,
        "contentDigest": hashlib.sha256(html.encode()).hexdigest(),
        "scope": "complete public daily repository listing; no language filter",
        "sourceDateNote": "Repository dateModified is not interpreted as the board date.",
    }
    if source_date:
        start = datetime.combine(date.fromisoformat(source_date), datetime.min.time(), tzinfo=UTC)
        result.update(
            sourceTimezone="UTC",
            periodStartAt=start.isoformat(),
            periodEndAt=(start + timedelta(days=1)).isoformat(),
            periodLabel="UTC calendar day (Trendshift reported; not local exact 24-hour observation)",
            sourceDateNote=(
                "Source row date and Today (UTC) identify the source calendar day. "
                "Daily snapshot is not a verified final historical day; source finalization delay is unknown."
            ),
        )
    return result


def _target_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("invalid_target_date")
    return date.fromisoformat(value)


def _date_action_assets(html: str) -> list[str]:
    """Resolve only assets declared for the public date-picker component."""
    soup = BeautifulSoup(html, "html.parser")
    wires = []
    for script in soup.find_all("script"):
        text = script.get_text()
        if text.startswith("self.__next_f.push("):
            try:
                payload = json.loads(text[len("self.__next_f.push(") :].rstrip().removesuffix(")"))
                if isinstance(payload[1], str):
                    wires.append(payload[1])
            except (ValueError, TypeError, IndexError):
                continue
    wire = "\n".join(wires)
    refs = set(re.findall(r'\["\$","\$L([a-f0-9]+)",null,\{"initialData":', wire))
    if len(refs) != 1:
        return []
    match = re.search(r"(?:^|\n)" + re.escape(refs.pop()) + r":I([^\n]+)", wire)
    if not match:
        return []
    try:
        assets = json.loads(match[1])[1]
    except (ValueError, TypeError, IndexError):
        return []
    if not isinstance(assets, list):
        return []
    return [
        "https://trendshift.io" + path
        for path in reversed(assets[-4:])
        if isinstance(path, str) and re.fullmatch(r"/_next/static/chunks/[A-Za-z0-9_-]+\.js", path)
    ]


def _date_action_id(javascript: str) -> str | None:
    matches = set(
        re.findall(
            r'createServerReference\)\("([a-f0-9]{40,64})",[^;]{0,180}?"getRepositoryRecommendationsByDate"\)',
            javascript,
        )
    )
    return matches.pop() if len(matches) == 1 else None


def parse_trendshift_date_response(wire: str, *, target_date: str, fetched_at: datetime) -> dict[str, Any]:
    """Observed public calendar response: rows carry rank, date and gains together."""
    target = _target_date(target_date)
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at_requires_timezone")
    start = datetime.combine(target, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)
    if end > fetched_at:
        raise BoardParseError("target_period_not_ended")
    records = {}
    try:
        for line in wire.splitlines():
            key, separator, value = line.partition(":")
            if separator and re.fullmatch(r"[a-f0-9]+", key):
                records[key] = json.loads(value)
        pointer = records["0"]["a"]
        if not isinstance(pointer, str) or not re.fullmatch(r"\$@[a-f0-9]+", pointer):
            raise ValueError("invalid action reference")
        rows = records[pointer[2:]]
    except (ValueError, TypeError, KeyError) as exc:
        raise BoardParseError("invalid_date_response") from exc
    if not isinstance(rows, list) or not rows:
        raise BoardParseError("empty_date_response")
    entries = []
    for row in rows:
        if not isinstance(row, dict) or row.get("date") != f"{target_date}T00:00:00Z":
            raise BoardParseError("source_date_mismatch")
        if type(row.get("rank")) is not int or row["rank"] <= 0:
            raise BoardParseError("invalid_rank_sequence")
        if not all(type(row.get(k)) is int and row[k] >= 0 for k in ("repository_stars", "repository_stars_gained")):
            raise BoardParseError("invalid_date_metrics")
        if type(row.get("repository_id")) is not int or row["repository_id"] <= 0:
            raise BoardParseError("invalid_source_repository_id")
        entries.append(
            {
                "repository": _repository(row.get("full_name", "")),
                "rank": row.get("rank"),
                "description": row.get("repository_description") or None,
                "totalStars": row["repository_stars"],
                "trendshiftStarsGained": row["repository_stars_gained"],
                "trendshiftStarsGainedLabel": None,
                "trendshiftMetricPeriod": "Trendshift UTC calendar day",
                "sourceDate": target_date,
                "reportedDelta": None,
                "reportedDeltaPeriod": None,
                "sourceRepositoryUrl": f'https://trendshift.io/repositories/{row["repository_id"]}',
            }
        )
    return {
        "source": "trendshift",
        "label": SOURCES["trendshift"][0],
        "sourceUrl": SOURCES["trendshift"][1],
        "status": "healthy",
        "sourceDate": target_date,
        "targetPeriodDate": target_date,
        "acquisitionMode": "ended_utc_day",
        "historicalDateFetchSupported": True,
        "period": "daily",
        "periodLabel": "UTC calendar day (Trendshift reported)",
        "sourceTimezone": "UTC",
        "periodStartAt": start.isoformat(),
        "periodEndAt": end.isoformat(),
        "captureDate": fetched_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "fetchedAt": fetched_at.astimezone(UTC).isoformat(),
        "checkedAt": fetched_at.astimezone(UTC).isoformat(),
        "entries": _validate_entries(entries),
        "errorCode": None,
        "contentDigest": hashlib.sha256(wire.encode()).hexdigest(),
        "scope": "complete public date-picker repository response; all languages",
        "sourceDateNote": "Rank and growth come from the same dated response; source finalization delay remains unknown.",
    }


async def _read_response(response: httpx.Response, types: tuple[str, ...], *, limit: int = _MAX_BYTES) -> str:
    response.raise_for_status()
    if not any(value in response.headers.get("content-type", "") for value in types):
        raise BoardParseError("unexpected_content_type")
    chunks, size = [], 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise BoardParseError("source_response_too_large")
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="strict")


async def _fetch_ended_trendshift(client: httpx.AsyncClient, html: str, target_date: str) -> dict[str, Any] | None:
    for asset in _date_action_assets(html):
        async with client.stream("GET", asset) as response:
            javascript = await _read_response(response, ("javascript",), limit=1_000_000)
        action = _date_action_id(javascript)
        if not action:
            continue
        async with client.stream(
            "POST",
            SOURCES["trendshift"][1],
            headers={"Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8", "Next-Action": action},
            content=json.dumps([target_date, "all"], separators=(",", ":")),
        ) as response:
            wire = await _read_response(response, ("text/x-component",))
        return parse_trendshift_date_response(wire, target_date=target_date, fetched_at=datetime.now(UTC))
    return None


async def fetch_board(source: str, *, target_date: str | None = None) -> dict[str, Any]:
    """One public snapshot; a requested ended day is never fabricated.

    Trendshift's observed public date action is discovered from its current
    component assets, not a hard-coded deployment hash or invented API. A
    changed component can fall back to an explicitly labelled daily snapshot.
    """
    if target_date is not None:
        _target_date(target_date)
    label, url = SOURCES[source]
    now = datetime.now(UTC)
    try:
        kwargs = build_scraper_client_kwargs(url, timeout=30, follow_redirects=False)
        kwargs["headers"]["Accept"] = "text/html"
        async with httpx.AsyncClient(**kwargs) as client:
            async with client.stream("GET", url) as response:
                html = await _read_response(response, ("text/html",), limit=_MAX_BYTES)
            if source == "trendshift" and target_date:
                historical = await _fetch_ended_trendshift(client, html, target_date)
                if historical is not None:
                    return historical
        return parse_board(source, html, fetched_at=datetime.now(UTC), target_date=target_date)
    except Exception as exc:
        # Never persist transport exception text, proxy URLs or credentials.
        code = str(exc) if isinstance(exc, BoardParseError) else type(exc).__name__
        return {
            "source": source,
            "label": label,
            "sourceUrl": url,
            "status": "failed",
            "sourceDate": None,
            "targetPeriodDate": target_date,
            "acquisitionMode": "daily_snapshot",
            "historicalDateFetchSupported": False,
            "period": "daily",
            "captureDate": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "fetchedAt": None,
            "checkedAt": datetime.now(UTC).isoformat(),
            "entries": [],
            "errorCode": code,
        }


async def fetch_boards() -> list[dict[str, Any]]:
    """Zero-model, fixed public endpoints; one source failure stays local."""
    return list(await asyncio.gather(*(fetch_board(source) for source in SOURCES)))


def parse_trendshift_history(html: str, *, fetched_at: datetime | None = None) -> dict[str, Any]:
    """A bounded public historical-appearance index, NOT a dated daily board.

    The public default page exposes cumulative appearance counts but no dates.
    Never reinterpret its ordinal position as an original GitHub daily rank.
    """
    now = fetched_at or datetime.now(UTC)
    soup = BeautifulSoup(html, "html.parser")
    if "GitHub trending repositories" not in soup.get_text(" ", strip=True):
        raise BoardParseError("history_page_not_identified")
    rows = None
    for script in soup.find_all("script"):
        text = script.get_text()
        if not text.startswith("self.__next_f.push("):
            continue
        try:
            payload = json.loads(text[len("self.__next_f.push(") :].rstrip().removesuffix(")"))
            wire = payload[1]
            marker = '"repositories":'
            if isinstance(wire, str) and marker in wire:
                candidate, _ = json.JSONDecoder().raw_decode(wire.split(marker, 1)[1])
                if isinstance(candidate, list) and candidate and all("featured_count" in r for r in candidate):
                    rows = candidate
                    break
        except (ValueError, TypeError, IndexError):
            continue
    if rows is None:
        raise BoardParseError("history_records_unavailable")
    entries = []
    for row in rows:
        repository = _repository(row.get("full_name", ""))
        count = row.get("featured_count")
        if type(count) is not int or count <= 0:
            raise BoardParseError("history_appearance_unproven")
        path = f'/repositories/{row.get("repository_id")}'
        link = next((a for a in soup.find_all("a", href=path) if a.get_text(strip=True) == repository), None)
        if link is None:
            raise BoardParseError("history_entry_not_visible")
        card = link.parent.parent.parent
        if f"Featured on GitHub Trending {count} times" not in card.get_text(" ", strip=True):
            raise BoardParseError("history_count_not_visible")
        entries.append(
            {
                "repository": repository,
                "description": row.get("description") or None,
                "totalStars": row.get("watchers") if type(row.get("watchers")) is int else None,
                "sourceDate": None,
                "rank": None,
                "indexPosition": len(entries) + 1,
                "reportedAppearanceCount": count,
                "sourceRepositoryUrl": f"https://trendshift.io{path}",
            }
        )
    if len({r["repository"].lower() for r in entries}) != len(entries):
        raise BoardParseError("duplicate_history_repository")
    return {
        "source": "github",
        "discoverySource": "trendshift-github-history",
        "sourceUrl": "https://trendshift.io/github-trending-repositories",
        "status": "healthy",
        "period": "historical-all-days",
        "sourceDate": None,
        "captureDate": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "fetchedAt": now.astimezone(UTC).isoformat(),
        "entries": entries,
        "contentDigest": hashlib.sha256(html.encode()).hexdigest(),
        "scope": "Public initial historical index page only; not the complete historical inventory",
        "sourceDateNote": "Source proves prior GitHub Trending appearances; individual dates are not exposed.",
    }


parse_history_page = parse_trendshift_history


async def fetch_history() -> dict[str, Any]:
    """Explicit initial seed only: never implicitly called by daily refresh."""
    url = "https://trendshift.io/github-trending-repositories"
    kwargs = build_scraper_client_kwargs(url, timeout=30, follow_redirects=False)
    kwargs["headers"]["Accept"] = "text/html"
    async with httpx.AsyncClient(**kwargs) as client, client.stream("GET", url) as response:
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            raise BoardParseError("unexpected_content_type")
        chunks = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > _MAX_BYTES:
                raise BoardParseError("source_response_too_large")
            chunks.append(chunk)
    return parse_history_page(b"".join(chunks).decode("utf-8", errors="strict"))
