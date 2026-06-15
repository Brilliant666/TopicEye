"""黑岩书城榜单 — https://h5.zhangwenpindu.cn/

源: 黑岩网（掌文品读）H5 书城的公开 CDN API。
- 接口域名: biz.zhangwenpindu.cn
- 鉴权: 无（自定义客户端头是 UA 指纹，httpx 直发即可）
- 暴露端点:
    GET /book/cdn/home?pageId=1663471786814947329     # 书城首页 (4 个 shelves, 27 本)
    GET /book/cdn/shelf/page?shelfId=...&pageNo=...   # 单榜单分页 (5th shelf「好书共赏」)
- 失败模式:
    * 反爬: 自定义头缺失 → code=90001「业务渠道不存在」(实测)
    * 列表类目: shelfId 是硬编码常量 (artemis_heiyan_recommendation_*),
      平台改版后失效, 届时 fail-fast 即可, 不要默默写空盘.
    * 详情/章节: 需 udid, 这里**不抓** (plan 范围外).
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Set

import httpx
from . import BaseTrendingScraper, register_trending, TrendingEntry

logger = logging.getLogger(__name__)


@register_trending("heiyan")
class HeiyanTrending(BaseTrendingScraper):
    SOURCE = "heiyan"
    CATEGORY = "webnovel"

    BASE = "https://biz.zhangwenpindu.cn"
    HOME_PAGE_ID = "1663471786814947329"
    THROTTLE_SECONDS = 0.2

    HEADERS = {
        "referer": "https://h5.zhangwenpindu.cn/",
        "app-name": "3",
        "client-platform": "2",
        "lang": "zh_CN",
        "app-version": "1.2.9",
        "package-time": "1736152412573",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    }

    # 注: 第 5 个 shelf「好书共赏」(artemis_heiyan_recommendation_good)
    # 实测不在 home 返回列表里, /shelf/page 也返空, 暂不抓.

    # ── Entry point ────────────────────────────────────────────────
    async def fetch(self, client: httpx.AsyncClient) -> List[TrendingEntry]:
        results: List[TrendingEntry] = []
        seen: Set[str] = set()

        home_payload = await self._fetch_home(client)
        if home_payload:
            home_shelves = (home_payload.get("data") or {}).get("shelves") or []
            for shelf in home_shelves:
                shelf_id = shelf.get("id", "")
                shelf_label = shelf.get("name", "书城榜单")
                for record in shelf.get("content") or []:
                    entry = self._build_entry(record, shelf_label, shelf_id)
                    if entry and entry["extra"]["book_id"] not in seen:
                        seen.add(entry["extra"]["book_id"])
                        results.append(entry)
            logger.info("heiyan home: %d unique books from %d shelves",
                        len(results), len(home_shelves))

        logger.info("heiyan trending: fetched %d unique books total", len(results))
        return results

    # ── Home API ───────────────────────────────────────────────────
    async def _fetch_home(self, client: httpx.AsyncClient) -> Optional[dict]:
        url = f"{self.BASE}/book/cdn/home?pageId={self.HOME_PAGE_ID}"
        try:
            resp = await client.get(url, headers=self.HEADERS, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning("heiyan home fetch failed: %s", exc)
            return None
        if not payload.get("success") or payload.get("code") != 1:
            logger.warning("heiyan home: code=%s msg=%s",
                           payload.get("code"), payload.get("message"))
            return None
        return payload

    # ── Entry builder ─────────────────────────────────────────────
    def _build_entry(
        self,
        record: dict,
        shelf_label: str,
        shelf_id: str,
    ) -> Optional[TrendingEntry]:
        book = record.get("book") or {}
        book_id = str(book.get("id") or "").strip()
        if not book_id:
            return None
        name = (book.get("name") or "").strip()
        if not name:
            return None

        author_obj = book.get("author") or {}
        intro = book.get("introduce") or ""
        if len(intro) > 200:
            intro = intro[:200] + "…"

        tags_raw = book.get("tags") or ""
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if t]
        else:
            tags = [t.strip() for t in str(tags_raw).replace("，", ",").split(",") if t.strip()]

        # home 来的直接用 record.sequence
        rank = record.get("sequence") or 0

        return {
            "title": name,
            "rank": rank,
            "hot_value": max(1, 1000 - rank),
            "url": f"https://h5.zhangwenpindu.cn/#/book/{book_id}",
            "hot_value_raw": shelf_label,
            "trend": "stable",
            "cover_url": book.get("iconUrlMedium") or book.get("iconUrl") or "",
            "extra": {
                "platform": "heiyan",
                "book_id": book_id,
                "author_id": str(author_obj.get("id") or ""),
                "author": author_obj.get("name", ""),
                "author_avatar": author_obj.get("iconUrlSmall", ""),
                "intro": intro,
                "words": book.get("words"),
                "words_str": book.get("wordsStr", ""),
                "tags": tags,
                "finished": bool(book.get("finished")),
                "free": bool(book.get("free")),
                "open": bool(book.get("open")),
                "type": book.get("type"),  # 1=短篇 3=长篇 (实测)
                "wx_book_id": book.get("wxBookId", ""),
                "tk_book_id": book.get("tkBookId", ""),
                "shelf": shelf_label,
                "shelf_id": shelf_id,
            },
        }
