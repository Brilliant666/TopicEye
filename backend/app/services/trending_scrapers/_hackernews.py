"""Hacker News Top — https://hacker-news.firebaseio.com/"""

from __future__ import annotations

import logging

import httpx

from . import BaseTrendingScraper, TrendingEntry, register_trending

logger = logging.getLogger(__name__)


@register_trending("hackernews")
class HackerNewsTrending(BaseTrendingScraper):
    SOURCE = "hackernews"
    CATEGORY = "tech"

    def __init__(self) -> None:
        self.conditional_etag: str | None = None
        self.conditional_last_modified: str | None = None
        self._latest_etag: str | None = None
        self._latest_last_modified: str | None = None
        self.not_modified = False
        self.fetch_degraded = False

    async def fetch(self, client: httpx.AsyncClient) -> list[TrendingEntry]:
        headers: dict[str, str] = {}
        if self.conditional_etag:
            headers["If-None-Match"] = self.conditional_etag
        if self.conditional_last_modified:
            headers["If-Modified-Since"] = self.conditional_last_modified
        try:
            response = await client.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                headers=headers,
            )
            self._latest_etag = response.headers.get("etag") or self.conditional_etag
            self._latest_last_modified = response.headers.get("last-modified") or self.conditional_last_modified
            if response.status_code == 304:
                self.not_modified = True
                return []
            response.raise_for_status()
            ids_data = response.json()
            if not isinstance(ids_data, list):
                raise ValueError("topstories response is not a list")
        except Exception as exc:
            self.fetch_degraded = True
            logger.warning("hackernews trending fetch failed: %s", exc)
            return []
        ids = ids_data[:30]

        results: list[TrendingEntry] = []
        for idx, item_id in enumerate(ids, start=1):
            try:
                item_resp = await client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                )
                item_resp.raise_for_status()
                item = item_resp.json()
            except Exception:
                continue

            title = item.get("title", "").strip()
            if not title:
                continue

            score = item.get("score", 0)
            url = item.get("url", f"https://news.ycombinator.com/item?id={item_id}")

            results.append(
                {
                    "title": title,
                    "rank": idx,
                    "url": url,
                    "hot_value": score,
                    "hot_value_raw": str(score),
                    "trend": "up" if score > 100 else "stable",
                    "extra": {
                        "by": item.get("by", ""),
                        "descendants": item.get("descendants", 0),
                        "time": item.get("time"),
                        "hn_link": f"https://news.ycombinator.com/item?id={item_id}",
                    },
                }
            )

        logger.info("hackernews trending: fetched %d items", len(results))
        return results
