"""
RSS / Atom feed crawler.

Fetches entries from a given feed URL, normalises them into ContentItem-like
dicts and returns them for further processing.
"""

from datetime import datetime
from typing import Any

import feedparser
import httpx


async def fetch_feed(url: str, timeout: int = 30) -> list[dict[str, Any]]:
    """Fetch and parse an RSS/Atom feed. Returns a list of entry dicts."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    entries: list[dict[str, Any]] = []

    for entry in feed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = datetime(*published[:6]) if published else datetime.utcnow()

        entries.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "author": entry.get("author", ""),
            "summary": entry.get("summary", ""),
            "raw_content": entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "",
            "tags": [tag.get("term", "") for tag in entry.get("tags", [])],
            "published_at": published_at,
        })

    return entries
