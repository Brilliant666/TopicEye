"""掘金热榜 — https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"""
from __future__ import annotations

import logging
from typing import List

import httpx
from . import BaseTrendingScraper, register_trending, TrendingEntry

logger = logging.getLogger(__name__)


@register_trending("juejin")
class JuejinTrending(BaseTrendingScraper):
    SOURCE = "juejin"
    CATEGORY = "tech"

    async def fetch(self, client: httpx.AsyncClient) -> List[TrendingEntry]:
        url = "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"
        payload = {
            "id_type": 2,
            "client_type": 2608,
            "sort_type": 200,  # 热门排序
            "cursor": "0",
            "limit": 30,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://juejin.cn/",
            "Content-Type": "application/json",
        }
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("juejin trending fetch failed: %s", e)
            return []

        items = data.get("data", [])
        if not items:
            logger.warning("juejin trending: empty data")
            return []

        results: List[TrendingEntry] = []
        for idx, item in enumerate(items[:30], start=1):
            article = item.get("article_info", {})
            title = article.get("title", "").strip()
            if not title:
                continue

            article_id = article.get("article_id", "")
            digg = item.get("article_info", {}).get("digg_count", 0)
            view = item.get("article_info", {}).get("view_count", 0)
            comment = item.get("article_info", {}).get("comment_count", 0)
            hot_val = digg * 100 + view + comment * 50

            author = item.get("author_user_info", {}).get("user_name", "")
            results.append({
                "title": title,
                "rank": idx,
                "url": f"https://juejin.cn/post/{article_id}",
                "hot_value": hot_val,
                "hot_value_raw": f"赞{digg} 读{view} 评{comment}",
                "trend": "up" if idx <= 5 else "stable",
                "extra": {
                    "author": author,
                    "digg_count": digg,
                    "view_count": view,
                    "comment_count": comment,
                },
            })

        logger.info("juejin trending: fetched %d items", len(results))
        return results
