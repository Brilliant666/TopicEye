"""豆瓣电影热门 — https://movie.douban.com/j/search_subjects"""
from __future__ import annotations

import logging
from typing import List

import httpx
from . import BaseTrendingScraper, register_trending, TrendingEntry

logger = logging.getLogger(__name__)


@register_trending("douban")
class DoubanTrending(BaseTrendingScraper):
    SOURCE = "douban"
    CATEGORY = "entertainment"

    async def fetch(self, client: httpx.AsyncClient) -> List[TrendingEntry]:
        url = (
            "https://movie.douban.com/j/search_subjects"
            "?type=movie&tag=%E7%83%AD%E9%97%A8"
            "&sort=recommend&page_limit=30&page_start=0"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://movie.douban.com",
        }
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("douban trending fetch failed: %s", e)
            return []

        subjects = data.get("subjects", [])
        if not subjects:
            logger.warning("douban trending: empty subjects")
            return []

        results: List[TrendingEntry] = []
        for idx, item in enumerate(subjects, start=1):
            title = item.get("title", "").strip()
            if not title:
                continue

            rate = item.get("rate", "0")
            try:
                hot_val = int(float(str(rate)) * 10000)
            except (ValueError, TypeError):
                hot_val = 0

            results.append({
                "title": title,
                "rank": idx,
                "url": item.get("url", ""),
                "hot_value": hot_val,
                "hot_value_raw": str(rate),
                "trend": "stable",
                "cover_url": item.get("cover", ""),
                "extra": {
                    "rate": rate,
                },
            })

        logger.info("douban trending: fetched %d items", len(results))
        return results
