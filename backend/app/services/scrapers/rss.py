"""
RSS / Atom feed scraper.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import feedparser
import httpx

from . import BaseScraper, register_scraper

logger = logging.getLogger(__name__)


@register_scraper("RSS")
class RSSScraper(BaseScraper):
    """Fetch and parse RSS/Atom feeds."""

    async def fetch(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await client.get(self.url)
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
                "raw_content": (
                    entry.get("content", [{}])[0].get("value", "")
                    if entry.get("content") else ""
                ),
                "tags": [tag.get("term", "") for tag in entry.get("tags", [])],
                "published_at": published_at,
            })

        return entries
