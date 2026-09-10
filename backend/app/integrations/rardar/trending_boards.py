"""Read two distinct public daily boards; never infer exact 24-hour facts.

Trendshift's homepage ItemList is its own ranking, NOT /github-trending.
Only the public rendered listing is consumed; no Signal API key is required.
Absolute board dates are unknown when the page only says Today/daily.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
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


def parse_board(source: str, html: str, *, fetched_at: datetime | None = None) -> dict[str, Any]:
    now = fetched_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("fetched_at_requires_timezone")
    label, url = SOURCES[source]
    entries = (parse_github if source == "github" else parse_trendshift)(html)
    dates = {entry.get("sourceDate") for entry in entries}
    source_date = next(iter(dates)) if source == "trendshift" and len(dates) == 1 else None
    return {
        "source": source,
        "label": label,
        "sourceUrl": url,
        "status": "healthy",
        "sourceDate": source_date,
        "period": "daily",
        "periodLabel": "Today (source-relative; absolute window not published)",
        "captureDate": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "fetchedAt": now.astimezone(UTC).isoformat(),
        "entries": entries,
        "errorCode": None,
        "contentDigest": hashlib.sha256(html.encode()).hexdigest(),
        "scope": "complete public daily repository listing; no language filter",
        "sourceDateNote": "Repository dateModified is not interpreted as the board date.",
    }


async def fetch_board(source: str) -> dict[str, Any]:
    label, url = SOURCES[source]
    now = datetime.now(UTC)
    try:
        kwargs = build_scraper_client_kwargs(url, timeout=30, follow_redirects=False)
        kwargs["headers"]["Accept"] = "text/html"
        async with httpx.AsyncClient(**kwargs) as client, client.stream("GET", url) as response:
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                raise BoardParseError("unexpected_content_type")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > _MAX_BYTES:
                    raise BoardParseError("source_response_too_large")
                chunks.append(chunk)
            html = b"".join(chunks).decode("utf-8", errors="strict")
        return parse_board(source, html, fetched_at=now)
    except Exception as exc:
        # Never persist transport exception text, proxy URLs or credentials.
        code = str(exc) if isinstance(exc, BoardParseError) else type(exc).__name__
        return {
            "source": source,
            "label": label,
            "sourceUrl": url,
            "status": "failed",
            "sourceDate": None,
            "period": "daily",
            "captureDate": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "fetchedAt": now.isoformat(),
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
